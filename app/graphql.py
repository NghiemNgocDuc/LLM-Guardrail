"""Read-only GraphQL analytics layer, mounted at /graphql (see main.py).

Mirrors the analytics REST endpoints 1:1 by delegating to the same router
functions (app/routers/analytics.py) â€” same org scoping, same filters, same
materialized-view semantics. Queries are read-only; mutations are intentionally
not exposed.

GraphQL surface:
  dashboard(days: 30)
  topBlockedReasons(days: 7, limit: 10)
  requestLogs(page: 1, pageSize: 25, status, keyword, dateFrom, dateTo, backend)
  falsePositiveCandidates(days: 7, limit: 50)

Deliberate gap vs REST: GET /analytics/export stays REST-only â€” GraphQL has no
file-download semantics, and the CSV path is tested as a unit.

Auth: identical to the REST routes â€” the Authorization bearer token is
verified through app.deps.get_current_user (Clerk JWT via JWKS/PEM, or local
JWT), and results are scoped to the caller's org. full_prompt is never
exposed, exactly like /analytics/logs.

Sessions: opened per resolver (the pattern chat.py's streaming endpoint and
the MCP server use) â€” auth uses a short-lived session for the token lookup,
then the user's loaded id/org_id/is_active stay valid on the detached object.
"""
from contextlib import asynccontextmanager

import strawberry
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from strawberry.types import Info

from app.database import get_sessionmaker
from app.deps import get_current_user
from app.i18n import _t
from app.routers import analytics as analytics_router


# â”€â”€ Types (mirror the REST response models / dict shapes) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@strawberry.type
class RequestLogType:
    id: str
    status: str
    prompt_preview: str
    model: str
    backend: str
    latency_ms: int
    input_passed: bool
    output_passed: bool | None
    input_block_reason: str | None
    output_block_reason: str | None
    fired_rule: str | None
    input_tokens: int
    output_tokens: int
    created_at: str


@strawberry.type
class TopBlockedReasonType:
    fired_rule: str
    count: int
    last_occurred_at: str | None


@strawberry.type
class FalsePositiveExampleType:
    id: str
    status: str
    prompt_preview: str
    created_at: str
    positive_feedback: bool
    override_hit: bool


@strawberry.type
class FalsePositiveRuleType:
    fired_rule: str
    count: int
    examples: list[FalsePositiveExampleType]


@strawberry.type
class SummaryType:
    total_requests: int
    delivered: int
    input_blocked: int
    output_blocked: int
    rate_limited: int
    error_count: int
    block_rate_pct: float
    avg_latency_ms: float
    total_tokens: int
    estimated_cost_usd: float


@strawberry.type
class TimeSeriesPointType:
    ts: str
    total: int
    delivered: int
    blocked: int


@strawberry.type
class TopFiredRuleType:
    rule: str
    count: int


@strawberry.type
class ProviderUsageType:
    backend: str
    model: str
    count: int
    tokens: int


@strawberry.type
class RecentSuspiciousType:
    id: str
    status: str
    prompt_preview: str
    backend: str
    fired_rule: str | None
    reason: str | None
    created_at: str


@strawberry.type
class RecentLogType:
    id: str
    status: str
    prompt_preview: str
    model: str
    backend: str
    latency_ms: int
    fired_rule: str | None
    created_at: str


@strawberry.type
class DashboardType:
    summary: SummaryType
    time_series: list[TimeSeriesPointType]
    top_rules: list[TopFiredRuleType]
    provider_usage: list[ProviderUsageType]
    recent_suspicious: list[RecentSuspiciousType]
    recent_logs: list[RecentLogType]


# â”€â”€ Session plumbing (per-resolver, like chat.py streaming) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@asynccontextmanager
async def _open_session():
    maker = get_sessionmaker()
    async with maker() as db:
        yield db


# â”€â”€ Auth â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def get_graphql_context(request, response) -> dict:
    """Verify the bearer token exactly like the REST routes and expose the
    authenticated user to resolvers. 401s bubble up as HTTP errors."""
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail=_t("auth.token_missing"))
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=auth.split(" ", 1)[1].strip()
    )
    async with _open_session() as db:
        user = await get_current_user(credentials, db)
    return {"request": request, "response": response, "user": user}


# â”€â”€ Queries (delegate to the REST routers â€” single source of truth) â”€â”€â”€â”€â”€â”€â”€â”€

@strawberry.type
class Query:
    @strawberry.field
    async def dashboard(self, info: Info, days: int = 30) -> DashboardType:
        async with _open_session() as db:
            data = await analytics_router.dashboard(
                info.context["user"], days=days, db=db
            )
        return DashboardType(
            summary=SummaryType(**data.summary.model_dump()),
            time_series=[TimeSeriesPointType(**p.model_dump()) for p in data.time_series],
            top_rules=[TopFiredRuleType(**r.model_dump()) for r in data.top_rules],
            provider_usage=[ProviderUsageType(**p.model_dump()) for p in data.provider_usage],
            recent_suspicious=[RecentSuspiciousType(**r) for r in data.recent_suspicious],
            recent_logs=[RecentLogType(**r) for r in data.recent_logs],
        )

    @strawberry.field
    async def top_blocked_reasons(
        self, info: Info, days: int = 7, limit: int = 10
    ) -> list[TopBlockedReasonType]:
        async with _open_session() as db:
            rows = await analytics_router.top_blocked_reasons(
                info.context["user"], days=days, limit=limit, db=db
            )
        return [
            TopBlockedReasonType(
                fired_rule=r.fired_rule,
                count=r.count,
                last_occurred_at=r.last_occurred_at.isoformat()
                if r.last_occurred_at else None,
            )
            for r in rows
        ]

    @strawberry.field
    async def request_logs(
        self,
        info: Info,
        page: int = 1,
        page_size: int = 25,
        status: str | None = None,
        keyword: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        backend: str | None = None,
    ) -> list[RequestLogType]:
        async with _open_session() as db:
            result = await analytics_router.logs(
                info.context["user"],
                page=page,
                page_size=page_size,
                status_filter=status,
                keyword=keyword,
                date_from=date_from,
                date_to=date_to,
                backend_filter=backend,
                db=db,
            )
        # request_id duplicates id; full_prompt is deliberately never exposed
        # (mirrors /analytics/logs, where the client always sees None).
        drop = {"request_id", "full_prompt"}
        return [
            RequestLogType(**{k: v for k, v in item.items() if k not in drop})
            for item in result["items"]
        ]

    @strawberry.field
    async def false_positive_candidates(
        self, info: Info, days: int = 7, limit: int = 50
    ) -> list[FalsePositiveRuleType]:
        async with _open_session() as db:
            rows = await analytics_router.false_positive_candidates(
                info.context["user"], days=days, limit=limit, db=db
            )
        return [
            FalsePositiveRuleType(
                fired_rule=r["fired_rule"],
                count=r["count"],
                examples=[
                    FalsePositiveExampleType(**ex) for ex in r["examples"]
                ],
            )
            for r in rows
        ]


schema = strawberry.Schema(query=Query)
