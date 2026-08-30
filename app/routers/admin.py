import secrets
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import CurrentUser, hash_password
from app.i18n import _t
from app.models import APIKey, OrgPolicy, RequestLog, TokenWallet, User
from app.schemas import (
    AdminInviteUser, AdminUserStats, AdminUserUpdate, APIKeyOut, BulkUserAction,
    ReplayCurrentVerdict, ReplayOriginalVerdict, ReplayResponse, UserOut,
)
from app.config import get_settings
from app.services.auth_tokens import TOKEN_PURPOSE_RESET, build_action_url, create_auth_token
from app.services.email import send_password_reset_email
from app.services.prompt_crypto import decrypt_prompt
from app.services.token_wallet import ensure_wallet
from guardrails.input import InputGuardrail

settings = get_settings()
router = APIRouter(prefix="/admin", tags=["Admin"])


TEAM_MEMBER_CAP = 500
TEAM_TERMS_CAP = 500  # terms = managed skills + org terms per team

def require_org_admin(user: User) -> None:
    if not user.is_admin or not user.org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_t("admin.access_required"))

async def _check_team_member_cap(db: AsyncSession, org_id: str) -> None:
    from app.models import OrgMembership
    # Count via primary org_id + membership
    cnt_res = await db.execute(select(func.count()).select_from(User).where(User.org_id == org_id))
    primary_cnt = cnt_res.scalar() or 0
    mem_cnt_res = await db.execute(select(func.count()).select_from(OrgMembership).where(OrgMembership.org_id == org_id))
    mem_cnt = mem_cnt_res.scalar() or 0
    # Deduplicate: users counted in both primary and membership
    # For cap, use max of sum with dedup estimate via distinct user_ids
    distinct_res = await db.execute(select(func.count(func.distinct(User.id))).select_from(User).outerjoin(OrgMembership, (OrgMembership.user_id == User.id) & (OrgMembership.org_id == org_id)).where((User.org_id == org_id) | (OrgMembership.org_id == org_id)))
    distinct_cnt = distinct_res.scalar() or 0
    # Fallback to max if distinct fails
    total = distinct_cnt if distinct_cnt else max(primary_cnt, mem_cnt)
    if total >= TEAM_MEMBER_CAP:
        raise HTTPException(status_code=400, detail=f"Team member cap reached — max {TEAM_MEMBER_CAP} members per team.")

async def _check_team_terms_cap(db: AsyncSession, org_id: str) -> None:
    from app.models import ManagedSkill
    cnt_res = await db.execute(select(func.count()).select_from(ManagedSkill).where(ManagedSkill.org_id == org_id))
    cnt = cnt_res.scalar() or 0
    if cnt >= TEAM_TERMS_CAP:
        raise HTTPException(status_code=400, detail=f"Team terms cap reached — max {TEAM_TERMS_CAP} terms per team.")


@router.post("/users/invite", response_model=UserOut)
async def invite_user(
    body: AdminInviteUser,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    require_org_admin(current_user)
    await _check_team_member_cap(db, current_user.org_id)

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_t("admin.email_exists"))

    temp_password = secrets.token_urlsafe(16)
    user = User(
        email=body.email,
        hashed_password=hash_password(temp_password),
        full_name=body.full_name,
        is_admin=body.is_admin,
        org_id=current_user.org_id,
        email_verified=False,
    )
    db.add(user)
    await db.flush()
    # Also add to membership table for multi-team support
    try:
        from app.models import OrgMembership
        db.add(OrgMembership(user_id=user.id, org_id=current_user.org_id, role="admin" if body.is_admin else "member"))
        # Ensure inviter has membership entry for current org
        mem_check = await db.execute(select(OrgMembership).where(OrgMembership.user_id == current_user.id, OrgMembership.org_id == current_user.org_id))
        if not mem_check.scalar_one_or_none():
            db.add(OrgMembership(user_id=current_user.id, org_id=current_user.org_id, role="admin" if current_user.is_admin else "member"))
    except Exception:
        pass

    # Multi-leader: inviting as admin does NOT demote inviter — team can have multiple leaders
    await ensure_wallet(db, user.id)

    raw = await create_auth_token(
        db,
        user_id=user.id,
        purpose=TOKEN_PURPOSE_RESET,
        expire_hours=settings.PASSWORD_RESET_EXPIRE_HOURS,
    )
    reset_url = build_action_url(settings.PUBLIC_APP_URL, "/reset-password", raw)
    await send_password_reset_email(user.email, reset_url)

    return user

@router.get("/users/lookup", response_model=UserOut)
async def lookup_user_by_email(
    current_user: CurrentUser,
    email: str = Query(..., description="Exact email to find"),
    db: AsyncSession = Depends(get_db),
):
    require_org_admin(current_user)
    clean = email.strip().lower()
    result = await db.execute(select(User).where(User.email == clean))
    user = result.scalar_one_or_none()
    if not user:
        result2 = await db.execute(select(User).where(User.email.ilike(clean)))
        user = result2.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found by email")
    return user


@router.post("/users/add-existing", response_model=UserOut)
async def add_existing_to_team(
    body: dict,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Add an existing user (found by email) to current org team — multi-team: keeps primary org, adds membership."""
    require_org_admin(current_user)
    await _check_team_member_cap(db, current_user.org_id)
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email required")
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        result2 = await db.execute(select(User).where(User.email.ilike(email)))
        user = result2.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found by email")
    from app.models import OrgMembership
    # Check if already member via membership or primary org_id
    mem_check = await db.execute(select(OrgMembership).where(OrgMembership.user_id == user.id, OrgMembership.org_id == current_user.org_id))
    already_member = mem_check.scalar_one_or_none() is not None or user.org_id == current_user.org_id
    if already_member:
        raise HTTPException(status_code=409, detail="User already in team")
    # Add membership only — keep primary org_id as is for multi-team (do not overwrite)
    # If user has no org, set primary
    if not user.org_id:
        user.org_id = current_user.org_id
    user.is_active = True
    try:
        # Add membership as member (leader can promote via update)
        db.add(OrgMembership(user_id=user.id, org_id=current_user.org_id, role="member"))
        # Ensure inviter also has membership
        inviter_mem = await db.execute(select(OrgMembership).where(OrgMembership.user_id == current_user.id, OrgMembership.org_id == current_user.org_id))
        if not inviter_mem.scalar_one_or_none():
            db.add(OrgMembership(user_id=current_user.id, org_id=current_user.org_id, role="admin" if current_user.is_admin else "member"))
    except Exception:
        pass
    await db.flush()
    return user


@router.get("/users", response_model=list[UserOut])
async def list_org_users(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    require_org_admin(current_user)
    from app.models import OrgMembership
    # Users in team via primary org_id OR membership (multi-team)
    result = await db.execute(
        select(User)
        .where(
            (User.org_id == current_user.org_id) |
            (User.id.in_(select(OrgMembership.user_id).where(OrgMembership.org_id == current_user.org_id)))
        )
        .order_by(User.created_at.desc())
    )
    # Deduplicate by id (in case both)
    users = {u.id: u for u in result.scalars().all()}
    return list(users.values())


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_org_user(
    user_id: str,
    body: AdminUserUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    require_org_admin(current_user)
    from app.models import OrgMembership
    user = await db.get(User, user_id)
    # Check membership via primary or join table (multi-team)
    is_member = False
    if user:
        if user.org_id == current_user.org_id:
            is_member = True
        else:
            mem_check = await db.execute(select(OrgMembership).where(OrgMembership.user_id == user_id, OrgMembership.org_id == current_user.org_id))
            if mem_check.scalar_one_or_none():
                is_member = True
    if not user or not is_member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_t("admin.user_not_found"))

    if user.id == current_user.id and body.is_active is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_t("admin.cannot_disable_self"))

    # Per-team role: update membership role if is_admin changed — allow multiple leaders
    if body.is_admin is not None:
        # If demoting (is_admin False), ensure at least 1 other leader remains
        if body.is_admin is False:
            # Count admins in this team
            admin_cnt_res = await db.execute(select(OrgMembership).where(OrgMembership.org_id == current_user.org_id, OrgMembership.role == "admin"))
            admins = admin_cnt_res.scalars().all()
            # Also count primary org admins without membership entry
            primary_admins = await db.execute(select(User).where(User.org_id == current_user.org_id, User.is_admin == True))
            primary_admin_ids = {u.id for u in primary_admins.scalars().all()}
            # Combine
            all_admin_ids = {m.user_id for m in admins} | primary_admin_ids
            # If demoting this user and they are the only admin, block
            if user_id in all_admin_ids and len(all_admin_ids) == 1:
                raise HTTPException(status_code=400, detail="Cannot demote: team must have at least 1 leader. Assign another leader first.")
            if user.id == current_user.id and len(all_admin_ids) == 1 and user_id in all_admin_ids:
                raise HTTPException(status_code=400, detail="Cannot decline leader role: you are the only leader. Assign another first.")
        mem = await db.execute(select(OrgMembership).where(OrgMembership.user_id == user_id, OrgMembership.org_id == current_user.org_id))
        membership = mem.scalar_one_or_none()
        if membership:
            membership.role = "admin" if body.is_admin else "member"
        elif body.is_admin:
            db.add(OrgMembership(user_id=user_id, org_id=current_user.org_id, role="admin"))
        elif body.is_admin is False and not membership:
            # Demoting a user with no membership entry but primary org — just update User.is_admin
            pass
        if user.org_id == current_user.org_id:
            user.is_admin = body.is_admin
        # Multi-leader: do NOT demote current user when promoting another — team can have multiple leaders

    if body.is_active is not None:
        user.is_active = body.is_active

    await db.flush()
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_org_user(user_id: str, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    require_org_admin(current_user)
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_t("admin.cannot_remove_self"))
    from app.models import OrgMembership
    user = await db.get(User, user_id)
    # Check membership
    is_member = False
    if user:
        if user.org_id == current_user.org_id:
            is_member = True
        else:
            mem_check = await db.execute(select(OrgMembership).where(OrgMembership.user_id == user_id, OrgMembership.org_id == current_user.org_id))
            if mem_check.scalar_one_or_none():
                is_member = True
    if not user or not is_member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_t("admin.user_not_found"))
    # Remove membership
    mem = await db.execute(select(OrgMembership).where(OrgMembership.user_id == user_id, OrgMembership.org_id == current_user.org_id))
    membership = mem.scalar_one_or_none()
    was_admin = False
    if membership:
        was_admin = (membership.role == "admin")
        await db.delete(membership)
    elif user.org_id == current_user.org_id and user.is_admin:
        was_admin = True
    # If primary org is this team, switch primary to another membership or clear
    if user.org_id == current_user.org_id:
        other_mem = await db.execute(select(OrgMembership).where(OrgMembership.user_id == user_id).limit(1))
        other = other_mem.scalar_one_or_none()
        if other:
            user.org_id = other.org_id
            user.is_admin = (other.role == "admin")
        else:
            user.org_id = None
            user.is_admin = False
    await db.flush()
    # If removed user was a leader, ensure team still has at least 1 leader — auto-promote if needed
    if was_admin:
        # Count remaining admins in this team
        admin_mems = await db.execute(select(OrgMembership).where(OrgMembership.org_id == current_user.org_id, OrgMembership.role == "admin"))
        remaining_admins = admin_mems.scalars().all()
        # Also count primary org admins (users with org_id == team and is_admin True but no membership)
        primary_admins_res = await db.execute(select(User).where(User.org_id == current_user.org_id, User.is_admin == True))
        primary_admins = primary_admins_res.scalars().all()
        total_admins = len(remaining_admins) + len(primary_admins)
        # If no admin left, promote someone: prefer previous leader (oldest membership) else random member
        if total_admins == 0:
            # Find a member to promote — oldest membership
            cand_mem = await db.execute(select(OrgMembership).where(OrgMembership.org_id == current_user.org_id).order_by(OrgMembership.created_at).limit(1))
            candidate = cand_mem.scalar_one_or_none()
            if candidate:
                candidate.role = "admin"
                # If their primary org is this team, also set is_admin
                cand_user = await db.get(User, candidate.user_id)
                if cand_user and cand_user.org_id == current_user.org_id:
                    cand_user.is_admin = True
            else:
                # No membership — pick a primary user in this team (oldest)
                cand_user_res = await db.execute(select(User).where(User.org_id == current_user.org_id).order_by(User.created_at).limit(1))
                cand_user = cand_user_res.scalar_one_or_none()
                if cand_user:
                    cand_user.is_admin = True
                    # Also create membership for them as admin for consistency
                    db.add(OrgMembership(user_id=cand_user.id, org_id=current_user.org_id, role="admin"))
            await db.flush()


@router.get("/users/stats", response_model=list[AdminUserStats])
async def user_stats(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    require_org_admin(current_user)
    from app.models import OrgMembership
    result = await db.execute(
        select(
            User,
            TokenWallet.balance_tokens,
            TokenWallet.tokens_used_lifetime,
            func.coalesce(func.sum(APIKey.total_requests), 0).label("total_requests"),
            func.coalesce(func.sum(APIKey.total_blocked), 0).label("total_blocked"),
        )
        .outerjoin(TokenWallet, TokenWallet.user_id == User.id)
        .outerjoin(APIKey, APIKey.owner_id == User.id)
        .where(
            (User.org_id == current_user.org_id) |
            (User.id.in_(select(OrgMembership.user_id).where(OrgMembership.org_id == current_user.org_id)))
        )
        .group_by(User.id, TokenWallet.balance_tokens, TokenWallet.tokens_used_lifetime)
        .order_by(User.created_at.desc())
    )
    # For multi-team, is_admin is per-team via membership; override global is_admin for display
    # Fetch membership roles for this org
    mem_result = await db.execute(select(OrgMembership.user_id, OrgMembership.role).where(OrgMembership.org_id == current_user.org_id))
    role_map = {uid: role for uid, role in mem_result.all()}
    rows = result.all()
    out = []
    for u, bal, used, reqs, blocked in rows:
        per_team_admin = role_map.get(u.id)
        if per_team_admin is not None:
            is_admin = (per_team_admin == "admin")
        else:
            # No membership entry — fallback to primary org's global flag
            is_admin = bool(u.is_admin and u.org_id == current_user.org_id)
        out.append(AdminUserStats(
            id=u.id, email=u.email, full_name=u.full_name,
            is_admin=is_admin, is_active=u.is_active,
            last_login=u.last_login,
            tokens_balance=bal or 0, tokens_used=used or 0,
            total_requests=int(reqs), total_blocked=int(blocked),
        ))
    return out


@router.get("/api-keys", response_model=list[APIKeyOut])
async def list_org_api_keys(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    require_org_admin(current_user)
    result = await db.execute(
        select(APIKey)
        .where(APIKey.org_id == current_user.org_id)
        .order_by(APIKey.created_at.desc())
    )
    return result.scalars().all()


@router.post("/users/bulk", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_user_action(body: BulkUserAction, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    require_org_admin(current_user)
    if body.action not in ("enable", "disable", "remove"):
        raise HTTPException(status_code=400, detail=_t("admin.action_invalid"))
    for user_id in body.user_ids:
        if user_id == current_user.id:
            continue
        user = await db.get(User, user_id)
        if not user or user.org_id != current_user.org_id:
            continue
        if body.action == "enable":
            user.is_active = True
        elif body.action == "disable":
            user.is_active = False
        elif body.action == "remove":
            user.org_id = None
            user.is_admin = False
    await db.flush()


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_org_api_key(key_id: str, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    require_org_admin(current_user)
    key = await db.get(APIKey, key_id)
    if not key or key.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_t("api_key.not_found"))
    key.is_active = False
    await db.flush()


@router.get("/webhook-deliveries")
async def list_webhook_deliveries(
    current_user: CurrentUser,
    limit: int = Query(50, ge=1, le=500),
):
    """Recent outgoing webhook delivery attempts for this org (Redis ring
    buffer with in-memory fallback), newest first. Records include event,
    ok/http_status, attempts, and error."""
    require_org_admin(current_user)
    from app.services.webhook_deliveries import recent_deliveries  # noqa: PLC0415
    return await recent_deliveries(current_user.org_id, limit)


@router.get("/bans")
async def list_bans(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Active exploit auto-bans (API key + user). Auto-expire after TTL. Scoped to org."""
    require_org_admin(current_user)
    from app.services.api_key_protection import list_active_bans  # noqa: PLC0415
    bans = await list_active_bans()
    # scope to current org (keys + users)
    try:
        result = await db.execute(select(APIKey.id).where(APIKey.org_id == current_user.org_id))
        org_key_ids = {r[0] for r in result.all()}
        result2 = await db.execute(select(User.id).where(User.org_id == current_user.org_id))
        org_user_ids = {r[0] for r in result2.all()}
        bans = [b for b in bans if (b["type"] == "api_key" and b["id"] in org_key_ids) or (b["type"] == "user" and b["id"] in org_user_ids)]
    except Exception:
        pass
    return bans


@router.post("/bans/unban", status_code=204)
async def unban(
    body: dict,
    current_user: CurrentUser,
):
    """Manually lift a temporary ban. Body: {"api_key_id": "...", "user_id": "..."}"""
    require_org_admin(current_user)
    from app.services.api_key_protection import unban_api_key  # noqa: PLC0415
    api_key_id = (body.get("api_key_id") or "").strip()
    user_id = (body.get("user_id") or "").strip() or None
    if not api_key_id and not user_id:
        raise HTTPException(status_code=400, detail="api_key_id or user_id required")
    # if only api_key_id given, also clear its owner
    if api_key_id and not user_id:
        # best-effort: lookup owner
        from app.database import get_sessionmaker  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415
        try:
            sm = get_sessionmaker()
            async with sm() as db:
                key = await db.get(APIKey, api_key_id)
                if key:
                    user_id = key.owner_id
        except Exception:
            pass
    await unban_api_key(api_key_id or "", user_id)
    return None


@router.post("/replay/{request_id}", response_model=ReplayResponse)
async def replay_request(
    request_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Dry-run a stored request against the CURRENT org policy.

    No LLM call, no token deduction, no new RequestLog row — the input
    guardrail is re-run against the policy as it stands today.
    Follow-up (not implemented): cap the size of full_prompt pulled per call
    and rate-limit this endpoint, matching the rest of /admin.
    """
    require_org_admin(current_user)

    log = await db.get(RequestLog, request_id)
    if not log or log.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_t("admin.replay_not_found"))

    if log.full_prompt is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_t("admin.replay_no_full_prompt"),
        )

    # full_prompt is AES-GCM encrypted at rest when ENCRYPTION_KEY is set
    prompt = decrypt_prompt(log.full_prompt)

    # Current policy for the log's org (system defaults if none — mirrors /chat)
    from app.defaults import DEFAULT_INPUT_RULES
    result = await db.execute(select(OrgPolicy).where(OrgPolicy.org_id == log.org_id))
    policy = result.scalar_one_or_none()
    input_rules = policy.input_rules if policy else DEFAULT_INPUT_RULES

    # Replicate /chat's redaction-mode handling: in "redact" mode PII is
    # handled by the redactor, so the input guardrail skips its PII check.
    guardrail_rules = dict(input_rules)
    if input_rules.get("pii_redaction_mode", "block") == "redact":
        guardrail_rules["block_pii"] = False

    current = InputGuardrail(
        guardrail_rules,
        custom_rule_rego=policy.custom_rule_rego if policy else None,
        org_id=log.org_id,
    ).check(prompt)

    # Original verdict is the INPUT dimension only — an output-blocked row has
    # no LLM output to re-check in a dry run, so its input verdict stands.
    original_passed = log.input_passed is not False
    would_change = original_passed != current.allowed

    return ReplayResponse(
        request_id=log.id,
        original=ReplayOriginalVerdict(
            passed=original_passed,
            status=log.status,
            reason=log.input_block_reason,
        ),
        current=ReplayCurrentVerdict(
            passed=current.allowed,
            check=current.check,
            reason=current.reason,
            reason_code=current.reason_code,
            risk_score=current.risk_score,
        ),
        would_change_outcome=would_change,
        note=(
            "Dry-run against the current org policy. The LLM was not called, "
            "no tokens were deducted, and no new RequestLog row was written."
        ),
    )
