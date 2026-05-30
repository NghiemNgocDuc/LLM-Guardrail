"""
Analytics endpoints (JWT-authenticated — dashboard use only):
  GET /analytics/dashboard   — full stats for current org
  GET /analytics/logs        — paginated request log
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, case, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import CurrentUser
from app.models import RequestLog
from app.schemas import (
    AnalyticsDashboard, TimeSeriesPoint, TopFiredRule, UsageSummary,
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
            func.sum(case((RequestLog.status == "error",         1), else_=0)).label("errors"),
            func.avg(RequestLog.latency_ms).label("avg_latency"),
            func.sum(RequestLog.input_tokens + RequestLog.output_tokens).label("total_tokens"),
        ).where(*base_filter)
    )
    row = summary_q.one()
    total = row.total or 0
    blocked = (row.input_blocked or 0) + (row.output_blocked or 0)

    summary = UsageSummary(
        total_requests=total,
        delivered=row.delivered or 0,
        input_blocked=row.input_blocked or 0,
        output_blocked=row.output_blocked or 0,
        error_count=row.errors or 0,
        block_rate_pct=round(blocked / total * 100, 2) if total else 0.0,
        avg_latency_ms=round(row.avg_latency or 0, 1),
        total_tokens=row.total_tokens or 0,
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
        recent_logs=recent_logs,
    )


@router.get("/logs")
async def logs(
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    status_filter: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Paginated request log with optional status filter."""
    filters = []
    if current_user.org_id:
        filters.append(RequestLog.org_id == current_user.org_id)
    if status_filter:
        filters.append(RequestLog.status == status_filter)

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
        }
        for log in logs_q.scalars().all()
    ]

    return {"total": total, "page": page, "page_size": page_size, "items": items}
