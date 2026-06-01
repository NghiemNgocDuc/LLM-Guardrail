"""
Token pack billing — wallet balance, Stripe Checkout, webhooks.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.plans import TOKEN_PLANS, plan_by_slug
from app.config import get_settings
from app.database import get_db
from app.deps import CurrentUser
from app.models import TokenPurchase
from app.schemas import (
    BillingCheckoutRequest,
    BillingCheckoutResponse,
    BillingConfigOut,
    BillingPlanOut,
    BillingPurchaseOut,
    BillingWalletOut,
    MessageResponse,
)
from app.services.stripe_billing import (
    construct_webhook_event,
    create_checkout_session,
    stripe_configured,
)
from app.services.token_wallet import credit_tokens, ensure_wallet, get_wallet

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/billing", tags=["Billing"])


@router.get("/config", response_model=BillingConfigOut)
async def billing_config():
    return BillingConfigOut(
        billing_enabled=settings.BILLING_ENABLED,
        free_signup_tokens=settings.FREE_SIGNUP_TOKENS,
        stripe_configured=stripe_configured(),
        stripe_publishable_key=settings.STRIPE_PUBLISHABLE_KEY or None,
    )


@router.get("/plans", response_model=list[BillingPlanOut])
async def list_plans():
    return [
        BillingPlanOut(
            slug=p.slug,
            name=p.name,
            tokens=p.tokens,
            price_cents=p.price_cents,
            currency=p.currency,
            description=p.description,
            popular=p.popular,
            price_display=f"${p.price_cents / 100:.2f}",
        )
        for p in TOKEN_PLANS
    ]


@router.get("/wallet", response_model=BillingWalletOut)
async def get_my_wallet(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    wallet = await ensure_wallet(db, current_user.id)
    return BillingWalletOut(
        balance_tokens=wallet.balance_tokens,
        tokens_used_lifetime=wallet.tokens_used_lifetime,
        tokens_purchased_lifetime=wallet.tokens_purchased_lifetime,
        billing_enabled=settings.BILLING_ENABLED,
    )


@router.get("/purchases", response_model=list[BillingPurchaseOut])
async def list_purchases(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
):
    result = await db.execute(
        select(TokenPurchase)
        .where(TokenPurchase.user_id == current_user.id)
        .order_by(TokenPurchase.created_at.desc())
        .limit(min(limit, 100))
    )
    rows = result.scalars().all()
    return [
        BillingPurchaseOut(
            id=r.id,
            plan_slug=r.plan_slug,
            tokens_granted=r.tokens_granted,
            amount_cents=r.amount_cents,
            currency=r.currency,
            status=r.status,
            created_at=r.created_at,
            completed_at=r.completed_at,
        )
        for r in rows
    ]


@router.post("/checkout", response_model=BillingCheckoutResponse)
async def start_checkout(
    body: BillingCheckoutRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    if not settings.BILLING_ENABLED:
        raise HTTPException(status_code=400, detail="Billing is disabled on this deployment.")

    plan = plan_by_slug(body.plan_slug)
    if not plan:
        raise HTTPException(status_code=404, detail="Unknown plan")

    purchase = TokenPurchase(
        user_id=current_user.id,
        plan_slug=plan.slug,
        tokens_granted=plan.tokens,
        amount_cents=plan.price_cents,
        currency=plan.currency,
        status="pending",
    )
    db.add(purchase)
    await db.flush()

    if not stripe_configured():
        if settings.APP_ENV == "development":
            await credit_tokens(db, current_user.id, plan.tokens, purchase=purchase)
            await db.commit()
            return BillingCheckoutResponse(
                checkout_url=None,
                message=f"Dev mode: credited {plan.tokens:,} tokens (Stripe not configured).",
                purchase_id=purchase.id,
            )
        raise HTTPException(
            status_code=503,
            detail="Stripe is not configured. Set STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET.",
        )

    url, session_id = create_checkout_session(
        user_id=current_user.id,
        user_email=current_user.email,
        plan=plan,
        purchase_id=purchase.id,
    )
    purchase.stripe_checkout_session_id = session_id
    await db.commit()
    return BillingCheckoutResponse(checkout_url=url, purchase_id=purchase.id)


@router.post("/simulate-purchase", response_model=MessageResponse)
async def simulate_purchase(
    body: BillingCheckoutRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Local testing only — credits tokens without Stripe."""
    if settings.APP_ENV != "development":
        raise HTTPException(status_code=403, detail="Only available in development.")

    plan = plan_by_slug(body.plan_slug)
    if not plan:
        raise HTTPException(status_code=404, detail="Unknown plan")

    purchase = TokenPurchase(
        user_id=current_user.id,
        plan_slug=plan.slug,
        tokens_granted=plan.tokens,
        amount_cents=0,
        status="pending",
    )
    db.add(purchase)
    await db.flush()
    await credit_tokens(db, current_user.id, plan.tokens, purchase=purchase)
    await db.commit()
    return MessageResponse(message=f"Credited {plan.tokens:,} tokens ({plan.name}).")


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    event = construct_webhook_event(payload, request.headers.get("Stripe-Signature"))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        meta = session.get("metadata") or {}
        purchase_id = meta.get("purchase_id")
        user_id = meta.get("user_id")
        tokens = int(meta.get("tokens") or 0)

        if not purchase_id or not user_id or tokens <= 0:
            logger.error("stripe.webhook_missing_metadata session=%s", session.get("id"))
            return {"received": True}

        purchase = await db.get(TokenPurchase, purchase_id)
        if not purchase or purchase.user_id != user_id:
            logger.error("stripe.webhook_purchase_not_found id=%s", purchase_id)
            return {"received": True}

        if purchase.status == "completed":
            return {"received": True}

        purchase.stripe_checkout_session_id = session.get("id")
        await credit_tokens(db, user_id, tokens, purchase=purchase)
        await db.commit()
        logger.info("stripe.credited user=%s tokens=%s purchase=%s", user_id, tokens, purchase_id)

    return {"received": True}
