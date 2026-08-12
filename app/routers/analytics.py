"""
Analytics endpoints (JWT-authenticated — dashboard use only):
  GET /analytics/dashboard   — full stats for current org
  GET /analytics/logs        — paginated request log
  GET /analytics/export      — download logs as CSV
"""
import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, case, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.pricing import estimate_cost_usd
from app.database import get_db
from app.deps import CurrentUser
from app.models import (
    APIKey, MvBlockedReasonsDaily, MvFalsePositiveCandidatesDaily,
    RequestLog, TokenWallet, User,
)
from app.schemas import (
    AnalyticsDashboard, ProviderUsage, TimeSeriesPoint, TopBlockedReason, TopFiredRule, UsageSummary,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/dashboard", response_model=AnalyticsDashboard)
async def dashboard(
    current_user: CurrentUser,
    days: int = Query(default=30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    org_id = current_user.org_id

    base_filter = [RequestLog.created_at >= since]
    if org_id:
        base_filter.append(RequestLog.org_id == org_id)

    # ── Summary stats ─────────────────────────────────────────────────────
    summary_q = await db.execute(
        select(
            func.count().label("total"),
            func.sum(case((RequestLog.status == "delivered",     1), else_=0)).label("delivered"),
            func.sum(case((RequestLog.status == "input_blocked", 1), else_=0)).label("input_blocked"),
            func.sum(case((RequestLog.status == "output_blocked",1), else_=0)).label("output_blocked"),
            func.sum(case((RequestLog.status == "rate_limited",  1), else_=0)).label("rate_limited"),
            func.sum(case((RequestLog.status == "error",         1), else_=0)).label("errors"),
            func.avg(RequestLog.latency_ms).label("avg_latency"),
            func.sum(RequestLog.input_tokens + RequestLog.output_tokens).label("total_tokens"),
        ).where(*base_filter)
    )
    row = summary_q.one()
    total = row.total or 0
    blocked = (row.input_blocked or 0) + (row.output_blocked or 0) + (row.rate_limited or 0)

    # ── Estimated cost (per provider/model) ──────────────────────────────
    cost_q = await db.execute(
        select(
            RequestLog.backend,
            RequestLog.model,
            func.sum(RequestLog.input_tokens + RequestLog.output_tokens).label("tokens"),
        )
        .where(*base_filter)
        .group_by(RequestLog.backend, RequestLog.model)
    )
    estimated_cost = sum(
        estimate_cost_usd(r.backend, r.model, r.tokens or 0)
        for r in cost_q.all()
    )

    summary = UsageSummary(
        total_requests=total,
        delivered=row.delivered or 0,
        input_blocked=row.input_blocked or 0,
        output_blocked=row.output_blocked or 0,
        rate_limited=row.rate_limited or 0,
        error_count=row.errors or 0,
        block_rate_pct=round(blocked / total * 100, 2) if total else 0.0,
        avg_latency_ms=round(row.avg_latency or 0, 1),
        total_tokens=row.total_tokens or 0,
        estimated_cost_usd=round(estimated_cost, 4),
    )

    # ── Time series (daily buckets) ───────────────────────────────────────
    ts_q = await db.execute(
        select(
            cast(RequestLog.created_at, Date).label("day"),
            func.count().label("total"),
            func.sum(case((RequestLog.status == "delivered",     1), else_=0)).label("delivered"),
            func.sum(case((RequestLog.status != "delivered",     1), else_=0)).label("blocked"),
        )
        .where(*base_filter)
        .group_by("day")
        .order_by("day")
    )
    time_series = [
        TimeSeriesPoint(ts=str(r.day), total=r.total, delivered=r.delivered, blocked=r.blocked)
        for r in ts_q.all()
    ]

    # ── Top fired rules ───────────────────────────────────────────────────
    rules_q = await db.execute(
        select(RequestLog.fired_rule, func.count().label("cnt"))
        .where(*base_filter, RequestLog.fired_rule.isnot(None))
        .group_by(RequestLog.fired_rule)
        .order_by(func.count().desc())
        .limit(10)
    )
    top_rules = [TopFiredRule(rule=r.fired_rule, count=r.cnt) for r in rules_q.all()]

    provider_q = await db.execute(
        select(
            RequestLog.backend,
            RequestLog.model,
            func.count().label("cnt"),
            func.sum(RequestLog.input_tokens + RequestLog.output_tokens).label("tokens"),
        )
        .where(*base_filter, RequestLog.status == "delivered")
        .group_by(RequestLog.backend, RequestLog.model)
        .order_by(func.count().desc())
        .limit(10)
    )
    provider_usage = [
        ProviderUsage(
            backend=r.backend,
            model=r.model,
            count=r.cnt,
            tokens=r.tokens or 0,
        )
        for r in provider_q.all()
    ]

    suspicious_q = await db.execute(
        select(RequestLog)
        .where(*base_filter, RequestLog.status != "delivered")
        .order_by(RequestLog.created_at.desc())
        .limit(10)
    )
    recent_suspicious = [
        {
            "id": log.id,
            "status": log.status,
            "prompt_preview": log.prompt_preview,
            "backend": log.backend,
            "fired_rule": log.fired_rule,
            "reason": log.input_block_reason or log.output_block_reason or log.fired_rule,
            "created_at": log.created_at.isoformat(),
        }
        for log in suspicious_q.scalars().all()
    ]

    # ── Recent logs ───────────────────────────────────────────────────────
    recent_q = await db.execute(
        select(RequestLog)
        .where(*base_filter)
        .order_by(RequestLog.created_at.desc())
        .limit(50)
    )
    recent_logs = [
        {
            "id":             log.id,
            "status":         log.status,
            "prompt_preview": log.prompt_preview,
            "model":          log.model,
            "backend":        log.backend,
            "latency_ms":     log.latency_ms,
            "fired_rule":     log.fired_rule,
            "created_at":     log.created_at.isoformat(),
        }
        for log in recent_q.scalars().all()
    ]

    return AnalyticsDashboard(
        summary=summary,
        time_series=time_series,
        top_rules=top_rules,
        provider_usage=provider_usage,
        recent_suspicious=recent_suspicious,
        recent_logs=recent_logs,
    )


@router.get("/top-blocked-reasons", response_model=list[TopBlockedReason])
async def top_blocked_reasons(
    current_user: CurrentUser,
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Most frequent fired rules among blocked requests, with the most recent occurrence of each.

    Backed by the mv_blocked_reasons_daily materialized view: counts are
    aggregated from the per-org per-day rows for the requested window. The
    view is refreshed on a schedule (scripts/refresh_analytics_views.py) —
    data can lag live request logs by up to one refresh interval.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    filters = [MvBlockedReasonsDaily.day >= since.date()]
    if current_user.org_id:
        filters.append(MvBlockedReasonsDaily.org_id == current_user.org_id)

    result = await db.execute(
        select(
            MvBlockedReasonsDaily.fired_rule,
            func.sum(MvBlockedReasonsDaily.cnt).label("cnt"),
            func.max(MvBlockedReasonsDaily.last_occurred_at).label("last_occurred_at"),
        )
        .where(*filters)
        .group_by(MvBlockedReasonsDaily.fired_rule)
        .order_by(func.sum(MvBlockedReasonsDaily.cnt).desc())
        .limit(limit)
    )
    return [
        TopBlockedReason(
            fired_rule=r.fired_rule,
            count=int(r.cnt),
            last_occurred_at=r.last_occurred_at,
        )
        for r in result.all()
    ]


@router.get("/users")
async def user_breakdown(
    current_user: CurrentUser,
    days: int = Query(default=30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Per-user request + token breakdown for org admins."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(
            User.id, User.email, User.full_name,
            TokenWallet.balance_tokens,
            TokenWallet.tokens_used_lifetime,
            func.coalesce(func.sum(
                case((RequestLog.created_at >= since, 1), else_=0)
            ), 0).label("requests"),
            func.coalesce(func.sum(
                case((
                    (RequestLog.created_at >= since) & (RequestLog.status != "delivered"),
                    1
                ), else_=0)
            ), 0).label("blocked"),
        )
        .outerjoin(TokenWallet, TokenWallet.user_id == User.id)
        .outerjoin(APIKey, APIKey.owner_id == User.id)
        .outerjoin(RequestLog, RequestLog.api_key_id == APIKey.id)
        .where(User.org_id == current_user.org_id)
        .group_by(User.id, User.email, User.full_name, TokenWallet.balance_tokens, TokenWallet.tokens_used_lifetime)
        .order_by(func.coalesce(func.sum(
            case((RequestLog.created_at >= since, 1), else_=0)
        ), 0).desc())
    )
    return [
        {
            "id": r.id,
            "email": r.email,
            "full_name": r.full_name,
            "tokens_balance": r.balance_tokens or 0,
            "tokens_used_lifetime": r.tokens_used_lifetime or 0,
            "requests": int(r.requests),
            "blocked": int(r.blocked),
        }
        for r in result.all()
    ]


@router.get("/logs")
async def logs(
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    status_filter: str | None = Query(default=None),
    keyword: str | None = Query(default=None, max_length=200),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    backend_filter: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Paginated request log with status, keyword, date range, and backend filters."""
    from sqlalchemy import or_
    filters = []
    if current_user.org_id:
        filters.append(RequestLog.org_id == current_user.org_id)
    if status_filter:
        filters.append(RequestLog.status == status_filter)
    if keyword:
        filters.append(or_(
            RequestLog.prompt_preview.ilike(f"%{keyword}%"),
            RequestLog.fired_rule.ilike(f"%{keyword}%"),
            RequestLog.input_block_reason.ilike(f"%{keyword}%"),
        ))
    if date_from:
        try:
            filters.append(RequestLog.created_at >= datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc))
        except ValueError:
            pass
    if date_to:
        try:
            filters.append(RequestLog.created_at <= datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc))
        except ValueError:
            pass
    if backend_filter:
        filters.append(RequestLog.backend == backend_filter)

    count_q  = await db.execute(select(func.count()).select_from(RequestLog).where(*filters))
    total    = count_q.scalar() or 0

    logs_q   = await db.execute(
        select(RequestLog)
        .where(*filters)
        .order_by(RequestLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        {
            "id":                  log.id,
            "status":              log.status,
            "prompt_preview":      log.prompt_preview,
            "full_prompt":         None,  # never expose raw prompts to the client
            "model":               log.model,
            "backend":             log.backend,
            "latency_ms":          log.latency_ms,
            "input_passed":        log.input_passed,
            "output_passed":       log.output_passed,
            "input_block_reason":  log.input_block_reason,
            "output_block_reason": log.output_block_reason,
            "fired_rule":          log.fired_rule,
            "input_tokens":        log.input_tokens,
            "output_tokens":       log.output_tokens,
            "created_at":          log.created_at.isoformat(),
            "request_id":          log.id,
        }
        for log in logs_q.scalars().all()
    ]

    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/export")
async def export_logs(
    current_user: CurrentUser,
    days: int = Query(default=30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Download request logs as a CSV file."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    filters = [RequestLog.created_at >= since]
    if current_user.org_id:
        filters.append(RequestLog.org_id == current_user.org_id)

    result = await db.execute(
        select(RequestLog)
        .where(*filters)
        .order_by(RequestLog.created_at.desc())
        .limit(10_000)
    )
    logs = result.scalars().all()

    fields = [
        "id", "created_at", "status", "backend", "model",
        "latency_ms", "input_tokens", "output_tokens", "estimated_cost_usd",
        "input_passed", "input_block_reason",
        "output_passed", "output_block_reason",
        "fired_rule", "prompt_preview",
    ]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    for log in logs:
        tokens = log.input_tokens + log.output_tokens
        writer.writerow({
            "id":                   log.id,
            "created_at":           log.created_at.isoformat(),
            "status":               log.status,
            "backend":              log.backend,
            "model":                log.model,
            "latency_ms":           log.latency_ms,
            "input_tokens":         log.input_tokens,
            "output_tokens":        log.output_tokens,
            "estimated_cost_usd":   estimate_cost_usd(log.backend, log.model, tokens),
            "input_passed":         log.input_passed,
            "input_block_reason":   log.input_block_reason or "",
            "output_passed":        log.output_passed,
            "output_block_reason":  log.output_block_reason or "",
            "fired_rule":           log.fired_rule or "",
            "prompt_preview":       log.prompt_preview,
        })

    filename = f"guardrails-logs-{days}d.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/false-positive-candidates")
async def false_positive_candidates(
    current_user: CurrentUser,
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Blocked requests that users later disputed — either via positive feedback
    (thumbs-up on a blocked request) or because the owner later added the rule
    to their always-allow overrides. Grouped by fired rule so you can spot the
    guardrails most likely throwing false positives.

    Backed by the mv_false_positive_candidates_daily materialized view, which
    precomputes the feedback/override join once per refresh instead of per
    request. The view is refreshed on a schedule
    (scripts/refresh_analytics_views.py) — data can lag live request logs by
    up to one refresh interval; newly-arriving feedback is only visible after
    the next refresh.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    filters = [MvFalsePositiveCandidatesDaily.day >= since.date()]
    if current_user.org_id:
        filters.append(MvFalsePositiveCandidatesDaily.org_id == current_user.org_id)

    rows = (
        await db.execute(
            select(MvFalsePositiveCandidatesDaily)
            .where(*filters)
            .order_by(MvFalsePositiveCandidatesDaily.created_at.desc())
            .limit(500)
        )
    ).scalars().all()

    by_rule: dict[str, dict] = {}
    for r in rows:
        entry = by_rule.setdefault(
            r.fired_rule,
            {"fired_rule": r.fired_rule, "count": 0, "examples": []},
        )
        entry["count"] += 1
        if len(entry["examples"]) < 5:
            entry["examples"].append({
                "id": r.request_log_id,
                "status": r.status,
                "prompt_preview": r.prompt_preview,
                "created_at": r.created_at.isoformat(),
                "positive_feedback": r.positive_feedback,
                "override_hit": r.override_hit,
            })

    return sorted(by_rule.values(), key=lambda r: r["count"], reverse=True)[:limit]
