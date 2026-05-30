from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import CurrentUser
from app.models import APIKey, User
from app.schemas import AdminUserUpdate, APIKeyOut, UserOut

router = APIRouter(prefix="/admin", tags=["Admin"])


def require_org_admin(user: User) -> None:
    if not user.is_admin or not user.org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization admin access required")


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
