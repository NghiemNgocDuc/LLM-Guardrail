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
from app.models import OrgPolicy
from app.schemas import PolicyOut, PolicyUpdate

router = APIRouter(prefix="/policy", tags=["Policy"])


def _require_admin(user):
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


@router.get("", response_model=PolicyOut)
async def get_policy(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail="No organization associated with this account")
    result = await db.execute(select(OrgPolicy).where(OrgPolicy.org_id == current_user.org_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy


@router.patch("", response_model=PolicyOut)
async def update_policy(
    body: PolicyUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail="No organization")

    result = await db.execute(select(OrgPolicy).where(OrgPolicy.org_id == current_user.org_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    # Only update fields that were explicitly sent
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(policy, field, value)

    await db.flush()
    return policy


@router.post("/reset", response_model=PolicyOut)
async def reset_policy(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Restore the org's policy to the system defaults."""
    _require_admin(current_user)
    from app.routers.auth import (
        _DEFAULT_INPUT_RULES, _DEFAULT_OUTPUT_RULES,
        _DEFAULT_TOPIC_POLICY, _DEFAULT_COMPLIANCE,
    )
    result = await db.execute(select(OrgPolicy).where(OrgPolicy.org_id == current_user.org_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    policy.input_rules      = _DEFAULT_INPUT_RULES
    policy.output_rules     = _DEFAULT_OUTPUT_RULES
    policy.topic_policy     = _DEFAULT_TOPIC_POLICY
    policy.compliance_rules = _DEFAULT_COMPLIANCE
    policy.llm_backend      = None
    policy.llm_model        = None
    await db.flush()
    return policy
