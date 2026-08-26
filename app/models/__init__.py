"""
Database models.

Relationships:
  User  ──belongs to──  Organization
  Org   ──has one──────  OrgPolicy       (per-tenant guardrail rules)
  User  ──has many──────  APIKey
  APIKey ──has many─────  RequestLog      (full audit trail)
"""
import secrets
import uuid
from datetime import date, datetime, timezone

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

    # Optional org-authored custom input rule in Rego, evaluated by the OPA
    # sidecar (docker-compose `opa` service) after the standard input checks
    # as the FINAL gate. Fail-closed: if OPA is unreachable the request is
    # blocked. See guardrails/opa.py for the policy contract.
    custom_rule_rego: Mapped[str | None] = mapped_column(Text, nullable=True)

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
    feedback: Mapped["ChatFeedback | None"] = relationship("ChatFeedback", back_populates="request_log", uselist=False, cascade="all, delete-orphan")


# ─────────────────────────────────────────────────────────────────────────────
# ChatFeedback  (thumbs up/down on individual chat responses)
# ─────────────────────────────────────────────────────────────────────────────

class ChatFeedback(Base):
    __tablename__ = "chat_feedback"

    request_log_id: Mapped[str] = mapped_column(ForeignKey("request_logs.id", ondelete="CASCADE"), primary_key=True)
    user_id:        Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rating:         Mapped[int] = mapped_column(Integer, nullable=False)  # 1 = thumbs up, -1 = thumbs down
    comment:        Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at:     Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    request_log: Mapped["RequestLog"] = relationship("RequestLog", back_populates="feedback")


# ─────────────────────────────────────────────────────────────────────────────
# Memory  (user/org long-term memory — Mem0 + OpenAI style)
# ─────────────────────────────────────────────────────────────────────────────

class Memory(Base):
    """Long-term memory — extracted from chats, skills, or manual entries.

    Design copied from Mem0 + OpenAI Memory + Linear:
      - categories like Mem0 (fact / preference / procedure / persona / goal)
      - confidence + importance like Mem0 graph
      - Pinecone embedding for semantic recall (vectorstore.py, namespace 'memories')
      - Linear-style UX: pin, archive, search, timeline
    """
    __tablename__ = "memories"

    id:          Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id:     Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    org_id:      Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)

    title:       Mapped[str] = mapped_column(String(160), nullable=False)
    content:     Mapped[str] = mapped_column(Text, nullable=False)
    category:    Mapped[str] = mapped_column(String(24), default="fact", index=True)  # fact|preference|procedure|persona|goal|skill
    kind:        Mapped[str] = mapped_column(String(16), default="user", index=True)  # user|org|agent
    confidence:  Mapped[float] = mapped_column(default=0.82)
    importance:  Mapped[int] = mapped_column(Integer, default=3)  # 1-5
    pinned:      Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    archived:    Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    source_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # chat|manual|skill|import
    source_id:   Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at:     Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at:     Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, index=True)
    last_accessed:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", backref="memories")
    org:  Mapped["Organization | None"] = relationship("Organization", backref="memories")


# ─────────────────────────────────────────────────────────────────────────────
# Analytics materialized views (alembic/versions/...0011_analytics_views.py)
#
# Read-model tables refreshed on a schedule by
# scripts/refresh_analytics_views.py (REFRESH MATERIALIZED VIEW CONCURRENTLY).
# They are kept in sync with request_logs / chat_feedback only as of the last
# refresh — endpoints reading them document the staleness window. No FK
# constraints (materialized views cannot have them); the columns mirror the
# base tables exactly.
# ─────────────────────────────────────────────────────────────────────────────

class MvBlockedReasonsDaily(Base):
    """Per-org, per-day blocked-request counts by fired rule.

    Unique key (org_id, day, fired_rule) doubles as the query index for the
    /analytics/top-blocked-reasons endpoint.
    """
    __tablename__ = "mv_blocked_reasons_daily"

    org_id:           Mapped[str] = mapped_column(primary_key=True)
    day:              Mapped[date] = mapped_column(primary_key=True)
    fired_rule:       Mapped[str] = mapped_column(primary_key=True)
    cnt:              Mapped[int] = mapped_column(Integer)
    last_occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MvFalsePositiveCandidatesDaily(Base):
    """Per-org, per-day disputed blocks: blocked request + thumbs-up feedback
    OR the fired rule in the owner's always-allow overrides. Unique on
    request_log_id so REFRESH ... CONCURRENTLY is allowed.
    """
    __tablename__ = "mv_false_positive_candidates_daily"

    request_log_id:    Mapped[str] = mapped_column(primary_key=True)
    org_id:            Mapped[str] = mapped_column(index=True)
    day:               Mapped[date] = mapped_column(index=True)
    fired_rule:        Mapped[str] = mapped_column(String)
    status:            Mapped[str] = mapped_column(String)
    prompt_preview:    Mapped[str | None] = mapped_column(Text)
    created_at:        Mapped[datetime] = mapped_column(DateTime(timezone=True))
    positive_feedback: Mapped[bool] = mapped_column(Boolean)
    override_hit:      Mapped[bool] = mapped_column(Boolean)
