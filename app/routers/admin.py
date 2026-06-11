import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import CurrentUser, hash_password
from app.models import APIKey, User
from app.schemas import AdminInviteUser, AdminUserUpdate, APIKeyOut, UserOut
from app.config import get_settings
from app.services.auth_tokens import TOKEN_PURPOSE_RESET, build_action_url, create_auth_token
from app.services.email import send_password_reset_email
from app.services.token_wallet import ensure_wallet

settings = get_settings()
router = APIRouter(prefix="/admin", tags=["Admin"])


def require_org_admin(user: User) -> None:
    if not user.is_admin or not user.org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization admin access required")


@router.post("/users/invite", response_model=UserOut)
async def invite_user(
    body: AdminInviteUser,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    require_org_admin(current_user)

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    temp_password = secrets.token_urlsafe(16)
    user = User(
        email=body.email,
        hashed_password=hash_password(temp_password),
        full_name=body.full_name,
        is_admin=body.is_admin,
        org_id=current_user.org_id,
        email_verified=False,  # They will verify when setting password
    )
    db.add(user)
    await db.flush()

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.id == current_user.id and body.is_admin is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot remove your own admin role")
    if user.id == current_user.id and body.is_active is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot disable your own account")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)

    await db.flush()
    return user


@router.get("/api-keys", response_model=list[APIKeyOut])
async def list_org_api_keys(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    require_org_admin(current_user)
    result = await db.execute(
        select(APIKey)
        .where(APIKey.org_id == current_user.org_id)
        .order_by(APIKey.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_org_api_key(key_id: str, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    require_org_admin(current_user)
    key = await db.get(APIKey, key_id)
    if not key or key.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    key.is_active = False
    await db.flush()
