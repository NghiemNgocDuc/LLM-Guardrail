"""
FastAPI dependency injection.
Resolves the current user from either a Clerk JWT, a local JWT, or an API key header.
"""
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from jose.jwk import construct
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.database import get_db
from app.http_client import get_http_client
from app.i18n import _t
from app.models import APIKey, User

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ─── Password helpers ─────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ─── Clerk JWT verification (via JWKS) ────────────────────────────────────────

# ─── Networkless Clerk JWT verification ───────────────────────────────────────
# When CLERK_JWT_KEY (PEM public key) is set, verification is purely local.
# Fall back to JWKS fetch if only CLERK_JWKS_URL is configured.

_jwks_cache: dict | None = None
_jwks_cache_ts: float = 0
_clerk_public_key: object | None = None


async def _verify_clerk_token(token: str) -> dict:
    global _clerk_public_key, _jwks_cache, _jwks_cache_ts

    unverified = jwt.get_unverified_header(token)
    kid = unverified.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail=_t("auth.clerk_missing_kid"))

    if settings.CLERK_JWT_KEY:
        if _clerk_public_key is None:
            pem = settings.CLERK_JWT_KEY.replace("\\n", "\n")
            _clerk_public_key = construct(pem)
        try:
            return jwt.decode(
                token,
                _clerk_public_key,
                algorithms=[unverified.get("alg", "RS256")],
                options={"verify_aud": False},
            )
        except JWTError:
            raise HTTPException(status_code=401, detail=_t("auth.clerk_invalid_jwt"))

    now = time.time()
    if _jwks_cache and now - _jwks_cache_ts < 3600:
        jwks = _jwks_cache
    else:
        url = settings.CLERK_JWKS_URL
        if not url:
            raise HTTPException(status_code=500, detail=_t("auth.clerk_jwks_not_configured"))
        client = get_http_client()
        resp = await client.get(url, timeout=15.0)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_cache_ts = now
        jwks = _jwks_cache

    key_data = None
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            key_data = k
            break
    if not key_data:
        raise HTTPException(status_code=401, detail=_t("auth.clerk_no_matching_key"))

    rsa_key = construct(key_data)
    try:
        return jwt.decode(
            token,
            rsa_key,
            algorithms=[unverified.get("alg", "RS256")],
            options={"verify_aud": False},
        )
    except JWTError:
        raise HTTPException(status_code=401, detail=_t("auth.clerk_invalid_jwt"))


# ─── Local JWT helpers (legacy, for migration) ───────────────────────────────

def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": user_id, "exp": expire, "type": "access"}, settings.SECRET_KEY, settings.ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": user_id, "exp": expire, "type": "refresh"}, settings.SECRET_KEY, settings.ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_t("auth.token_expired"))


# ─── API key hash ─────────────────────────────────────────────────────────────

def hash_api_key(raw_key: str) -> str:
    return pwd_context.hash(raw_key)


def verify_api_key(raw_key: str, hashed: str) -> bool:
    return pwd_context.verify(raw_key, hashed)


GATEWAY_KEY_PREFIX = "grg_"
MIN_GATEWAY_KEY_LENGTH = 40


def normalize_gateway_api_key(raw_key: str) -> str:
    return raw_key.strip()


def validate_gateway_api_key_format(raw_key: str) -> None:
    if not raw_key.startswith(GATEWAY_KEY_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_t("api_key.invalid_format"),
        )
    if len(raw_key) < MIN_GATEWAY_KEY_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_t("api_key.incomplete"),
        )


async def resolve_api_key(raw_key: str, db: AsyncSession) -> APIKey:
    validate_gateway_api_key_format(raw_key)
    prefix = raw_key[:12]
    result = await db.execute(
        select(APIKey)
        .where(APIKey.key_prefix == prefix, APIKey.is_active == True)
    )
    candidates = result.scalars().all()

    for key in candidates:
        if verify_api_key(raw_key, key.key_hash):
            if key.expires_at and key.expires_at < datetime.now(timezone.utc):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_t("api_key.expired"))
            return key

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_t("api_key.invalid"),
    )


async def api_key_for_user(user: User, db: AsyncSession) -> APIKey:
    result = await db.execute(
        select(APIKey)
        .where(APIKey.owner_id == user.id, APIKey.is_active == True)
        .order_by(APIKey.created_at.desc())
        .limit(1)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_t("api_key.none_active"))
    if key.expires_at and key.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_t("api_key.expired"))
    return key


# ─── Dependencies ─────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_t("auth.token_missing"))

    token = credentials.credentials
    payload = None
    is_clerk = False

    if settings.CLERK_SECRET_KEY:
        try:
            payload = await _verify_clerk_token(token)
            is_clerk = True
        except HTTPException:
            pass

    if not payload:
        payload = decode_token(token)
        is_clerk = False

    if is_clerk:
        clerk_user_id = payload.get("sub")
        if not clerk_user_id:
            raise HTTPException(status_code=401, detail=_t("auth.clerk_missing_sub"))
        result = await db.execute(select(User).where(User.clerk_id == clerk_user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=401, detail=_t("auth.clerk_not_synced"))
    else:
        if payload.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_t("auth.invalid_token_type"))
        user = await db.get(User, payload["sub"])

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_t("auth.user_not_found"))
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_api_key_auth(
    x_api_key: Annotated[str | None, Header(alias="X-Api-Key")] = None,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    db: AsyncSession = Depends(get_db),
) -> APIKey:
    if x_api_key and x_api_key.strip():
        return await resolve_api_key(normalize_gateway_api_key(x_api_key), db)

    if credentials and credentials.credentials:
        token = credentials.credentials.strip()
        if token.startswith(GATEWAY_KEY_PREFIX):
            return await resolve_api_key(token, db)

        payload = None
        if settings.CLERK_SECRET_KEY:
            try:
                payload = await _verify_clerk_token(token)
            except HTTPException:
                pass

        if not payload:
            payload = decode_token(token)
            if payload.get("type") != "access":
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_t("auth.invalid_token_type"))

        clerk_id = payload.get("sub") if settings.CLERK_SECRET_KEY else None
        if clerk_id:
            result = await db.execute(select(User).where(User.clerk_id == clerk_id))
            user = result.scalar_one_or_none()
        else:
            user = await db.get(User, payload["sub"])

        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_t("auth.user_not_found"))
        return await api_key_for_user(user, db)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_t("api_key.missing_header"))
    )


AuthedAPIKey = Annotated[APIKey, Depends(get_api_key_auth)]
