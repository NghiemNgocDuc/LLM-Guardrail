"""
Per-org policy management (admin only):
  GET   /policy        — current org policy
  PATCH /policy        — partial update
  POST  /policy/reset  — restore defaults
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import CurrentUser
from app.i18n import _t
from app.models import OrgPolicy
from app.schemas import PolicyDiffEntry, PolicyDiffRequest, PolicyOut, PolicyUpdate

router = APIRouter(prefix="/policy", tags=["Policy"])

# Fields compared by POST /policy/diff in a flat, field-by-field manner.
# input_rules/output_rules/topic_policy/compliance_rules are JSON blobs that
# may contain nested structures — those are compared wholesale, per field.
_POLICY_DIFF_FIELDS = [
    "input_rules", "output_rules", "topic_policy", "compliance_rules",
    "llm_backend", "llm_model", "rate_limit_rpm", "rate_limit_rpd",
]


def _require_admin(user):
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_t("admin.access_required"))


@router.get("", response_model=PolicyOut)
async def get_policy(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail=_t("org.not_found"))
    result = await db.execute(select(OrgPolicy).where(OrgPolicy.org_id == current_user.org_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail=_t("policy.not_found"))
    return policy


@router.patch("", response_model=PolicyOut)
async def update_policy(
    body: PolicyUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail=_t("policy.no_org"))

    result = await db.execute(select(OrgPolicy).where(OrgPolicy.org_id == current_user.org_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail=_t("policy.not_found"))

    # Only update fields that were explicitly sent
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(policy, field, value)

    await db.flush()
    return policy


@router.post("/reset", response_model=PolicyOut)
async def reset_policy(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Restore the org's policy to the system defaults."""
    _require_admin(current_user)
    from app.defaults import (
        DEFAULT_INPUT_RULES, DEFAULT_OUTPUT_RULES,
        DEFAULT_TOPIC_POLICY, DEFAULT_COMPLIANCE,
    )
    result = await db.execute(select(OrgPolicy).where(OrgPolicy.org_id == current_user.org_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail=_t("policy.not_found"))

    policy.input_rules      = DEFAULT_INPUT_RULES
    policy.output_rules     = DEFAULT_OUTPUT_RULES
    policy.topic_policy     = DEFAULT_TOPIC_POLICY
    policy.compliance_rules = DEFAULT_COMPLIANCE
    policy.llm_backend      = None
    policy.llm_model        = None
    await db.flush()
    return policy


@router.post("/diff", response_model=list[PolicyDiffEntry])
async def diff_policy(
    body: PolicyDiffRequest,
    current_user: CurrentUser,
):
    """
    Compare two policy blobs field by field. No DB write — pure comparison.

    Nested structures inside the rule blobs (e.g. pii_patterns entries) are
    compared as whole values per top-level field, not recursively.
    """
    a, b = body.policy_a, body.policy_b
    return [
        PolicyDiffEntry(field=field, before=a.get(field), after=b.get(field))
        for field in _POLICY_DIFF_FIELDS
        if a.get(field) != b.get(field)
    ]
