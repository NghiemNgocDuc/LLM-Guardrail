"""
Database models.

Relationships:
  User  ──belongs to──▶  Organization
  Org   ──has one──────▶  OrgPolicy       (per-tenant guardrail rules)
  User  ──has many──────▶  APIKey
  APIKey ──has many─────▶  RequestLog      (full audit trail)
"""
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey,
    Integer, String, Text, JSON, BigInteger, Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Organization  (one per team / company)
# ─────────────────────────────────────────────────────────────────────────────

class Organization(Base):
    __tablename__ = "organizations"

    id:         Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name:       Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    slug:       Mapped[str] = mapped_column(String(60),  unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    users:   Mapped[list["User"]]      = relationship("User",      back_populates="org")
    policy:  Mapped["OrgPolicy"]       = relationship("OrgPolicy", back_populates="org", uselist=False, cascade="all, delete-orphan")
    api_keys: Mapped[list["APIKey"]]   = relationship("APIKey",    back_populates="org")


# ─────────────────────────────────────────────────────────────────────────────
# OrgPolicy  (per-tenant guardrail config stored as JSON)
# ─────────────────────────────────────────────────────────────────────────────

class OrgPolicy(Base):
    __tablename__ = "org_policies"

    id:     Mapped[str]  = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str]  = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), unique=True)

    # Stored as JSON so each organization can tune guardrails independently.
    input_rules:      Mapped[dict] = mapped_column(JSON, default=dict)
    output_rules:     Mapped[dict] = mapped_column(JSON, default=dict)
    topic_policy:     Mapped[dict] = mapped_column(JSON, default=dict)
    compliance_rules: Mapped[dict] = mapped_column(JSON, default=dict)

    # LLM backend override for this org ("openai", "anthropic", "ollama", or None = use default)
    llm_backend: Mapped[str | None] = mapped_column(String(32), nullable=True)
    llm_model:   Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Rate limits (override global defaults)
    rate_limit_rpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_limit_rpd: Mapped[int | None] = mapped_column(Integer, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    org: Mapped["Organization"] = relationship("Organization", back_populates="policy")


# ─────────────────────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id:             Mapped[str]  = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    clerk_id:       Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    email:          Mapped[str]  = mapped_column(String(254), unique=True, index=True, nullable=False)
    hashed_password:Mapped[str]  = mapped_column(String(256), nullable=False)
    full_name:      Mapped[str]  = mapped_column(String(120), nullable=False)
    is_active:      Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin:       Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    org_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    org:    Mapped["Organization"] = relationship("Organization", back_populates="users")

    api_keys: Mapped[list["APIKey"]] = relationship("APIKey", back_populates="owner", cascade="all, delete-orphan")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    auth_tokens: Mapped[list["AuthToken"]] = relationship(
        "AuthToken", back_populates="user", cascade="all, delete-orphan"
    )
    token_wallet: Mapped["TokenWallet | None"] = relationship(
        "TokenWallet", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    token_purchases: Mapped[list["TokenPurchase"]] = relationship(
        "TokenPurchase", back_populates="user", cascade="all, delete-orphan"
    )
    skill_rejections: Mapped[list["SkillAccessRejection"]] = relationship(
        "SkillAccessRejection", back_populates="user", cascade="all, delete-orphan"
    )
    skill_guard_overrides: Mapped["UserSkillGuardOverrides | None"] = relationship(
        "UserSkillGuardOverrides", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Skill Guard — rejected access queue (web review / unblock)
# ─────────────────────────────────────────────────────────────────────────────

class SkillAccessRejection(Base):
    __tablename__ = "skill_access_rejections"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="api_scan")  # api_scan | git_push | cli | report
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    # pending | unblocked_once | unblocked_always | kept_rejected
    findings: Mapped[list] = mapped_column(JSON, default=list)
    rejection_summary: Mapped[str] = mapped_column(Text, default="")
    content_preview: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resolved_action: Mapped[str | None] = mapped_column(String(24), nullable=True)
    resolver_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="skill_rejections")


class UserSkillGuardOverrides(Base):
    __tablename__ = "user_skill_guard_overrides"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    overrides: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="skill_guard_overrides")


# ─────────────────────────────────────────────────────────────────────────────
# Token billing (gateway usage)
# ─────────────────────────────────────────────────────────────────────────────

class TokenWallet(Base):
    __tablename__ = "token_wallets"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    balance_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    tokens_used_lifetime: Mapped[int] = mapped_column(BigInteger, default=0)
    tokens_purchased_lifetime: Mapped[int] = mapped_column(BigInteger, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="token_wallet")


class TokenPurchase(Base):
    __tablename__ = "token_purchases"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_slug: Mapped[str] = mapped_column(String(32), nullable=False)
    tokens_granted: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="usd")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | completed | failed
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="token_purchases")


# ─────────────────────────────────────────────────────────────────────────────
# AuthToken  (email verification + password reset)
# ─────────────────────────────────────────────────────────────────────────────

class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id:         Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id:    Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose:    Mapped[str] = mapped_column(String(32), nullable=False)  # verify_email | password_reset
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="auth_tokens")


# ─────────────────────────────────────────────────────────────────────────────
# APIKey
# ─────────────────────────────────────────────────────────────────────────────

class APIKey(Base):
    __tablename__ = "api_keys"

    id:          Mapped[str]  = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name:        Mapped[str]  = mapped_column(String(80), nullable=False)           # human label
    key_prefix:  Mapped[str]  = mapped_column(String(12), nullable=False)           # e.g. "grg_abc123" (shown in UI)
    key_hash:    Mapped[str]  = mapped_column(String(256), unique=True, nullable=False)  # bcrypt hash
    is_active:   Mapped[bool] = mapped_column(Boolean, default=True)

    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    org_id:   Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)

    owner: Mapped["User"]          = relationship("User",         back_populates="api_keys")
    org:   Mapped["Organization"]  = relationship("Organization", back_populates="api_keys")

    # Scopes granted to this key (e.g. ["chat", "analytics"])
    scopes: Mapped[list] = mapped_column(JSON, default=lambda: ["chat"])

    # Usage counters (updated on every request)
    total_requests:  Mapped[int] = mapped_column(BigInteger, default=0)
    total_blocked:   Mapped[int] = mapped_column(BigInteger, default=0)
    total_tokens:    Mapped[int] = mapped_column(BigInteger, default=0)

    created_at:  Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    logs: Mapped[list["RequestLog"]] = relationship("RequestLog", back_populates="api_key")

    @staticmethod
    def generate_raw_key() -> str:
        """Generate a raw key (shown once). Prefix + 32 random bytes."""
        return "grg_" + secrets.token_urlsafe(32)


# ─────────────────────────────────────────────────────────────────────────────
# RequestLog  (immutable audit trail — never update, only insert)
# ─────────────────────────────────────────────────────────────────────────────

class RequestLog(Base):
    __tablename__ = "request_logs"

    id:          Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    api_key_id:  Mapped[str] = mapped_column(ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True, index=True)
    org_id:      Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)

    # Request
    prompt_hash:    Mapped[str]      = mapped_column(String(64))    # SHA-256 of prompt (never store raw PII)
    prompt_preview: Mapped[str]      = mapped_column(String(120))   # first 120 chars, redacted if PII found
    full_prompt:    Mapped[str | None] = mapped_column(Text, nullable=True) # Optional full raw prompt
    model:          Mapped[str]      = mapped_column(String(80))
    backend:        Mapped[str]      = mapped_column(String(32))

    # Guardrail verdicts
    input_passed:    Mapped[bool]        = mapped_column(Boolean)
    input_block_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_passed:   Mapped[bool | None] = mapped_column(Boolean, nullable=True)   # None if input blocked
    output_block_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Which specific rule fired (for analytics)
    fired_rule: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Outcome
    status:          Mapped[str]   = mapped_column(String(20))   # "delivered" | "input_blocked" | "output_blocked" | "error"
    latency_ms:      Mapped[int]   = mapped_column(Integer)
    input_tokens:    Mapped[int]   = mapped_column(Integer, default=0)
    output_tokens:   Mapped[int]   = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    api_key: Mapped["APIKey"] = relationship("APIKey", back_populates="logs")
