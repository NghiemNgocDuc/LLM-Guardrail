"""
FastAPI dependency injection.
Resolves the current user from either a JWT bearer token or an API key header.
"""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.models import APIKey, Organization, User

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ─── Password helpers ─────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ─── JWT helpers ─────────────────────────────────────────────────────────────

def create_access_token(user_id: str) -> str:
    from datetime import timedelta
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": user_id, "exp": expire, "type": "access"}, settings.SECRET_KEY, settings.ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    from datetime import timedelta
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": user_id, "exp": expire, "type": "refresh"}, settings.SECRET_KEY, settings.ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


# ─── API key hash ─────────────────────────────────────────────────────────────

def hash_api_key(raw_key: str) -> str:
    return pwd_context.hash(raw_key)


def verify_api_key(raw_key: str, hashed: str) -> bool:
    return pwd_context.verify(raw_key, hashed)


GATEWAY_KEY_PREFIX = "grg_"
# Full keys are "grg_" + token_urlsafe(32) (~47 chars). Prefix-only copies are 12 chars.
MIN_GATEWAY_KEY_LENGTH = 40


def normalize_gateway_api_key(raw_key: str) -> str:
    return raw_key.strip()


def validate_gateway_api_key_format(raw_key: str) -> None:
    if not raw_key.startswith(GATEWAY_KEY_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Expected a gateway API key (starts with grg_). "
                "Provider keys such as gsk_ or sk- cannot be used as X-Api-Key."
            ),
        )
    if len(raw_key) < MIN_GATEWAY_KEY_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "API key looks incomplete. Use the full grg_ key shown once when you "
                "created the key — not the short prefix from the API Keys table."
            ),
        )


async def resolve_api_key(raw_key: str, db: AsyncSession) -> APIKey:
    validate_gateway_api_key_format(raw_key)
    prefix = raw_key[:12]
    result = await db.execute(
        select(APIKey)
        .where(APIKey.key_prefix == prefix, APIKey.is_active == True)
        .options(selectinload(APIKey.org).selectinload(Organization.policy))
    )
    candidates = result.scalars().all()

    for key in candidates:
        if verify_api_key(raw_key, key.key_hash):
            if key.expires_at and key.expires_at < datetime.now(timezone.utc):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key expired")
            return key

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=(
            "Invalid API key. Create a new key in the dashboard (API Keys), copy the full "
            "grg_ value, and ensure you are calling the same deployment where the key was created."
        ),
    )


async def api_key_for_user(user: User, db: AsyncSession) -> APIKey:
    result = await db.execute(
        select(APIKey)
        .where(APIKey.owner_id == user.id, APIKey.is_active == True)
        .order_by(APIKey.created_at.desc())
        .limit(1)
        .options(selectinload(APIKey.org).selectinload(Organization.policy))
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No active gateway API key. Create one under API Keys.",
        )
    if key.expires_at and key.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key expired")
    return key


# ─── Dependencies ─────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve JWT bearer → User. Raises 401 if invalid."""
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    user = await db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_api_key_auth(
    x_api_key: Annotated[str | None, Header(alias="X-Api-Key")] = None,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    db: AsyncSession = Depends(get_db),
) -> APIKey:
    """
    Resolve gateway auth for /chat:
      - X-Api-Key: grg_... (integrations)
      - Authorization: Bearer grg_... (some HTTP clients)
      - Authorization: Bearer <JWT> (dashboard — uses newest active key for user)
    """
    if x_api_key and x_api_key.strip():
        return await resolve_api_key(normalize_gateway_api_key(x_api_key), db)

    if credentials and credentials.credentials:
        token = credentials.credentials.strip()
        if token.startswith(GATEWAY_KEY_PREFIX):
            return await resolve_api_key(token, db)

        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        user = await db.get(User, payload["sub"])
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
        return await api_key_for_user(user, db)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="X-Api-Key header required (gateway key starting with grg_)",
    )


AuthedAPIKey = Annotated[APIKey, Depends(get_api_key_auth)]
