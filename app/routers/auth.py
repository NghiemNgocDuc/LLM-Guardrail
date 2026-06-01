"""
Auth endpoints:
  POST /auth/signup              — create user (+ optional org), send verification email
  POST /auth/login               — get tokens (requires verified email when enabled)
  POST /auth/refresh             — swap refresh token → new access token
  GET  /auth/me                  — current user info
  POST /auth/verify-email        — confirm email from link token
  POST /auth/resend-verification — resend verification email
  POST /auth/forgot-password     — send password reset email
  POST /auth/reset-password      — set new password from reset token
"""
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.deps import (
    CurrentUser, create_access_token, create_refresh_token,
    decode_token, hash_password, verify_password,
)
from app.models import Organization, OrgPolicy, User
from app.schemas import (
    EmailRequest,
    LoginRequest,
    MessageResponse,
    ResetPasswordRequest,
    SignupRequest,
    SignupResponse,
    TokenResponse,
    UserOut,
    VerifyEmailRequest,
)
from app.config import get_settings
from app.services.auth_tokens import (
    TOKEN_PURPOSE_RESET,
    TOKEN_PURPOSE_VERIFY,
    build_action_url,
    consume_auth_token,
    create_auth_token,
)
from app.services.email import send_password_reset_email, send_verification_email

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])

_DEFAULT_INPUT_RULES = {
    "block_secrets": True,
    "block_pii": True,
    "pii_patterns": [
        {"name": "credit_card", "regex": r"\b(?:\d[ -]?){13,16}\b"},
        {"name": "ssn",         "regex": r"\b\d{3}-\d{2}-\d{4}\b"},
        {"name": "email",       "regex": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"},
    ],
    "block_prompt_injection": True,
    "injection_keywords": [
        "ignore previous instructions",
        "disregard your system prompt",
        "forget everything",
        "reveal your system prompt",
        "print your hidden instructions",
        "bypass the policy",
        "disable safety",
    ],
    "block_jailbreak": True,
    "jailbreak_patterns": [
        "DAN mode",
        "developer mode",
        "pretend you have no restrictions",
        "act as an unrestricted ai",
        "you are now jailbroken",
    ],
}
_DEFAULT_OUTPUT_RULES = {
    "enforce_schema": False,
    "block_toxic_content": True,
    "required_fields": [],
}
_DEFAULT_TOPIC_POLICY = {"blocked_topics": ["competitor products", "medical advice"]}
_DEFAULT_COMPLIANCE   = {"block_medical_advice": True, "never_discuss_competitors": True}


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]


async def _issue_verification_email(db: AsyncSession, user: User) -> None:
    if not settings.REQUIRE_EMAIL_VERIFICATION:
        user.email_verified = True
        await db.flush()
        return

    raw = await create_auth_token(
        db,
        user_id=user.id,
        purpose=TOKEN_PURPOSE_VERIFY,
        expire_hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS,
    )
    verify_url = build_action_url(settings.PUBLIC_APP_URL, "/verify-email", raw)
    await send_verification_email(user.email, verify_url)
    if not settings.smtp_configured:
        logger.warning("email.verification_link user=%s url=%s", user.email, verify_url)


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)):
    if settings.DEMO_MODE and settings.DEMO_DISABLE_SIGNUPS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo mode is using a fixed demo account; public signup is disabled.",
        )

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    org = None
    if body.org_name:
        slug = _slugify(body.org_name)
        existing_org = await db.execute(select(Organization).where(Organization.slug == slug))
        if existing_org.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Organization name already taken")
        org = Organization(name=body.org_name, slug=slug)
        db.add(org)
        await db.flush()

        policy = OrgPolicy(
            org_id=org.id,
            input_rules=_DEFAULT_INPUT_RULES,
            output_rules=_DEFAULT_OUTPUT_RULES,
            topic_policy=_DEFAULT_TOPIC_POLICY,
            compliance_rules=_DEFAULT_COMPLIANCE,
        )
        db.add(policy)

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        is_admin=bool(body.org_name),
        org_id=org.id if org else None,
        email_verified=not settings.REQUIRE_EMAIL_VERIFICATION,
    )
    db.add(user)
    await db.flush()

    await _issue_verification_email(db, user)

    if settings.REQUIRE_EMAIL_VERIFICATION:
        message = "Account created. Check your email to confirm your address before signing in."
    else:
        message = "Account created. You can sign in now."

    return SignupResponse(
        message=message,
        email=user.email,
        verification_required=settings.REQUIRE_EMAIL_VERIFICATION,
    )


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    user = await consume_auth_token(db, raw_token=body.token, purpose=TOKEN_PURPOSE_VERIFY)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    user.email_verified = True
    await db.flush()
    return MessageResponse(message="Email confirmed. You can sign in now.")


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(body: EmailRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Do not reveal whether the email exists.
    if user and not user.email_verified:
        await _issue_verification_email(db, user)

    return MessageResponse(
        message="If that account exists and is unverified, a new confirmation email was sent."
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(body: EmailRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user and user.is_active:
        raw = await create_auth_token(
            db,
            user_id=user.id,
            purpose=TOKEN_PURPOSE_RESET,
            expire_hours=settings.PASSWORD_RESET_EXPIRE_HOURS,
        )
        reset_url = build_action_url(settings.PUBLIC_APP_URL, "/reset-password", raw)
        await send_password_reset_email(user.email, reset_url)
        if not settings.smtp_configured:
            logger.warning("email.password_reset_link user=%s url=%s", user.email, reset_url)

    return MessageResponse(
        message="If that account exists, a password reset email was sent."
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    user = await consume_auth_token(db, raw_token=body.token, purpose=TOKEN_PURPOSE_RESET)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user.hashed_password = hash_password(body.new_password)
    user.email_verified = True
    await db.flush()
    return MessageResponse(message="Password updated. You can sign in with your new password.")


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user: User | None = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    if settings.REQUIRE_EMAIL_VERIFICATION and not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Check your inbox or request a new confirmation email.",
        )

    user.last_login = datetime.now(timezone.utc)

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(refresh_token: str, db: AsyncSession = Depends(get_db)):
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = await db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    if settings.REQUIRE_EMAIL_VERIFICATION and not user.email_verified:
        raise HTTPException(status_code=403, detail="Email not verified")
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: CurrentUser):
    return current_user
