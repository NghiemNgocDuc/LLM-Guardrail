"""CRUD for ManagedSkill — per-org synced SKILL.md files."""
from __future__ import annotations

import hashlib
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ManagedSkill, ManagedSkillVersion, User


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _slugify(raw: str) -> str:
    s = (raw or "").strip().lower().replace(" ", "_")
    # keep only [a-z0-9_-]
    import re as _re
    s = _re.sub(r"[^a-z0-9_-]", "", s)
    s = _re.sub(r"_+", "_", s).strip("_")
    return s or "skill"


async def list_managed_skills(db: AsyncSession, org_id: str) -> list[ManagedSkill]:
    result = await db.execute(select(ManagedSkill).where(ManagedSkill.org_id == org_id).order_by(ManagedSkill.slug))
    return list(result.scalars().all())


async def get_managed_skill(db: AsyncSession, org_id: str, slug: str) -> ManagedSkill | None:
    s = slug.strip().lower()
    result = await db.execute(select(ManagedSkill).where(ManagedSkill.org_id == org_id, ManagedSkill.slug == s))
    return result.scalar_one_or_none()


async def create_managed_skill(
    db: AsyncSession,
    *,
    org_id: str,
    slug: str,
    name: str,
    description: str,
    content: str,
    update_mode: str = "overwrite",
    created_by: str | None = None,
) -> ManagedSkill:
    slug = _slugify(slug)
    if not slug:
        raise HTTPException(status_code=400, detail="slug is required")
    if not content or not content.strip():
        raise HTTPException(status_code=400, detail="content is required")
    if update_mode not in ("overwrite", "versioned"):
        raise HTTPException(status_code=400, detail="update_mode must be overwrite or versioned")
    existing = await get_managed_skill(db, org_id, slug)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Skill '{slug}' already exists. Use PUT to update.")

    h = _hash(content)
    row = ManagedSkill(
        id=str(uuid.uuid4()),
        org_id=org_id,
        slug=slug,
        name=name.strip() or slug,
        description=(description or "")[:500],
        content=content,
        content_hash=h,
        version=1,
        update_mode=update_mode,
        created_by=created_by,
    )
    db.add(row)
    await db.flush()
    # version history
    ver = ManagedSkillVersion(
        id=str(uuid.uuid4()),
        skill_id=row.id,
        org_id=org_id,
        slug=slug,
        version=1,
        content=content,
        content_hash=h,
        update_mode=update_mode,
        created_by=created_by,
    )
    db.add(ver)
    await db.flush()
    return row


async def update_managed_skill(
    db: AsyncSession,
    *,
    org_id: str,
    slug: str,
    name: str | None = None,
    description: str | None = None,
    content: str | None = None,
    update_mode: str | None = None,
    updated_by: str | None = None,
) -> ManagedSkill:
    row = await get_managed_skill(db, org_id, slug)
    if not row:
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found")

    if update_mode is not None and update_mode not in ("overwrite", "versioned"):
        raise HTTPException(status_code=400, detail="update_mode must be overwrite or versioned")

    changed = False
    if name is not None and name.strip() and name.strip() != row.name:
        row.name = name.strip()
        changed = True
    if description is not None and description[:500] != row.description:
        row.description = (description or "")[:500]
        changed = True
    if update_mode is not None and update_mode != row.update_mode:
        row.update_mode = update_mode
        changed = True

    if content is not None:
        if not content.strip():
            raise HTTPException(status_code=400, detail="content cannot be empty")
        h = _hash(content)
        if h != row.content_hash:
            row.content = content
            row.content_hash = h
            row.version = (row.version or 1) + 1
            # add version history row for the new version
            ver = ManagedSkillVersion(
                id=str(uuid.uuid4()),
                skill_id=row.id,
                org_id=org_id,
                slug=row.slug,
                version=row.version,
                content=content,
                content_hash=h,
                update_mode=row.update_mode,
                created_by=updated_by,
            )
            db.add(ver)
            changed = True

    if changed:
        from datetime import datetime, timezone
        row.updated_at = datetime.now(timezone.utc)
        await db.flush()
    return row


async def delete_managed_skill(db: AsyncSession, *, org_id: str, slug: str) -> None:
    row = await get_managed_skill(db, org_id, slug)
    if not row:
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found")
    await db.delete(row)
    await db.flush()


async def list_skill_versions(db: AsyncSession, org_id: str, slug: str) -> list[ManagedSkillVersion]:
    row = await get_managed_skill(db, org_id, slug)
    if not row:
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found")
    result = await db.execute(
        select(ManagedSkillVersion)
        .where(ManagedSkillVersion.org_id == org_id, ManagedSkillVersion.slug == slug)
        .order_by(ManagedSkillVersion.version.desc())
    )
    return list(result.scalars().all())
