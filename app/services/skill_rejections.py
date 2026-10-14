"""
Persist and resolve Skill Guard rejected access for the web review queue.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SkillAccessRejection, User
from app.config import get_settings
from app.i18n import _t
from app.services.skill_user_overrides import approval_key, stored_approval_key, lock_approval_owner, revoke_user_overrides, save_user_overrides
from app.services.private_audit import PRIVATE_FILENAME, private_reason_code
from guardrails.skill import SkillFinding, redact_skill_excerpt
from guardrails.skill_overrides import finding_key
from guardrails.skill_messages import explain_finding

RESOLVE_ACTIONS = frozenset({"allow_once", "allow_always", "keep_rejected"})


def findings_from_json(raw: list) -> list[dict]:
    return [finding for finding in raw if isinstance(finding, dict)] if isinstance(raw, list) else []


async def record_rejection(
    db: AsyncSession,
    *,
    user: User,
    filename: str | None,
    source: str,
    findings: list[SkillFinding] | list[dict],
    summary: str | None,
    content_preview: str | None = None,
    content_sha256: str | None = None,
) -> SkillAccessRejection:
    if not findings:
        raise ValueError("findings required to record rejection")

    private = getattr(get_settings(), "PRIVATE_MODE", False)
    if private and (not isinstance(content_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", content_sha256)):
        content_sha256 = None

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
            rows.append(dict(f))

    for finding in rows:
        # Reported keys are untrusted. Every private identity is calculated
        # here before evidence and the original filename are discarded.
        finding.pop("server_approval_key", None)
        finding.pop("private_identity_version", None)
        if private:
            try:
                key = approval_key(filename, content_sha256, finding)
            except (ValueError, TypeError):
                key = None
            code = private_reason_code(finding.get("reason_code")) or "guardrail_event"
            severity = finding.get("severity")
            line = finding.get("line_number")
            finding.clear()
            finding.update(
                reason_code=code,
                severity=severity if isinstance(severity, str) and severity in {"low", "medium", "high", "critical"} else "high",
                check="Skill Guard",
                line_number=line if isinstance(line, int) and not isinstance(line, bool) and line > 0 else None,
                snippet="",
                explanation=explain_finding(code, "Skill Guard"),
                private_identity_version=1,
                server_approval_key=key,
            )
        # Persist immutable identity with each finding in the existing JSON
        # column. A reported CLI digest is client-attested; scan/create derive
        # their digest on the server. Both require an explicit own-user review.
        finding["content_sha256"] = content_sha256
        finding["approval_org_id"] = user.org_id
        for field in ("snippet", "reason", "explanation"):
            if isinstance(finding.get(field), str):
                finding[field] = redact_skill_excerpt(finding[field], max_length=72 if field == "snippet" else 2000)

    await lock_approval_owner(db, user.id, user.org_id, require_current_org=False)
    try:
        identities = {stored_approval_key(PRIVATE_FILENAME if private else filename, finding) for finding in rows}
    except (ValueError, TypeError):
        identities = set()
    if identities:
        # Owner lock serializes retries across workers. Only a pending case
        # with the complete exact finding set is reused; its original evidence
        # and creation time remain immutable. A resolved case is never reused.
        candidates = (await db.execute(select(SkillAccessRejection).where(
            SkillAccessRejection.user_id == user.id,
            SkillAccessRejection.org_id == user.org_id,
            SkillAccessRejection.filename == (PRIVATE_FILENAME if private else filename),
            SkillAccessRejection.status == "pending",
            SkillAccessRejection.findings[0]["content_sha256"].as_string() == content_sha256,
        ))).scalars().all()
        for candidate in candidates:
            previous = findings_from_json(candidate.findings)
            try:
                prior_identities = {stored_approval_key(candidate.filename, finding) for finding in previous}
            except (ValueError, TypeError):
                continue
            if identities == prior_identities:
                return candidate

    row = SkillAccessRejection(
        user_id=user.id,
        org_id=user.org_id,
        filename=PRIVATE_FILENAME if private else filename,
        source=source if not private or source in {"api_scan", "managed_download", "managed_write", "git_push", "cli", "report"} else "report",
        status="pending",
        findings=rows,
        rejection_summary=f"Rejected access: {len(rows)} issue(s). Content omitted in private mode." if private else redact_skill_excerpt(summary or f"Rejected access: {len(rows)} issue(s)", max_length=2000),
        content_preview=None if private else (redact_skill_excerpt(content_preview or "", max_length=500) or None),
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
    q = select(SkillAccessRejection).where(SkillAccessRejection.user_id == user.id, SkillAccessRejection.org_id == user.org_id)
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

    await lock_approval_owner(db, user.id, user.org_id)
    row = (await db.execute(select(SkillAccessRejection).where(
        SkillAccessRejection.id == rejection_id,
        SkillAccessRejection.user_id == user.id,
        SkillAccessRejection.org_id == user.org_id,
    ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=_t("skills.not_found"))

    if row.status != "pending":
        if row.resolved_action == action:
            return row
        raise HTTPException(status_code=409, detail=_t("skills.already_resolved"))

    findings = findings_from_json(row.findings)
    if action in ("allow_once", "allow_always"):
        try:
            if not findings or any("approval_org_id" not in finding or finding["approval_org_id"] != user.org_id for finding in findings):
                raise ValueError("workspace identity is missing")
            keys = {stored_approval_key(row.filename, finding) for finding in findings}
        except (ValueError, TypeError):
            raise HTTPException(status_code=409, detail="This rejection has no exact content identity. Re-scan or re-report the file before approving it.") from None
        await save_user_overrides(db, user.id, org_id=user.org_id, keys=keys, action=action)
        row.status = "unblocked_once" if action == "allow_once" else "unblocked_always"
    else:
        keys: set[str] = set()
        for finding in findings:
            if "approval_org_id" not in finding or finding["approval_org_id"] != user.org_id:
                continue
            try:
                keys.add(stored_approval_key(row.filename, finding))
            except (ValueError, TypeError):
                continue
        await revoke_user_overrides(db, user.id, org_id=user.org_id, keys=keys)
        row.status = "kept_rejected"

    row.resolved_action = action
    row.resolver_note = None if getattr(get_settings(), "PRIVATE_MODE", False) else (redact_skill_excerpt((note or "").strip(), max_length=2000) or None)
    row.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    return row
