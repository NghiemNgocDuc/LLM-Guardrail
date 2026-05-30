"""
Auth endpoints:
  POST /auth/signup   — create user (+ optional org)
  POST /auth/login    — get tokens
  POST /auth/refresh  — swap refresh token → new access token
  GET  /auth/me       — current user info
"""
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
from app.schemas import LoginRequest, SignupRequest, TokenResponse, UserOut
from app.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["Auth"])

_DEFAULT_INPUT_RULES = {
    "block_pii": True,
    "pii_patterns": [
        {"name": "credit_card", "regex": r"\b(?:\d[ -]?){13,16}\b"},
        {"name": "ssn",         "regex": r"\b\d{3}-\d{2}-\d{4}\b"},
        {"name": "email",       "regex": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"},
    ],
    "block_prompt_injection": True,
    "injection_keywords": ["ignore previous instructions", "disregard your system prompt", "forget everything"],
    "block_jailbreak": True,
    "jailbreak_patterns": ["DAN mode", "developer mode", "pretend you have no restrictions"],
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


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)):
    if settings.DEMO_MODE and settings.DEMO_DISABLE_SIGNUPS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo mode is using a fixed demo account; public signup is disabled.",
        )

    # Check email uniqueness
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
        await db.flush()   # get org.id

        # Seed default policy for this org
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
        is_admin=bool(body.org_name),   # org creator = admin
        org_id=org.id if org else None,
    )
    db.add(user)
    await db.flush()
    return user


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user: User | None = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

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
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: CurrentUser):
    return current_user
