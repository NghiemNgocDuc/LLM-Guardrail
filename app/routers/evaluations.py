"""Inference tables — per-guardrail trace (Databricks pattern)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import CurrentUser
from app.models import GuardrailEvaluation

router = APIRouter(prefix="/evaluations", tags=["Evaluations"])

@router.get("", response_model=list[dict])
async def list_evals(
    current_user: CurrentUser,
    correlation_id: str | None = None,
    guardrail: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    q = select(GuardrailEvaluation).order_by(GuardrailEvaluation.created_at.desc()).limit(limit)
    if correlation_id:
        q = q.where(GuardrailEvaluation.correlation_id == correlation_id)
    if guardrail:
        q = q.where(GuardrailEvaluation.guardrail == guardrail)
    # scope to org via request_logs org_id if needed — simple: filter by org_id if set
    if current_user.org_id:
        q = q.where((GuardrailEvaluation.org_id == current_user.org_id) | (GuardrailEvaluation.org_id.is_(None)))
    res = await db.execute(q)
    return [
        {
            "id": r.id, "correlation_id": r.correlation_id, "guardrail": r.guardrail,
            "stage": r.stage, "action": r.action, "reason_code": r.reason_code,
            "latency_ms": r.latency_ms, "created_at": r.created_at,
        }
        for r in res.scalars().all()
    ]
