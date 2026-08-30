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


def _next_team_name(db_orgs: list) -> str:
    # Default Team 1, Team 2, etc. based on existing org names that start with Team
    import re as _re
    nums = []
    for o in db_orgs:
        m = _re.match(r"Team\s+(\d+)", o.name)
        if m:
            nums.append(int(m.group(1)))
    n = (max(nums) + 1) if nums else 1
    # If Team N already taken (due to rename), keep incrementing
    existing_names = {o.name for o in db_orgs}
    while f"Team {n}" in existing_names:
        n += 1
    return f"Team {n}"


class OrgUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(min_length=2, max_length=120)


class OrgCreate(BaseModel):
    model_config = {"extra": "forbid"}
    name: str | None = Field(default=None, max_length=120, description="Optional, defaults to Team 1, Team 2")


class OrgSwitch(BaseModel):
    model_config = {"extra": "forbid"}
    org_id: str = Field(description="Org to switch to")


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


@router.get("/list", response_model=list[OrgOut])
async def list_orgs(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """All teams/projects the current user belongs to — for team selector. Leader can be in many."""
    from app.models import OrgMembership
    # Primary org + memberships
    org_ids: set[str] = set()
    if current_user.org_id:
        org_ids.add(current_user.org_id)
    result = await db.execute(select(OrgMembership.org_id).where(OrgMembership.user_id == current_user.id))
    for (oid,) in result.all():
        org_ids.add(oid)
    if not org_ids:
        return []
    result2 = await db.execute(select(Organization).where(Organization.id.in_(list(org_ids))).order_by(Organization.created_at))
    return result2.scalars().all()


@router.post("", response_model=OrgOut, status_code=201)
async def create_org(body: OrgCreate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Create a new team/project. Defaults to Team 1, Team 2 if name omitted. Creator becomes admin and is switched to it. Caps: 500 teams per user, 500 members per team."""
    from app.models import OrgMembership, OrgPolicy
    from app.defaults import DEFAULT_COMPLIANCE, DEFAULT_INPUT_RULES, DEFAULT_OUTPUT_RULES, DEFAULT_TOPIC_POLICY
    # Cap teams per user to 500
    org_ids: set[str] = set()
    if current_user.org_id:
        org_ids.add(current_user.org_id)
    mem = await db.execute(select(OrgMembership.org_id).where(OrgMembership.user_id == current_user.id))
    for (oid,) in mem.all():
        org_ids.add(oid)
    if len(org_ids) >= 500:
        raise HTTPException(status_code=400, detail="Team limit reached — max 500 teams per user.")
    existing_orgs = []
    if org_ids:
        res = await db.execute(select(Organization).where(Organization.id.in_(list(org_ids))))
        existing_orgs = list(res.scalars().all())
    name = (body.name or "").strip() or _next_team_name(existing_orgs)
    slug = _slugify(name)
    # Ensure slug unique
    base_slug = slug
    counter = 1
    while True:
        check = await db.execute(select(Organization).where(Organization.slug == slug))
        if not check.scalar_one_or_none():
            break
        counter += 1
        slug = f"{base_slug}-{counter}"
    org = Organization(name=name, slug=slug)
    db.add(org)
    await db.flush()
    # Policy
    policy = OrgPolicy(org_id=org.id, input_rules=DEFAULT_INPUT_RULES, output_rules=DEFAULT_OUTPUT_RULES, topic_policy=DEFAULT_TOPIC_POLICY, compliance_rules=DEFAULT_COMPLIANCE)
    db.add(policy)
    # Membership + switch
    membership = OrgMembership(user_id=current_user.id, org_id=org.id, role="admin")
    db.add(membership)
    current_user.org_id = org.id
    current_user.is_admin = True
    await db.flush()
    return org


@router.post("/switch", response_model=OrgOut)
async def switch_org(body: OrgSwitch, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Switch working team — leader can be in many teams, click Team 1/Team 2 to work there. Updates User.org_id."""
    from app.models import OrgMembership
    org = await db.get(Organization, body.org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Team not found")
    # Check membership or invite
    is_member = False
    if current_user.org_id == org.id:
        is_member = True
    else:
        res = await db.execute(select(OrgMembership).where(OrgMembership.user_id == current_user.id, OrgMembership.org_id == org.id))
        if res.scalar_one_or_none():
            is_member = True
    if not is_member:
        raise HTTPException(status_code=403, detail="Not a member of this team")
    # Update role from membership if exists
    res = await db.execute(select(OrgMembership).where(OrgMembership.user_id == current_user.id, OrgMembership.org_id == org.id))
    mem = res.scalar_one_or_none()
    current_user.org_id = org.id
    if mem:
        current_user.is_admin = (mem.role == "admin")
    await db.flush()
    return org


@router.patch("/{org_id}", response_model=OrgOut)
async def rename_org_by_id(org_id: str, body: OrgUpdate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Rename any team you are admin of — easy rename for Team 1 → My Project."""
    from app.models import OrgMembership
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Team not found")
    is_admin = False
    if current_user.org_id == org.id and current_user.is_admin:
        is_admin = True
    else:
        res = await db.execute(select(OrgMembership).where(OrgMembership.user_id == current_user.id, OrgMembership.org_id == org.id, OrgMembership.role == "admin"))
        if res.scalar_one_or_none():
            is_admin = True
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin required for this team")
    new_slug = _slugify(body.name)
    existing = await db.execute(select(Organization).where(Organization.slug == new_slug, Organization.id != org.id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Name taken")
    org.name = body.name
    org.slug = new_slug
    await db.flush()
    return org


class OrgDeleteConfirm(BaseModel):
    model_config = {"extra": "forbid"}
    full_name: str = Field(min_length=2, max_length=120, description="Must match your full name to confirm delete")


@router.delete("/{org_id}", status_code=204)
async def delete_org(org_id: str, body: OrgDeleteConfirm, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Delete project — last button, leader only, must sign full name exactly."""
    from app.models import OrgMembership, OrgPolicy, ManagedSkill
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Team not found")
    # Must be admin of that org
    is_admin = False
    if current_user.org_id == org.id and current_user.is_admin:
        is_admin = True
    else:
        res = await db.execute(select(OrgMembership).where(OrgMembership.user_id == current_user.id, OrgMembership.org_id == org_id, OrgMembership.role == "admin"))
        if res.scalar_one_or_none():
            is_admin = True
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only a leader can delete the project")
    # Must sign full name exactly (case-sensitive trim)
    if body.full_name.strip() != current_user.full_name.strip():
        raise HTTPException(status_code=400, detail=f"Full name does not match — type '{current_user.full_name}' exactly to confirm")
    # Delete all memberships, policies, skills, then org (cascade will handle)
    await db.execute(select(OrgMembership).where(OrgMembership.org_id == org_id))  # ensure load
    # Delete memberships
    mems = await db.execute(select(OrgMembership).where(OrgMembership.org_id == org_id))
    for m in mems.scalars().all():
        await db.delete(m)
    # Delete managed skills and policies
    # OrgPolicy cascade, but delete explicitly for clarity
    pol = await db.execute(select(OrgPolicy).where(OrgPolicy.org_id == org_id))
    for p in pol.scalars().all():
        await db.delete(p)
    # If user's primary org is this one, switch them to another team or clear
    if current_user.org_id == org_id:
        other_mem = await db.execute(select(OrgMembership).where(OrgMembership.user_id == current_user.id).order_by(OrgMembership.created_at).limit(1))
        other = other_mem.scalar_one_or_none()
        if other and other.org_id != org_id:
            current_user.org_id = other.org_id
            current_user.is_admin = (other.role == "admin")
        else:
            # Check other membership after delete (we just deleted this org's, so other is next)
            remaining = await db.execute(select(OrgMembership).where(OrgMembership.user_id == current_user.id).limit(1))
            rem = remaining.scalar_one_or_none()
            if rem:
                current_user.org_id = rem.org_id
                current_user.is_admin = (rem.role == "admin")
            else:
                current_user.org_id = None
                current_user.is_admin = False
    # Users whose primary org was this team → clear or move to their next membership
    primary_users = await db.execute(select(User).where(User.org_id == org_id))
    for u in primary_users.scalars().all():
        if u.id == current_user.id:
            continue
        other_u = await db.execute(select(OrgMembership).where(OrgMembership.user_id == u.id).limit(1))
        ou = other_u.scalar_one_or_none()
        if ou and ou.org_id != org_id:
            u.org_id = ou.org_id
            u.is_admin = (ou.role == "admin")
        else:
            u.org_id = None
            u.is_admin = False
    await db.delete(org)
    await db.flush()
    return None


@router.post("/leave", response_model=dict)
async def leave_current_team(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Leave current team. If you are the only leader, you must assign another first — else auto-promote previous leader or random member."""
    if not current_user.org_id:
        raise HTTPException(status_code=400, detail="Not in a team")
    from app.models import OrgMembership
    org_id = current_user.org_id
    # Check if user is the only admin — block if so
    admin_mems = await db.execute(select(OrgMembership).where(OrgMembership.org_id == org_id, OrgMembership.role == "admin"))
    admins = admin_mems.scalars().all()
    primary_admins = await db.execute(select(User).where(User.org_id == org_id, User.is_admin == True))
    primary_admin_ids = {u.id for u in primary_admins.scalars().all()}
    all_admin_ids = {m.user_id for m in admins} | primary_admin_ids
    is_leader = current_user.id in all_admin_ids or current_user.is_admin
    if is_leader and len(all_admin_ids) == 1 and current_user.id in all_admin_ids:
        raise HTTPException(status_code=400, detail="You are the only leader — assign another leader before leaving.")
    # Remove membership
    mem = await db.execute(select(OrgMembership).where(OrgMembership.user_id == current_user.id, OrgMembership.org_id == org_id))
    membership = mem.scalar_one_or_none()
    was_admin = False
    if membership:
        was_admin = (membership.role == "admin")
        await db.delete(membership)
    elif current_user.is_admin:
        was_admin = True
    # If was admin and team would have no admin, auto-promote
    if was_admin:
        # Re-count after deletion (need flush first to reflect delete)
        await db.flush()
        admin_mems2 = await db.execute(select(OrgMembership).where(OrgMembership.org_id == org_id, OrgMembership.role == "admin"))
        remaining = admin_mems2.scalars().all()
        primary2 = await db.execute(select(User).where(User.org_id == org_id, User.is_admin == True))
        total2 = len(remaining) + len(primary2.scalars().all())
        if total2 == 0:
            # Prefer previous leader (oldest admin membership) — but we already deleted, so pick oldest member
            cand_mem = await db.execute(select(OrgMembership).where(OrgMembership.org_id == org_id).order_by(OrgMembership.created_at).limit(1))
            candidate = cand_mem.scalar_one_or_none()
            if candidate:
                candidate.role = "admin"
                cand_user = await db.get(User, candidate.user_id)
                if cand_user and cand_user.org_id == org_id:
                    cand_user.is_admin = True
            else:
                cand_user_res = await db.execute(select(User).where(User.org_id == org_id).order_by(User.created_at).limit(1))
                cand_user = cand_user_res.scalar_one_or_none()
                if cand_user:
                    cand_user.is_admin = True
                    db.add(OrgMembership(user_id=cand_user.id, org_id=org_id, role="admin"))
            await db.flush()
    # Switch to another team or clear
    other_mem = await db.execute(select(OrgMembership).where(OrgMembership.user_id == current_user.id).order_by(OrgMembership.created_at).limit(1))
    other = other_mem.scalar_one_or_none()
    if other:
        current_user.org_id = other.org_id
        current_user.is_admin = (other.role == "admin")
    else:
        # Check if user has primary elsewhere? Keep as is if not
        # If no other membership, clear
        current_user.org_id = None
        current_user.is_admin = False
    await db.flush()
    return {"left": org_id, "new_org_id": current_user.org_id}


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
