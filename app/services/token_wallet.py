"""
Per-user token balance for gateway LLM usage (input + output tokens).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import TokenPurchase, TokenWallet, User

settings = get_settings()


def unlimited_email_set() -> set[str]:
    return {e.strip().lower() for e in settings.BILLING_UNLIMITED_EMAILS.split(",") if e.strip()}


async def user_has_unlimited_tokens(db: AsyncSession, user_id: str) -> bool:
    user = await db.get(User, user_id)
    if not user:
        return False
    return user.email.lower() in unlimited_email_set()


async def get_wallet(db: AsyncSession, user_id: str) -> TokenWallet | None:
    result = await db.execute(select(TokenWallet).where(TokenWallet.user_id == user_id))
    return result.scalar_one_or_none()


async def ensure_wallet(db: AsyncSession, user_id: str) -> TokenWallet:
    wallet = await get_wallet(db, user_id)
    if wallet:
        return wallet
    wallet = TokenWallet(
        user_id=user_id,
        balance_tokens=settings.FREE_SIGNUP_TOKENS if settings.BILLING_ENABLED else 10**12,
    )
    db.add(wallet)
    await db.flush()
    return wallet


def estimate_request_tokens(prompt: str, max_output_tokens: int) -> int:
    """Conservative pre-check before calling the LLM."""
    prompt_est = max(1, len(prompt) // 4)
    return prompt_est + max_output_tokens


async def require_balance(db: AsyncSession, user_id: str, needed: int) -> TokenWallet:
    if not settings.BILLING_ENABLED:
        return await ensure_wallet(db, user_id)

    if await user_has_unlimited_tokens(db, user_id):
        return await ensure_wallet(db, user_id)

    wallet = await ensure_wallet(db, user_id)
    if wallet.balance_tokens < needed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "insufficient_tokens",
                "message": "Token balance too low. Purchase a plan under Billing.",
                "balance_tokens": wallet.balance_tokens,
                "needed_tokens": needed,
            },
        )
    return wallet


async def deduct_tokens(db: AsyncSession, wallet: TokenWallet, amount: int) -> None:
    if not settings.BILLING_ENABLED or amount <= 0:
        return
    if await user_has_unlimited_tokens(db, wallet.user_id):
        return
    wallet.balance_tokens = max(0, wallet.balance_tokens - amount)
    wallet.tokens_used_lifetime += amount
    wallet.updated_at = datetime.now(timezone.utc)
    await db.flush()


async def credit_tokens(
    db: AsyncSession,
    user_id: str,
    amount: int,
    *,
    purchase: TokenPurchase | None = None,
) -> TokenWallet:
    wallet = await ensure_wallet(db, user_id)
    wallet.balance_tokens += amount
    wallet.tokens_purchased_lifetime += amount
    wallet.updated_at = datetime.now(timezone.utc)
    if purchase:
        purchase.status = "completed"
        purchase.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return wallet
