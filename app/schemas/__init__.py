"""
Pydantic v2 schemas — request/response shapes for every router.
"""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, EmailStr, Field, model_validator


# ─── Auth ─────────────────────────────────────────────────────────────────────

class UpdateProfileRequest(BaseModel):
    model_config = {"extra": "forbid"}
    full_name: str | None = Field(default=None, min_length=1, max_length=120)


class BulkUserAction(BaseModel):
    model_config = {"extra": "forbid"}
    action: str = Field(description="enable | disable | remove")
    user_ids: list[str] = Field(min_length=1)


class AdminUserStats(BaseModel):
    id: str
    email: str
    full_name: str
    is_admin: bool
    is_active: bool
    last_login: datetime | None
    tokens_balance: int
    tokens_used: int
    total_requests: int
    total_blocked: int


class MessageResponse(BaseModel):
    message: str


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
    model_config = {"extra": "forbid"}
    name: str = Field(min_length=1, max_length=80)
    expires_at: datetime | None = None
    scopes: list[str] = ["chat"]


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
    scopes: list[str] = ["chat"]

    model_config = {"from_attributes": True}


class APIKeyCreated(APIKeyOut):
    """Returned only once at creation — includes the raw key."""
    raw_key: str


class AdminInviteUser(BaseModel):
    model_config = {"extra": "forbid"}
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    is_admin: bool = False

class AdminUserUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    is_active: bool | None = None
    is_admin: bool | None = None


# ─── Organization & Policy ────────────────────────────────────────────────────

class OrgOut(BaseModel):
    id: str
    name: str
    slug: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RotatedWebhookSecret(BaseModel):
    """New webhook signing secret — only ever returned to the caller once."""
    webhook_secret: str
    created_at: datetime


class PolicyUpdate(BaseModel):
    """Partial update — only send what you want to change."""
    model_config = {"extra": "forbid"}
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
    model_config = {"extra": "forbid"}
    plan_slug: str = Field(min_length=1, max_length=32)


class BillingCheckoutResponse(BaseModel):
    checkout_url: str | None = None
    purchase_id: str | None = None
    message: str | None = None


# ─── Chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    model_config = {"extra": "forbid"}
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


class FeedbackRequest(BaseModel):
    model_config = {"extra": "forbid"}
    rating: int = Field(..., ge=-1, le=1, description="1 = thumbs up, -1 = thumbs down, 0 = neutral")
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackOut(BaseModel):
    request_log_id: str
    rating: int
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


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
    model_config = {"extra": "forbid"}
    session_allow_keys: list[str] = Field(default_factory=list)
    always_allow_keys: list[str] = Field(default_factory=list)
    always_allow_reason_codes: list[str] = Field(default_factory=list)


class SkillScanRequest(BaseModel):
    model_config = {"extra": "forbid"}
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
    model_config = {"extra": "forbid"}
    filename: str | None = None
    source: str = Field(default="git_push", max_length=32)
    rejection_summary: str | None = None
    content_preview: str | None = Field(default=None, max_length=500)
    findings: list[SkillFindingOut] = Field(min_length=1)


class SkillRejectionCreateIn(BaseModel):
    model_config = {"extra": "forbid"}
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
    model_config = {"extra": "forbid"}
    action: str = Field(description="allow_once | allow_always | keep_rejected")
    note: str | None = Field(default=None, max_length=2000)


# ─── Analytics ────────────────────────────────────────────────────────────────

class UsageSummary(BaseModel):
    total_requests:      int
    delivered:           int
    input_blocked:       int
    output_blocked:      int
    rate_limited:        int = 0
    error_count:         int
    block_rate_pct:      float
    avg_latency_ms:      float
    total_tokens:        int
    estimated_cost_usd:  float = 0.0


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


class TopBlockedReason(BaseModel):
    fired_rule:       str
    count:            int
    last_occurred_at: datetime


# ─── Policy diff ──────────────────────────────────────────────────────────────

class PolicyDiffRequest(BaseModel):
    model_config = {"extra": "forbid"}
    policy_a: dict[str, Any]
    policy_b: dict[str, Any]


class PolicyDiffEntry(BaseModel):
    field:  str
    before: Any | None = None
    after:  Any | None = None


# ─── Admin replay (dry-run stored request against current policy) ─────────────

class ReplayOriginalVerdict(BaseModel):
    passed: bool
    status: str
    reason: str | None = None


class ReplayCurrentVerdict(BaseModel):
    passed:      bool
    check:       str
    reason:      str | None = None
    reason_code: str = "clean"
    risk_score:  float = 0.0


class ReplayResponse(BaseModel):
    request_id:           str
    original:             ReplayOriginalVerdict
    current:              ReplayCurrentVerdict
    would_change_outcome: bool
    note:                 str
