"""Server approvals, scoped to a user, workspace, and exact scanned finding.

The local CLI's SkillOverrides file is deliberately separate. Legacy broad
reason/line approvals have no trustworthy tenant/content identity and are not
accepted by the hosted API. JSON versioning avoids a database migration.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OrgMembership, User, UserSkillGuardOverrides
from guardrails.skill import SkillFinding, SkillScanResult
from guardrails.skill_overrides import SkillScanDecision

APPROVAL_VERSION = 2
_DIGEST = re.compile(r"^[a-f0-9]{64}$")


def content_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def approval_key(filename: str | None, digest: str, finding: SkillFinding | dict) -> str:
    """No category-wide or same-line equivalence: bind the exact content too."""
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        raise ValueError("a valid content digest is required")
    fields = ("reason_code", "check", "severity", "line_number", "snippet")
    detail = {name: getattr(finding, name) if isinstance(finding, SkillFinding) else finding.get(name) for name in fields}
    if not detail["reason_code"] or not detail["check"] or not detail["severity"]:
        raise ValueError("complete finding identity is required")
    payload = {"filename": filename or "", "content_sha256": digest, **detail}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def stored_approval_key(filename: str | None, finding: dict) -> str:
    """Read identity only from a server-persisted rejection, never scan input.

    Private records omit filenames and snippets after the server computes this
    key. Keeping it separate from approval_key prevents reported JSON from
    injecting a precomputed approval into normal enforcement.
    """
    if finding.get("private_identity_version") == 1:
        key = finding.get("server_approval_key")
        if not isinstance(key, str) or not _DIGEST.fullmatch(key):
            raise ValueError("private rejection identity is missing")
        return key
    return approval_key(filename, finding.get("content_sha256"), finding)


def _store(raw: object) -> dict:
    if not isinstance(raw, dict) or raw.get("version") != APPROVAL_VERSION or not isinstance(raw.get("org_scopes"), dict):
        return {"version": APPROVAL_VERSION, "org_scopes": {}}
    return copy.deepcopy(raw)


def _scope(org_id: str | None) -> str:
    return org_id or "__personal__"


def _always_keys(value: object) -> set[str]:
    return {key for key in value if isinstance(key, str) and _DIGEST.fullmatch(key)} if isinstance(value, list) else set()


async def lock_approval_owner(db: AsyncSession, user_id: str, org_id: str | None, *, require_current_org: bool = True) -> None:
    # Lock the existing user first, including when its overrides row does not
    # exist yet. This serializes grants and consumption across processes and
    # prevents concurrent first inserts or lost JSON updates.
    owner = (await db.execute(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if not owner or not owner.is_active:
        raise HTTPException(status_code=403, detail="Approval owner is no longer active in this workspace")
    if owner.org_id != org_id:
        if require_current_org or not org_id:
            raise HTTPException(status_code=403, detail="Approval owner is no longer active in this workspace")
        membership = (await db.execute(select(OrgMembership).where(OrgMembership.user_id == user_id, OrgMembership.org_id == org_id))).scalar_one_or_none()
        if not membership:
            raise HTTPException(status_code=403, detail="Approval owner is not a member of this workspace")


async def _row(db: AsyncSession, user_id: str) -> UserSkillGuardOverrides | None:
    return (await db.execute(select(UserSkillGuardOverrides).where(UserSkillGuardOverrides.user_id == user_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()


async def load_user_overrides(
    db: AsyncSession,
    user_id: str,
    *,
    org_id: str | None,
    filename: str | None,
    digest: str,
    findings: list[SkillFinding],
    consume_once: bool = False,
) -> set[str]:
    """Return exact approved identities; optionally consume one scan attempt."""
    if not findings:
        return set()
    await lock_approval_owner(db, user_id, org_id, require_current_org=False)
    row = await _row(db, user_id)
    if not row:
        return set()
    store = _store(row.overrides)
    scope = store["org_scopes"].get(_scope(org_id), {})
    if not isinstance(scope, dict):
        return set()
    once = scope.get("once") if isinstance(scope.get("once"), dict) else {}
    always = _always_keys(scope.get("always"))
    allowed: set[str] = set()
    consumed: set[str] = set()
    for finding in findings:
        key = approval_key(filename, digest, finding)
        allowance = once.get(key, 0)
        if key in always:
            allowed.add(key)
        elif isinstance(allowance, int) and not isinstance(allowance, bool) and allowance > 0:
            allowed.add(key)
            if consume_once and key not in consumed:
                if allowance == 1:
                    once.pop(key, None)
                else:
                    once[key] = allowance - 1
                consumed.add(key)
    if consumed:
        scope["once"] = once
        row.overrides = store
        row.updated_at = datetime.now(timezone.utc)
        await db.flush()
    return allowed


async def apply_saved_scan_overrides(db: AsyncSession, user: User, result: SkillScanResult, content: str, filename: str | None) -> SkillScanDecision:
    """Shared hosted enforcement for scans and managed-skill distribution.

    ``user`` is the authenticated actor (or a key-authenticated, verified
    membership context with id/org_id). The caller owns the transaction and
    must commit consumption and any recorded rejection before returning.
    """
    digest = content_digest(content)
    approved = await load_user_overrides(db, user.id, org_id=user.org_id, filename=filename, digest=digest, findings=result.findings, consume_once=True)
    allowed = [finding for finding in result.findings if approval_key(filename, digest, finding) in approved]
    blocking = [finding for finding in result.findings if approval_key(filename, digest, finding) not in approved]
    return SkillScanDecision(raw=result, blocking=blocking, allowed=allowed, safe=not blocking, blocked=bool(blocking))


async def save_user_overrides(
    db: AsyncSession,
    user_id: str,
    *,
    org_id: str | None,
    keys: set[str],
    action: str,
) -> None:
    if action not in {"allow_once", "allow_always"} or not keys or any(not _DIGEST.fullmatch(key) for key in keys):
        raise ValueError("exact approval identities and a supported action are required")
    await lock_approval_owner(db, user_id, org_id)
    row = await _row(db, user_id)
    store = _store(row.overrides if row else None)
    scope = store["org_scopes"].setdefault(_scope(org_id), {"once": {}, "always": []})
    if not isinstance(scope, dict):
        scope = {"once": {}, "always": []}
        store["org_scopes"][_scope(org_id)] = scope
    once = scope.get("once") if isinstance(scope.get("once"), dict) else {}
    always = _always_keys(scope.get("always"))
    if action == "allow_once":
        for key in keys:
            current = once.get(key, 0)
            once[key] = (current if isinstance(current, int) and not isinstance(current, bool) and current > 0 else 0) + 1
    else:
        always |= keys
    scope.update(once=once, always=sorted(always))
    if row:
        row.overrides = store
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(UserSkillGuardOverrides(user_id=user_id, overrides=store))
    await db.flush()


async def revoke_user_overrides(db: AsyncSession, user_id: str, *, org_id: str | None, keys: set[str]) -> None:
    """A new explicit rejection revokes only its exact prior approvals."""
    if not keys:
        return
    await lock_approval_owner(db, user_id, org_id)
    row = await _row(db, user_id)
    if not row:
        return
    store = _store(row.overrides)
    scope = store["org_scopes"].get(_scope(org_id))
    if not isinstance(scope, dict):
        return
    once = scope.get("once") if isinstance(scope.get("once"), dict) else {}
    for key in keys:
        once.pop(key, None)
    scope.update(once=once, always=sorted(_always_keys(scope.get("always")) - keys))
    row.overrides = store
    row.updated_at = datetime.now(timezone.utc)
    await db.flush()
