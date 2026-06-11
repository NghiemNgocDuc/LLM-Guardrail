"""
Pydantic v2 schemas — request/response shapes for every router.
"""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, EmailStr, Field, model_validator


# ─── Auth ─────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    org_name: str | None = None      # if provided, creates an org and makes this user admin


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class EmailRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=16, max_length=256)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)


class MessageResponse(BaseModel):
    message: str


class SignupResponse(BaseModel):
    message: str
    email: str
    verification_required: bool = True


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int                  # seconds


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    is_admin: bool
    is_active: bool = True
    email_verified: bool = False
    org_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── API Keys ─────────────────────────────────────────────────────────────────

class APIKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    expires_at: datetime | None = None


class APIKeyOut(BaseModel):
    id: str
    name: str
    key_prefix: str
    is_active: bool
    total_requests: int
    total_blocked: int
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None

    model_config = {"from_attributes": True}


class APIKeyCreated(APIKeyOut):
    """Returned only once at creation — includes the raw key."""
    raw_key: str


class AdminInviteUser(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    is_admin: bool = False

class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None


# ─── Organization & Policy ────────────────────────────────────────────────────

class OrgOut(BaseModel):
    id: str
    name: str
    slug: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PolicyUpdate(BaseModel):
    """Partial update — only send what you want to change."""
    input_rules:      dict[str, Any] | None = None
    output_rules:     dict[str, Any] | None = None
    topic_policy:     dict[str, Any] | None = None
    compliance_rules: dict[str, Any] | None = None
    llm_backend:      str | None = None
    llm_model:        str | None = None
    rate_limit_rpm:   int | None = None
    rate_limit_rpd:   int | None = None


class PolicyOut(PolicyUpdate):
    org_id: str
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Billing (token packs) ────────────────────────────────────────────────────

class BillingConfigOut(BaseModel):
    billing_enabled: bool
    free_signup_tokens: int
    stripe_configured: bool
    stripe_publishable_key: str | None = None


class BillingPlanOut(BaseModel):
    slug: str
    name: str
    tokens: int
    price_cents: int
    currency: str
    description: str
    popular: bool = False
    price_display: str


class BillingWalletOut(BaseModel):
    balance_tokens: int
    tokens_used_lifetime: int
    tokens_purchased_lifetime: int
    billing_enabled: bool
    unlimited: bool = False


class BillingPurchaseOut(BaseModel):
    id: str
    plan_slug: str
    tokens_granted: int
    amount_cents: int
    currency: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None


class BillingCheckoutRequest(BaseModel):
    plan_slug: str = Field(min_length=1, max_length=32)


class BillingCheckoutResponse(BaseModel):
    checkout_url: str | None = None
    purchase_id: str | None = None
    message: str | None = None


# ─── Chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=32_000)
    model: str | None = None        # overrides org default if provided
    backend: str | None = None      # "openai" | "anthropic" | "gemini" | "ollama" | "groq"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=8192)


class GuardrailResult(BaseModel):
    passed: bool
    check:  str
    reason: str
    reason_code: str = "clean"
    risk_score: float = 0.0


class ChatResponse(BaseModel):
    request_id:    str
    response:      str | None        # None if blocked
    status:        str               # "delivered" | "input_blocked" | "output_blocked" | "error"
    input_guard:   GuardrailResult
    output_guard:  GuardrailResult | None
    latency_ms:    int
    model:         str
    backend:       str
    tokens_remaining: int | None = None


# ─── Agent skill scan ─────────────────────────────────────────────────────────

class SkillOverridesIn(BaseModel):
    session_allow_keys: list[str] = Field(default_factory=list)
    always_allow_keys: list[str] = Field(default_factory=list)
    always_allow_reason_codes: list[str] = Field(default_factory=list)


class SkillScanRequest(BaseModel):
    content: str = Field(min_length=1, max_length=256_000)
    filename: str | None = Field(default=None, max_length=255)
    overrides: SkillOverridesIn | None = None


class SkillFindingOut(BaseModel):
    finding_key: str
    category: str
    severity: str
    check: str
    reason: str
    reason_code: str
    explanation: str
    line_number: int | None = None
    snippet: str = ""
    risk_score: float = 0.0
    allowed_by_override: bool = False


class SkillScanResponse(BaseModel):
    safe: bool
    risk_score: float
    findings: list[SkillFindingOut]
    line_count: int
    char_count: int
    filename: str | None = None
    blocked: bool = False
    agent_may_continue: bool = True
    agent_status: str = "ok"
    rejection_summary: str | None = None
    blocking_findings: list[SkillFindingOut] = Field(default_factory=list)
    overridden_findings: list[SkillFindingOut] = Field(default_factory=list)
    rejection_id: str | None = None


class SkillRejectionReportIn(BaseModel):
    filename: str | None = None
    source: str = Field(default="git_push", max_length=32)
    rejection_summary: str | None = None
    content_preview: str | None = Field(default=None, max_length=500)
    findings: list[SkillFindingOut] = Field(min_length=1)


class SkillRejectionCreateIn(BaseModel):
    content: str = Field(min_length=1, max_length=256_000)
    filename: str | None = Field(default=None, max_length=255)
    source: str = Field(default="web_manual", max_length=32)
    rejection_summary: str | None = None
    content_preview: str | None = Field(default=None, max_length=500)


class SkillRejectionOut(BaseModel):
    id: str
    filename: str | None
    source: str
    status: str
    findings: list[dict]
    rejection_summary: str
    content_preview: str | None
    resolved_action: str | None
    resolver_note: str | None
    created_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}


class SkillRejectionResolveIn(BaseModel):
    action: str = Field(description="allow_once | allow_always | keep_rejected")
    note: str | None = Field(default=None, max_length=2000)


# ─── Analytics ────────────────────────────────────────────────────────────────

class UsageSummary(BaseModel):
    total_requests:     int
    delivered:          int
    input_blocked:      int
    output_blocked:     int
    rate_limited:       int = 0
    error_count:        int
    block_rate_pct:     float
    avg_latency_ms:     float
    total_tokens:       int


class TimeSeriesPoint(BaseModel):
    ts:            str       # ISO date string (day bucket)
    total:         int
    delivered:     int
    blocked:       int


class TopFiredRule(BaseModel):
    rule:  str
    count: int


class ProviderUsage(BaseModel):
    backend: str
    model: str
    count: int
    tokens: int


class AnalyticsDashboard(BaseModel):
    summary:      UsageSummary
    time_series:  list[TimeSeriesPoint]
    top_rules:    list[TopFiredRule]
    provider_usage: list[ProviderUsage] = []
    recent_suspicious: list[dict] = []
    recent_logs:  list[dict]
