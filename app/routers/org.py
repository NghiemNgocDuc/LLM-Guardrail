"""
Organisation settings:
  GET   /org                        — current org details
  PATCH /org                        — rename org (admin only)
  GET   /org/export                 — paginated audit export (admin only)
  POST  /org/rotate-webhook-secret  — new webhook HMAC secret (admin only)
"""
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import CurrentUser
from app.i18n import _t
from app.models import APIKey, Organization, OrgPolicy, RequestLog, User
from app.schemas import OrgOut, RotatedWebhookSecret

router = APIRouter(prefix="/org", tags=["Organisation"])


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]


class OrgUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(min_length=2, max_length=120)


@router.get("", response_model=OrgOut)
async def get_org(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail=_t("org.not_found"))
    org = await db.get(Organization, current_user.org_id)
    if not org:
        raise HTTPException(status_code=404, detail=_t("org.missing"))
    return org


@router.patch("", response_model=OrgOut)
async def update_org(body: OrgUpdate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_t("admin.access_required"))
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail=_t("org.no_org"))
    org = await db.get(Organization, current_user.org_id)
    if not org:
        raise HTTPException(status_code=404, detail=_t("org.missing"))

    new_slug = _slugify(body.name)
    existing = await db.execute(
        select(Organization).where(Organization.slug == new_slug, Organization.id != org.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=_t("org.name_taken"))

    org.name = body.name
    org.slug = new_slug
    await db.flush()
    return org


@router.get("/export")
async def export_org_data(
    current_user: CurrentUser,
    days: int = Query(default=30, ge=1, le=90),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Org-scoped audit export for admins. Paginated request logs joined to the
    owning user's email. Never exposes raw prompts, passwords, or key hashes."""
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_t("admin.access_required"))
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail=_t("org.no_org"))

    since = datetime.now(timezone.utc) - timedelta(days=days)
    filters = [RequestLog.created_at >= since, RequestLog.org_id == current_user.org_id]

    count_q = await db.execute(select(func.count()).select_from(RequestLog).where(*filters))
    total = count_q.scalar() or 0

    rows_q = await db.execute(
        select(RequestLog, User.email)
        .outerjoin(APIKey, APIKey.id == RequestLog.api_key_id)
        .outerjoin(User, User.id == APIKey.owner_id)
        .where(*filters)
        .order_by(RequestLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        {
            "id":                  log.id,
            "request_id":          log.id,
            "status":              log.status,
            "user_email":          user_email,
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
        for log, user_email in rows_q.all()
    ]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.post("/rotate-webhook-secret", response_model=RotatedWebhookSecret)
async def rotate_webhook_secret(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Generate a new HMAC-SHA256 secret used to sign guardrail webhooks.
    Shown exactly once — store it in your webhook receiver."""
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_t("admin.access_required"))
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail=_t("org.no_org"))
    result = await db.execute(select(OrgPolicy).where(OrgPolicy.org_id == current_user.org_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail=_t("policy.not_found"))

    new_secret = secrets.token_urlsafe(32)
    rules = dict(policy.compliance_rules or {})
    rules["webhook_secret"] = new_secret
    policy.compliance_rules = rules
    await db.flush()
    return RotatedWebhookSecret(
        webhook_secret=new_secret,
        created_at=datetime.now(timezone.utc),
    )
