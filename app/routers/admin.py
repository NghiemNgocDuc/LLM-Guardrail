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


def require_org_admin(user: User) -> None:
    if not user.is_admin or not user.org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_t("admin.access_required"))


@router.post("/users/invite", response_model=UserOut)
async def invite_user(
    body: AdminInviteUser,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    require_org_admin(current_user)

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

    # Admin transfer: inviting someone as admin hands over the role
    if body.is_admin:
        current_user.is_admin = False

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

@router.get("/users", response_model=list[UserOut])
async def list_org_users(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    require_org_admin(current_user)
    result = await db.execute(
        select(User)
        .where(User.org_id == current_user.org_id)
        .order_by(User.created_at.desc())
    )
    return result.scalars().all()


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_org_user(
    user_id: str,
    body: AdminUserUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    require_org_admin(current_user)
    user = await db.get(User, user_id)
    if not user or user.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_t("admin.user_not_found"))

    if user.id == current_user.id and body.is_admin is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_t("admin.cannot_remove_own_admin"))
    if user.id == current_user.id and body.is_active is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_t("admin.cannot_disable_self"))

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)

    # Admin transfer: promoting another user to admin hands over the role
    if body.is_admin and user.id != current_user.id:
        current_user.is_admin = False

    await db.flush()
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_org_user(user_id: str, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    require_org_admin(current_user)
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_t("admin.cannot_remove_self"))
    user = await db.get(User, user_id)
    if not user or user.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_t("admin.user_not_found"))
    user.org_id = None
    user.is_admin = False
    await db.flush()


@router.get("/users/stats", response_model=list[AdminUserStats])
async def user_stats(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    require_org_admin(current_user)
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
        .where(User.org_id == current_user.org_id)
        .group_by(User.id, TokenWallet.balance_tokens, TokenWallet.tokens_used_lifetime)
        .order_by(User.created_at.desc())
    )
    return [
        AdminUserStats(
            id=u.id, email=u.email, full_name=u.full_name,
            is_admin=u.is_admin, is_active=u.is_active,
            last_login=u.last_login,
            tokens_balance=bal or 0, tokens_used=used or 0,
            total_requests=int(reqs), total_blocked=int(blocked),
        )
        for u, bal, used, reqs, blocked in result.all()
    ]


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
