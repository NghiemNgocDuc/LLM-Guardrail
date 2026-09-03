"""
Auth endpoints:
  POST /auth/clerk-webhook    — Clerk user events (create / update / delete)
  GET  /auth/me               — current user info
  PATCH /auth/profile         — update profile fields
"""
import hashlib
import hmac
import json
import logging
import time
from collections import OrderedDict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import CurrentUser
from app.deps import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from app.i18n import _t
from app.models import Organization, OrgPolicy, User
from app.schemas import MessageResponse, UpdateProfileRequest, UserOut
from app.config import get_settings
from app.defaults import DEFAULT_COMPLIANCE, DEFAULT_INPUT_RULES, DEFAULT_OUTPUT_RULES, DEFAULT_TOPIC_POLICY
from app.services.token_wallet import ensure_wallet
from app.services.auth_tokens import TOKEN_PURPOSE_RESET, TOKEN_PURPOSE_VERIFY, build_action_url, consume_auth_token, create_auth_token
from app.services.email import send_email, send_password_reset_email

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class SignupRequest(LoginRequest):
    full_name: str = Field(min_length=1, max_length=120)
    org_name: str | None = Field(default=None, max_length=120)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenRequest(BaseModel):
    token: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=256)


def _auth_response(user: User) -> dict:
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
    }


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == str(body.email).lower()))
    user = result.scalar_one_or_none()
    if not user or not user.is_active or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail=_t("auth.invalid_credentials"))
    user.last_login = datetime.now(timezone.utc)
    await db.flush()
    return _auth_response(user)


@router.post("/signup", response_model=MessageResponse)
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)):
    email = str(body.email).lower()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    org = Organization(name=body.org_name or f"{body.full_name}'s workspace", slug=f"{email.split('@')[0]}-{time.time_ns()}")
    db.add(org)
    await db.flush()
    user = User(email=email, hashed_password=hash_password(body.password), full_name=body.full_name, org_id=org.id, email_verified=not settings.email_configured)
    db.add(user)
    await db.flush()
    db.add(OrgPolicy(org_id=org.id, input_rules=DEFAULT_INPUT_RULES, output_rules=DEFAULT_OUTPUT_RULES, topic_policy=DEFAULT_TOPIC_POLICY, compliance_rules=DEFAULT_COMPLIANCE))
    await ensure_wallet(db, user.id)
    if settings.email_configured and not user.email_verified:
        raw = await create_auth_token(db, user_id=user.id, purpose=TOKEN_PURPOSE_VERIFY, expire_hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS)
        await send_email(email, f"Verify your {settings.APP_NAME} account", f"Verify your account: {build_action_url(settings.PUBLIC_APP_URL, '/verify-email', raw)}", "")
    return {"message": "Account created. You can sign in." if user.email_verified else "Account created. Check your email to verify your account."}


@router.post("/refresh")
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = await db.get(User, payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return _auth_response(user)


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(body: TokenRequest, db: AsyncSession = Depends(get_db)):
    user = await consume_auth_token(db, raw_token=body.token, purpose=TOKEN_PURPOSE_VERIFY)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    user.email_verified = True
    return {"message": "Email verified. You can sign in."}


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(body: dict, db: AsyncSession = Depends(get_db)):
    email = str(body.get("email", "")).lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user and settings.email_configured:
        raw = await create_auth_token(db, user_id=user.id, purpose=TOKEN_PURPOSE_RESET, expire_hours=settings.PASSWORD_RESET_EXPIRE_HOURS)
        await send_password_reset_email(email, build_action_url(settings.PUBLIC_APP_URL, "/reset-password", raw))
    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    user = await consume_auth_token(db, raw_token=body.token, purpose=TOKEN_PURPOSE_RESET)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    user.hashed_password = hash_password(body.new_password)
    return {"message": "Password reset. You can sign in."}


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(body: dict, db: AsyncSession = Depends(get_db)):
    email = str(body.get("email", "")).lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user and not user.email_verified and settings.email_configured:
        raw = await create_auth_token(db, user_id=user.id, purpose=TOKEN_PURPOSE_VERIFY, expire_hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS)
        await send_email(email, f"Verify your {settings.APP_NAME} account", f"Verify your account: {build_action_url(settings.PUBLIC_APP_URL, '/verify-email', raw)}", "")
    return {"message": "If that email exists, a verification link has been sent."}

# Webhook idempotency — deduplicate Clerk retries within a 1-hour window
_processed_webhooks: OrderedDict[str, float] = OrderedDict()
_MAX_WEBHOOK_CACHE = 10_000


def _is_duplicate_webhook(svix_id: str) -> bool:
    now = time.time()
    cutoff = now - 3600
    while _processed_webhooks and next(iter(_processed_webhooks.values())) < cutoff:
        _processed_webhooks.popitem(last=False)
    if svix_id in _processed_webhooks:
        return True
    _processed_webhooks[svix_id] = now
    if len(_processed_webhooks) > _MAX_WEBHOOK_CACHE:
        _processed_webhooks.popitem(last=False)
    return False


# ─── Webhook helpers ──────────────────────────────────────────────────────────

def _verify_webhook_signature(payload: bytes, svix_id: str, svix_timestamp: str, svix_signature: str) -> bool:
    secret = settings.CLERK_WEBHOOK_SECRET
    if not secret:
        return False
    signed_content = f"{svix_id}.{svix_timestamp}.{payload.decode()}".encode()
    expected = hmac.new(secret.encode(), signed_content, hashlib.sha256).hexdigest()
    for sig in svix_signature.split():
        if sig.startswith("v1,"):
            parts = sig.split(",")
            if len(parts) >= 2 and hmac.compare_digest(parts[1], expected):
                return True
    return False


@router.post("/clerk-webhook")
async def clerk_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    svix_id = request.headers.get("svix-id", "")
    svix_timestamp = request.headers.get("svix-timestamp", "")
    svix_signature = request.headers.get("svix-signature", "")
    body = await request.body()

    if settings.CLERK_WEBHOOK_SECRET and not _verify_webhook_signature(body, svix_id, svix_timestamp, svix_signature):
        raise HTTPException(status_code=401, detail=_t("auth.webhook_signature_invalid"))

    if svix_id and _is_duplicate_webhook(svix_id):
        logger.debug("clerk_webhook.duplicate_event svix_id=%s", svix_id)
        return {"status": "ok", "action": "duplicate"}

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail=_t("auth.webhook_invalid_json"))

    event_type = event.get("type", "")
    data = event.get("data", {})

    if event_type == "user.created":
        clerk_id = data.get("id")
        email = data.get("email_addresses", [{}])[0].get("email_address", "")
        full_name = data.get("first_name", "") or ""
        if data.get("last_name"):
            full_name = f"{full_name} {data['last_name']}".strip()

        existing = await db.execute(
            select(User).where(User.clerk_id == clerk_id)
        )
        if existing.scalar_one_or_none():
            logger.warning("clerk_webhook.duplicate user=%s", clerk_id)
            return {"status": "ok", "action": "duplicate"}

        existing_email = await db.execute(
            select(User).where(User.email == email)
        )
        existing_user = existing_email.scalar_one_or_none()
        if existing_user:
            existing_user.clerk_id = clerk_id
            existing_user.email_verified = True
            if full_name:
                existing_user.full_name = full_name
            await db.flush()
            logger.info("clerk_webhook.linked_legacy user=%s email=%s", clerk_id, email)
            return {"status": "ok", "action": "linked_legacy"}

        user = User(
            clerk_id=clerk_id,
            email=email or f"{clerk_id}@placeholder.local",
            hashed_password="",
            full_name=full_name or "Unknown",
            email_verified=True,
        )
        db.add(user)
        try:
            await db.flush()
        except Exception:
            await db.rollback()
            logger.error("clerk_webhook.create_failed user=%s email=%s", clerk_id, email)
            return {"status": "ok", "action": "create_failed"}
        await ensure_wallet(db, user.id)
        await db.flush()
        logger.info("clerk_webhook.created user=%s email=%s", clerk_id, email)
        return {"status": "ok", "action": "created"}

    elif event_type == "user.updated":
        clerk_id = data.get("id")
        email = data.get("email_addresses", [{}])[0].get("email_address", "")
        full_name = data.get("first_name", "") or ""
        if data.get("last_name"):
            full_name = f"{full_name} {data['last_name']}".strip()

        result = await db.execute(select(User).where(User.clerk_id == clerk_id))
        user = result.scalar_one_or_none()
        if user:
            if email:
                user.email = email
            if full_name:
                user.full_name = full_name
            await db.flush()
            logger.info("clerk_webhook.updated user=%s", clerk_id)
        return {"status": "ok", "action": "updated" if user else "not_found"}

    elif event_type == "user.deleted":
        clerk_id = data.get("id")
        result = await db.execute(select(User).where(User.clerk_id == clerk_id))
        user = result.scalar_one_or_none()
        if user:
            user.is_active = False
            await db.flush()
            logger.info("clerk_webhook.deactivated user=%s", clerk_id)
        return {"status": "ok", "action": "deactivated" if user else "not_found"}

    logger.debug("clerk_webhook.ignored type=%s", event_type)
    return {"status": "ok", "action": "ignored"}


# ─── User info ────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserOut)
async def me(current_user: CurrentUser):
    return current_user


@router.patch("/profile", response_model=UserOut)
async def update_profile(
    body: UpdateProfileRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    if body.full_name is not None:
        current_user.full_name = body.full_name
    await db.flush()
    return current_user
