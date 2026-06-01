"""Per-user Skill Guard overrides (web unblock → persisted for API scans)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserSkillGuardOverrides
from guardrails.skill_overrides import SkillOverrides


async def load_user_overrides(db: AsyncSession, user_id: str) -> SkillOverrides:
    row = await db.get(UserSkillGuardOverrides, user_id)
    if not row:
        return SkillOverrides(set(), set(), set())
    return SkillOverrides.from_dict(row.overrides)


async def save_user_overrides(db: AsyncSession, user_id: str, overrides: SkillOverrides) -> None:
    row = await db.get(UserSkillGuardOverrides, user_id)
    data = overrides.to_dict()
    if row:
        row.overrides = data
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(UserSkillGuardOverrides(user_id=user_id, overrides=data))
    await db.flush()
