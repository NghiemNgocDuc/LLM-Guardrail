"""Opaque auth tokens for email verification and password reset."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuthToken, User

TOKEN_PURPOSE_VERIFY = "verify_email"
TOKEN_PURPOSE_RESET = "password_reset"


def generate_raw_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def build_action_url(public_app_url: str, path: str, raw_token: str) -> str:
    base = public_app_url.rstrip("/")
    return f"{base}{path}?token={raw_token}"


async def create_auth_token(
    db: AsyncSession,
    *,
    user_id: str,
    purpose: str,
    expire_hours: int,
) -> str:
    """Invalidate prior tokens for this purpose, store hash, return raw token once."""
    await db.execute(
        delete(AuthToken).where(AuthToken.user_id == user_id, AuthToken.purpose == purpose)
    )
    raw = generate_raw_token()
    db.add(
        AuthToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=hash_token(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=expire_hours),
        )
    )
    await db.flush()
    return raw


async def consume_auth_token(
    db: AsyncSession,
    *,
    raw_token: str,
    purpose: str,
) -> User | None:
    token_hash = hash_token(raw_token.strip())
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(AuthToken).where(
            AuthToken.token_hash == token_hash,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
            AuthToken.expires_at > now,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        return None

    user = await db.get(User, row.user_id)
    if not user:
        return None

    row.used_at = now
    await db.flush()
    return user
