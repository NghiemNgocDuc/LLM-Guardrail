"""
Stripe Checkout for token packs (optional — billing UI works without Stripe for balance display).
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import HTTPException, status

from app.billing.plans import TokenPlan, plan_by_slug
from app.config import get_settings
from app.i18n import _t

logger = logging.getLogger(__name__)
settings = get_settings()


def stripe_configured() -> bool:
    return bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_WEBHOOK_SECRET)


def _stripe():
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_t("billing.payments_not_configured"),
        )
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def _stripe_price_id(plan: TokenPlan) -> str | None:
    key = f"STRIPE_PRICE_{plan.slug.upper()}"
    val = getattr(settings, key, "") or os.environ.get(key, "")
    return val or None


def create_checkout_session(
    *,
    user_id: str,
    user_email: str,
    plan: TokenPlan,
    purchase_id: str,
) -> str:
    stripe = _stripe()
    success = f"{settings.PUBLIC_APP_URL.rstrip('/')}/?view=billing&checkout=success"
    cancel = f"{settings.PUBLIC_APP_URL.rstrip('/')}/?view=billing&checkout=cancel"

    metadata = {
        "purchase_id": purchase_id,
        "user_id": user_id,
        "plan_slug": plan.slug,
        "tokens": str(plan.tokens),
    }

    price_id = _stripe_price_id(plan)
    if price_id:
        line_items: list[dict[str, Any]] = [{"price": price_id, "quantity": 1}]
    else:
        line_items = [
            {
                "price_data": {
                    "currency": plan.currency,
                    "unit_amount": plan.price_cents,
                    "product_data": {
                        "name": f"AI Guardrails — {plan.name}",
                        "description": f"{plan.tokens:,} gateway tokens",
                    },
                },
                "quantity": 1,
            }
        ]

    session = stripe.checkout.Session.create(
        mode="payment",
        customer_email=user_email,
        line_items=line_items,
        success_url=success,
        cancel_url=cancel,
        metadata=metadata,
    )
    return session.url, session.id


def construct_webhook_event(payload: bytes, sig_header: str | None):
    stripe = _stripe()
    if not sig_header:
        raise HTTPException(status_code=400, detail=_t("billing.missing_signature"))
    try:
        return stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        logger.warning("stripe.webhook_invalid: %s", e)
        raise HTTPException(status_code=400, detail=_t("billing.webhook_signature_invalid")) from e
