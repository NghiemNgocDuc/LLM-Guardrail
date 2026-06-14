"""
Organisation settings:
  GET   /org          — current org details
  PATCH /org          — rename org (admin only)
"""
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import CurrentUser
from app.models import Organization
from app.schemas import OrgOut

router = APIRouter(prefix="/org", tags=["Organisation"])


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]


class OrgUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


@router.get("", response_model=OrgOut)
async def get_org(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail="No organisation associated with this account")
    org = await db.get(Organization, current_user.org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    return org


@router.patch("", response_model=OrgOut)
async def update_org(body: OrgUpdate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail="No organisation")
    org = await db.get(Organization, current_user.org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    new_slug = _slugify(body.name)
    existing = await db.execute(
        select(Organization).where(Organization.slug == new_slug, Organization.id != org.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Organisation name already taken")

    org.name = body.name
    org.slug = new_slug
    await db.flush()
    return org
