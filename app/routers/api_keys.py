"""
API Key management:
  POST   /api-keys          — create a new key (raw key shown once)
  GET    /api-keys          — list all keys for current user
  DELETE /api-keys/{id}     — revoke a key
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import CurrentUser, hash_api_key
from app.i18n import _t
from app.models import APIKey
from app.schemas import APIKeyCreate, APIKeyCreated, APIKeyOut

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


@router.post("", response_model=APIKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: APIKeyCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    raw_key = APIKey.generate_raw_key()
    prefix  = raw_key[:12]   # "grg_" + first 8 chars

    key = APIKey(
        name=body.name,
        key_prefix=prefix,
        key_hash=hash_api_key(raw_key),
        owner_id=current_user.id,
        org_id=current_user.org_id,
        expires_at=body.expires_at,
        scopes=body.scopes,
    )
    db.add(key)
    await db.flush()

    key_data = APIKeyOut.model_validate(key).model_dump()
    return APIKeyCreated(**key_data, raw_key=raw_key)


@router.get("", response_model=list[APIKeyOut])
async def list_api_keys(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(APIKey)
        .where(APIKey.owner_id == current_user.id)
        .order_by(APIKey.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(key_id: str, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    key = await db.get(APIKey, key_id)
    if not key or key.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail=_t("api_key.not_found"))
    key.is_active = False
    await db.flush()
