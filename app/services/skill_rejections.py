"""
Persist and resolve Skill Guard rejected access for the web review queue.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SkillAccessRejection, User
from app.i18n import _t
from app.services.skill_user_overrides import load_user_overrides, save_user_overrides
from guardrails.skill import SkillFinding
from guardrails.skill_overrides import SkillOverrides, finding_key

OVERRIDES_PATH = Path(".cursor/skill-guard-overrides.json")

RESOLVE_ACTIONS = frozenset({"allow_once", "allow_always", "keep_rejected"})


def _load_disk_overrides() -> SkillOverrides:
    if OVERRIDES_PATH.is_file():
        try:
            data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
            return SkillOverrides.from_dict(data)
        except (json.JSONDecodeError, OSError):
            pass
    return SkillOverrides(set(), set(), set())


def _save_disk_overrides(overrides: SkillOverrides) -> None:
    OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    OVERRIDES_PATH.write_text(json.dumps(overrides.to_dict(), indent=2) + "\n", encoding="utf-8")


def findings_from_json(raw: list) -> list[dict]:
    return raw if isinstance(raw, list) else []


async def record_rejection(
    db: AsyncSession,
    *,
    user: User,
    filename: str | None,
    source: str,
    findings: list[SkillFinding] | list[dict],
    summary: str | None,
    content_preview: str | None = None,
) -> SkillAccessRejection:
    if not findings:
        raise ValueError("findings required to record rejection")

    rows: list[dict] = []
    for f in findings:
        if isinstance(f, SkillFinding):
            rows.append({
                "finding_key": finding_key(f),
                "reason_code": f.reason_code,
                "severity": f.severity,
                "check": f.check,
                "line_number": f.line_number,
                "snippet": f.snippet,
                "explanation": f.reason or "",
            })
        else:
            rows.append(f)

    row = SkillAccessRejection(
        user_id=user.id,
        org_id=user.org_id,
        filename=filename,
        source=source,
        status="pending",
        findings=rows,
        rejection_summary=summary or f"Rejected access: {len(rows)} issue(s)",
        content_preview=(content_preview or "")[:500] or None,
    )
    db.add(row)
    await db.flush()
    return row


async def list_rejections(
    db: AsyncSession,
    user: User,
    *,
    status: str | None = "pending",
    limit: int = 50,
) -> list[SkillAccessRejection]:
    q = select(SkillAccessRejection).where(SkillAccessRejection.user_id == user.id)
    if status and status != "all":
        q = q.where(SkillAccessRejection.status == status)
    q = q.order_by(SkillAccessRejection.created_at.desc()).limit(min(limit, 100))
    result = await db.execute(q)
    return list(result.scalars().all())


async def resolve_rejection(
    db: AsyncSession,
    user: User,
    rejection_id: str,
    action: str,
    note: str | None = None,
) -> SkillAccessRejection:
    if action not in RESOLVE_ACTIONS:
        raise HTTPException(status_code=400, detail=_t("skills.action_invalid"))

    row = await db.get(SkillAccessRejection, rejection_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail=_t("skills.not_found"))

    if row.status != "pending":
        raise HTTPException(status_code=400, detail=_t("skills.already_resolved"))

    findings = findings_from_json(row.findings)
    overrides = await load_user_overrides(db, user.id)
    # Also merge repo-local file if present (dev machine)
    disk = _load_disk_overrides()
    overrides.session_allow_keys |= disk.session_allow_keys
    overrides.always_allow_keys |= disk.always_allow_keys
    overrides.always_allow_reason_codes |= disk.always_allow_reason_codes

    if action in ("allow_once", "allow_always"):
        for f in findings:
            key = f.get("finding_key") or f"{f.get('reason_code')}:{f.get('line_number') or 0}"
            code = f.get("reason_code", "")
            if action == "allow_once":
                overrides.session_allow_keys.add(key)
            else:
                overrides.always_allow_keys.add(key)
                if code:
                    overrides.always_allow_reason_codes.add(code)
        await save_user_overrides(db, user.id, overrides)
        _save_disk_overrides(overrides)
        row.status = "unblocked_once" if action == "allow_once" else "unblocked_always"
    else:
        row.status = "kept_rejected"

    row.resolved_action = action
    row.resolver_note = (note or "").strip() or None
    row.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    return row
