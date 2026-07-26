"""
Agent skill scanner — find secrets, PII, and internal details before they ship in agent context.
"""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import CurrentUser
from app.i18n import _t
from app.schemas import (
    SkillFindingOut,
    SkillRejectionCreateIn,
    SkillRejectionOut,
    SkillRejectionReportIn,
    SkillRejectionResolveIn,
    SkillScanRequest,
    SkillScanResponse,
)
from app.services.skill_rejections import list_rejections, record_rejection, resolve_rejection
from app.services.skill_user_overrides import load_user_overrides
from guardrails.skill import SkillFinding, SkillGuardrail
from guardrails.skill_messages import explain_finding
from guardrails.skill_overrides import SkillOverrides, apply_overrides, finding_key

router = APIRouter(prefix="/skills", tags=["Agent Skills"])

DEFAULT_OVERRIDES_PATH = Path(".cursor/skill-guard-overrides.json")


def _finding_out(f: SkillFinding, *, allowed: bool = False) -> SkillFindingOut:
    return SkillFindingOut(
        finding_key=finding_key(f),
        category=f.category,
        severity=f.severity,
        check=f.check,
        reason=f.reason or "",
        reason_code=f.reason_code,
        explanation=explain_finding(f.reason_code, f.check),
        line_number=f.line_number,
        snippet=f.snippet,
        risk_score=f.risk_score,
        allowed_by_override=allowed,
    )


def _merge_overrides(base: SkillOverrides, extra: SkillOverrides) -> SkillOverrides:
    base.session_allow_keys |= extra.session_allow_keys
    base.always_allow_keys |= extra.always_allow_keys
    base.always_allow_reason_codes |= extra.always_allow_reason_codes
    return base


async def _load_overrides(db: AsyncSession, user_id: str, body: SkillScanRequest) -> SkillOverrides:
    base = SkillOverrides.from_dict(body.overrides.model_dump() if body.overrides else None)
    base = _merge_overrides(base, await load_user_overrides(db, user_id))
    if DEFAULT_OVERRIDES_PATH.is_file():
        try:
            on_disk = json.loads(DEFAULT_OVERRIDES_PATH.read_text(encoding="utf-8"))
            base = _merge_overrides(base, SkillOverrides.from_dict(on_disk))
        except (json.JSONDecodeError, OSError):
            pass
    return base


@router.get("/rejections", response_model=list[SkillRejectionOut])
async def get_rejections(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    status: str = Query(default="pending", description="pending | all | unblocked_once | unblocked_always | kept_rejected"),
    limit: int = Query(default=50, ge=1, le=100),
):
    rows = await list_rejections(db, current_user, status=status, limit=limit)
    return rows


@router.post("/rejections/report", response_model=SkillRejectionOut, status_code=201)
async def report_rejection(
    body: SkillRejectionReportIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Record rejected access from git push, CLI, or CI (authenticated)."""
    row = await record_rejection(
        db,
        user=current_user,
        filename=body.filename,
        source=body.source,
        findings=[f.model_dump() for f in body.findings],
        summary=body.rejection_summary,
        content_preview=body.content_preview,
    )
    await db.commit()
    return row


@router.post("/rejections/create", response_model=SkillRejectionOut, status_code=201)
async def create_rejection_from_content(
    body: SkillRejectionCreateIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Web helper: submit skill content, auto-scan, and add only blocked findings
    into the rejected-access review queue.
    """
    result = SkillGuardrail().scan(body.content)
    if result.safe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_t("skills.no_findings"),
        )

    row = await record_rejection(
        db,
        user=current_user,
        filename=body.filename,
        source=body.source,
        findings=result.findings,
        summary=body.rejection_summary or f"Rejected access: {len(result.findings)} issue(s)",
        content_preview=body.content_preview or body.content[:500],
    )
    await db.commit()
    return row


@router.post("/rejections/{rejection_id}/resolve", response_model=SkillRejectionOut)
async def resolve_rejected_access(
    rejection_id: str,
    body: SkillRejectionResolveIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    row = await resolve_rejection(
        db,
        current_user,
        rejection_id,
        body.action,
        body.note,
    )
    await db.commit()
    return row


@router.post("/scan", response_model=SkillScanResponse)
async def scan_skill(
    body: SkillScanRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = SkillGuardrail().scan(body.content)
    overrides = await _load_overrides(db, current_user.id, body)
    decision = apply_overrides(result, overrides)

    all_out = [_finding_out(f, allowed=overrides.is_allowed(f)) for f in result.findings]
    blocking_out = [_finding_out(f) for f in decision.blocking]
    overridden_out = [_finding_out(f, allowed=True) for f in decision.allowed]

    rejection_id = None
    if decision.blocking:
        row = await record_rejection(
            db,
            user=current_user,
            filename=body.filename,
            source="api_scan",
            findings=decision.blocking,
            summary=decision.rejection_summary,
            content_preview=body.content[:500],
        )
        rejection_id = row.id
        await db.commit()

    return SkillScanResponse(
        safe=result.safe,
        risk_score=result.risk_score,
        findings=all_out,
        line_count=result.line_count,
        char_count=result.char_count,
        filename=body.filename,
        blocked=decision.blocked,
        agent_may_continue=decision.safe,
        agent_status="paused" if decision.blocked else "ok",
        rejection_summary=decision.rejection_summary,
        blocking_findings=blocking_out,
        overridden_findings=overridden_out,
        rejection_id=rejection_id,
    )

