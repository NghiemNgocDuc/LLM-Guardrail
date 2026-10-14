"""CRUD for ManagedSkill — per-org synced SKILL.md files."""
from __future__ import annotations

import hashlib
import json
import re
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ManagedSkill, ManagedSkillVersion, Organization


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _slugify(raw: str) -> str:
    s = re.sub(r"\s+", "_", (raw or "").strip().lower())
    s = re.sub(r"_+", "_", s).strip("_")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", s):
        raise HTTPException(status_code=400, detail="slug must contain 1–80 letters, digits, underscores or hyphens, starting with a letter or digit")
    if s in {"metrics", "check-conflict", "check-identical-block", "test-new-block", "generate-tests"}:
        raise HTTPException(status_code=400, detail="This slug is reserved for a skill API endpoint")
    return s


def skill_revision(row: ManagedSkill) -> str:
    """Editor concurrency token also covers metadata changes without a content bump."""
    snapshot = [row.slug, row.name, row.description, row.content_hash, row.version, row.update_mode]
    return hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _validate_text(name: str | None, description: str | None, content: str | None) -> None:
    if name is not None and (not name.strip() or len(name) > 120):
        raise HTTPException(status_code=400, detail="name must contain 1–120 characters")
    if description is not None and len(description) > 500:
        raise HTTPException(status_code=400, detail="description must be at most 500 characters")
    if content is not None and (not content.strip() or len(content) > 256_000):
        raise HTTPException(status_code=400, detail="content must contain 1–256000 characters")


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
    if content is None:
        raise HTTPException(status_code=400, detail="content is required")
    _validate_text(name or slug, description, content)
    if update_mode not in ("overwrite", "versioned"):
        raise HTTPException(status_code=400, detail="update_mode must be overwrite or versioned")
    # Serialize creation per org so the cap cannot be exceeded by concurrent creates.
    organization = await db.execute(select(Organization).where(Organization.id == org_id).with_for_update())
    if organization.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    existing = await get_managed_skill(db, org_id, slug)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Skill '{slug}' already exists. Use PUT to update.")
    count = await db.scalar(select(func.count()).select_from(ManagedSkill).where(ManagedSkill.org_id == org_id))
    if (count or 0) >= 500:
        raise HTTPException(status_code=400, detail="Team terms cap reached — max 500 terms per team.")

    h = _hash(content)
    row = ManagedSkill(
        id=str(uuid.uuid4()),
        org_id=org_id,
        slug=slug,
        name=name.strip() or slug,
        description=description or "",
        content=content,
        content_hash=h,
        version=1,
        update_mode=update_mode,
        created_by=created_by,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Skill '{slug}' already exists. Reload the skill list.") from error
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
    expected_version: int | None = None,
    expected_revision: str | None = None,
) -> ManagedSkill:
    _validate_text(name, description, content)
    result = await db.execute(select(ManagedSkill).where(ManagedSkill.org_id == org_id, ManagedSkill.slug == slug.strip().lower()).with_for_update().execution_options(populate_existing=True))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found")

    if expected_version is not None and row.version != expected_version or expected_revision is not None and skill_revision(row) != expected_revision:
        raise HTTPException(status_code=409, detail="This skill changed since you opened it. Reload the latest version before saving your draft.")

    if update_mode is not None and update_mode not in ("overwrite", "versioned"):
        raise HTTPException(status_code=400, detail="update_mode must be overwrite or versioned")

    changed = False
    if name is not None and name.strip() and name.strip() != row.name:
        row.name = name.strip()
        changed = True
    if description is not None and description != row.description:
        row.description = description
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
        .where(ManagedSkillVersion.org_id == org_id, ManagedSkillVersion.skill_id == row.id)
        .order_by(ManagedSkillVersion.version.desc())
    )
    return list(result.scalars().all())
