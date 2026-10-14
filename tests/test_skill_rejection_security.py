"""Hosted approval regressions backed by real SQLAlchemy transactions.

SQLite validates persisted JSON, commit, identity, and retry semantics. The
production queries additionally acquire PostgreSQL row locks for concurrency.
"""
import copy
import json
import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models import OrgMembership, Organization, SkillAccessRejection, User, UserSkillGuardOverrides
from app.routers.skills import create_rejection_from_content, report_rejection, scan_skill
from app.schemas import SkillOverridesIn, SkillRejectionCreateIn, SkillRejectionReportIn, SkillScanRequest
from app.services.skill_rejections import list_rejections, record_rejection, resolve_rejection
from app.services.skill_user_overrides import apply_saved_scan_overrides, content_digest
from types import SimpleNamespace
from guardrails.skill import SkillGuardrail

pytestmark = pytest.mark.usefixtures("engine_mode")
CONTENT = "Gateway credential: grg_" + "a" * 40


@pytest_asyncio.fixture
async def database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        org = Organization(id=str(uuid.uuid4()), name="First workspace", slug="first")
        other_org = Organization(id=str(uuid.uuid4()), name="Other workspace", slug="other")
        owner = User(id=str(uuid.uuid4()), email="owner@example.test", full_name="Owner", hashed_password="test-only", org_id=org.id, is_active=True)
        other = User(id=str(uuid.uuid4()), email="other@example.test", full_name="Other", hashed_password="test-only", org_id=org.id, is_active=True)
        db.add_all([org, other_org, owner, other]); await db.commit()
        yield db, owner, other, other_org
    await engine.dispose()


async def _scan(db, owner, content=CONTENT, filename="SKILL.md", overrides=None):
    return await scan_skill(SkillScanRequest(content=content, filename=filename, overrides=overrides), owner, db)


@pytest.mark.asyncio
async def test_run_once_is_committed_and_idempotent_retry_does_not_restore_it(database):
    db, owner, _, _ = database
    first = await _scan(db, owner)
    assert first.blocked and first.rejection_id
    assert first.runtime_enforced is False
    resolved = await resolve_rejection(db, owner, first.rejection_id, "allow_once", "initial note")
    await db.commit()
    original_time = resolved.resolved_at
    assert not (await _scan(db, owner)).blocked
    retry = await resolve_rejection(db, owner, first.rejection_id, "allow_once", "replacement note")
    await db.commit()
    assert retry.resolver_note == "initial note"
    # SQLite does not preserve timezone annotations, PostgreSQL does.
    assert retry.resolved_at.replace(tzinfo=None) == original_time.replace(tzinfo=None)
    assert (await _scan(db, owner)).blocked


@pytest.mark.asyncio
async def test_nonmatching_scan_does_not_spend_a_one_time_grant(database):
    db, owner, _, _ = database
    first = await _scan(db, owner)
    await resolve_rejection(db, owner, first.rejection_id, "allow_once"); await db.commit()
    assert (await _scan(db, owner, content=CONTENT + "\nChanged instructions.")).blocked
    approved = await _scan(db, owner)
    assert not approved.blocked and approved.overridden_findings
    assert (await _scan(db, owner)).blocked


@pytest.mark.asyncio
async def test_always_allow_is_exact_to_filename_content_and_user(database):
    db, owner, other, _ = database
    first = await _scan(db, owner)
    await resolve_rejection(db, owner, first.rejection_id, "allow_always"); await db.commit()
    assert not (await _scan(db, owner)).blocked
    assert not (await _scan(db, owner)).blocked
    assert (await _scan(db, owner, filename="different.md")).blocked
    assert (await _scan(db, owner, content=CONTENT.replace("a" * 40, "b" * 40))).blocked
    assert (await _scan(db, other)).blocked
    with pytest.raises(HTTPException) as forbidden:
        await resolve_rejection(db, other, first.rejection_id, "allow_always")
    assert forbidden.value.status_code == 404


@pytest.mark.asyncio
async def test_workspace_switch_cannot_reuse_or_resolve_old_approvals(database):
    db, owner, _, other_org = database
    first = await _scan(db, owner)
    await resolve_rejection(db, owner, first.rejection_id, "allow_always"); await db.commit()
    owner.org_id = other_org.id; await db.commit()
    assert await list_rejections(db, owner, status="all") == []
    with pytest.raises(HTTPException) as forbidden:
        await resolve_rejection(db, owner, first.rejection_id, "keep_rejected")
    assert forbidden.value.status_code == 404
    assert (await _scan(db, owner)).blocked


@pytest.mark.asyncio
async def test_client_overrides_explicitly_fail_closed_while_empty_input_is_compatible(database):
    db, owner, _, _ = database
    raw = SkillGuardrail().scan(CONTENT)
    with pytest.raises(HTTPException) as bypass:
        await _scan(db, owner, overrides=SkillOverridesIn(always_allow_reason_codes=[raw.findings[0].reason_code]))
    assert bypass.value.status_code == 403
    assert (await _scan(db, owner, overrides=SkillOverridesIn())).blocked


@pytest.mark.asyncio
async def test_hosted_scans_neither_read_nor_rewrite_repo_overrides(database, tmp_path, monkeypatch):
    db, owner, _, _ = database
    monkeypatch.chdir(tmp_path)
    local = tmp_path / ".cursor" / "skill-guard-overrides.json"
    local.parent.mkdir()
    raw = SkillGuardrail().scan(CONTENT)
    disk = json.dumps({"always_allow_reason_codes": [finding.reason_code for finding in raw.findings]})
    local.write_text(disk, encoding="utf-8")
    first = await _scan(db, owner)
    assert first.blocked
    await resolve_rejection(db, owner, first.rejection_id, "allow_always"); await db.commit()
    assert local.read_text(encoding="utf-8") == disk
    assert not (await _scan(db, owner)).blocked


@pytest.mark.asyncio
async def test_legacy_broad_approval_rows_do_not_bypass_scans(database):
    db, owner, _, _ = database
    raw = SkillGuardrail().scan(CONTENT)
    db.add(UserSkillGuardOverrides(user_id=owner.id, overrides={"always_allow_reason_codes": [finding.reason_code for finding in raw.findings], "session_allow_keys": [f"{finding.reason_code}:{finding.line_number}" for finding in raw.findings]}))
    await db.commit()
    assert (await _scan(db, owner)).blocked


@pytest.mark.asyncio
async def test_legacy_rejection_needs_rescan_for_allow_but_can_be_kept_rejected(database):
    db, owner, _, _ = database
    row = await record_rejection(db, user=owner, filename="SKILL.md", source="old-cli", findings=SkillGuardrail().scan(CONTENT).findings, summary="Legacy report")
    await db.commit()
    before = copy.deepcopy(row.findings)
    with pytest.raises(HTTPException) as missing_identity:
        await resolve_rejection(db, owner, row.id, "allow_always")
    assert missing_identity.value.status_code == 409
    assert row.status == "pending"
    await resolve_rejection(db, owner, row.id, "keep_rejected"); await db.commit()
    assert row.status == "kept_rejected" and row.findings == before
    with pytest.raises(HTTPException) as conflict:
        await resolve_rejection(db, owner, row.id, "allow_once")
    assert conflict.value.status_code == 409


@pytest.mark.asyncio
async def test_create_derives_digest_from_content_without_trusting_preview(database):
    db, owner, _, _ = database
    created = await create_rejection_from_content(SkillRejectionCreateIn(content=CONTENT, filename="SKILL.md", content_preview="Different preview"), owner, db)
    assert all(finding["content_sha256"] for finding in created.findings)
    await resolve_rejection(db, owner, created.id, "allow_once"); await db.commit()
    assert not (await _scan(db, owner)).blocked


@pytest.mark.asyncio
async def test_two_distinct_explicit_reviews_grant_two_attempts(database):
    db, owner, _, _ = database
    first = await _scan(db, owner)
    await resolve_rejection(db, owner, first.rejection_id, "allow_once"); await db.commit()
    second = await create_rejection_from_content(SkillRejectionCreateIn(content=CONTENT, filename="SKILL.md"), owner, db)
    await resolve_rejection(db, owner, second.id, "allow_once"); await db.commit()
    assert not (await _scan(db, owner)).blocked
    assert not (await _scan(db, owner)).blocked
    assert (await _scan(db, owner)).blocked


@pytest.mark.asyncio
async def test_repeated_blocked_attempt_reuses_pending_evidence_but_resolved_case_is_immutable(database):
    db, owner, _, _ = database
    first = await _scan(db, owner); second = await _scan(db, owner)
    assert first.rejection_id == second.rejection_id
    row = await db.get(SkillAccessRejection, first.rejection_id)
    evidence = copy.deepcopy(row.findings)
    assert "a" * 40 not in row.content_preview
    await resolve_rejection(db, owner, row.id, "keep_rejected", "reviewed"); await db.commit()
    third = await _scan(db, owner)
    assert third.rejection_id != first.rejection_id
    await db.refresh(row)
    assert row.findings == evidence and row.resolver_note == "reviewed" and row.status == "kept_rejected"


@pytest.mark.asyncio
async def test_key_bound_membership_can_consume_its_own_org_grant_without_switching_owner(database):
    db, owner, _, other_org = database
    original_org = owner.org_id
    first = await _scan(db, owner)
    await resolve_rejection(db, owner, first.rejection_id, "allow_once"); await db.commit()
    db.add(OrgMembership(user_id=owner.id, org_id=original_org, role="member"))
    owner.org_id = other_org.id; await db.commit()
    actor = SimpleNamespace(id=owner.id, org_id=original_org)
    decision = await apply_saved_scan_overrides(db, actor, SkillGuardrail().scan(CONTENT), CONTENT, "SKILL.md")
    await db.commit()
    assert decision.safe and owner.org_id == other_org.id
    assert (await apply_saved_scan_overrides(db, actor, SkillGuardrail().scan(CONTENT), CONTENT, "SKILL.md")).blocked


@pytest.mark.asyncio
async def test_forged_scope_without_membership_cannot_use_approval_store(database):
    db, owner, _, other_org = database
    actor = SimpleNamespace(id=owner.id, org_id=other_org.id)
    with pytest.raises(HTTPException) as denied:
        await apply_saved_scan_overrides(db, actor, SkillGuardrail().scan(CONTENT), CONTENT, "SKILL.md")
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_fresh_rejection_revokes_matching_grants_without_rewriting_history_or_replaying_old_actions(database):
    db, owner, _, _ = database
    first = await _scan(db, owner)
    await resolve_rejection(db, owner, first.rejection_id, "allow_always", "first approval"); await db.commit()
    assert not (await _scan(db, owner)).blocked
    report = await report_rejection(SkillRejectionReportIn(filename="SKILL.md", content_preview=CONTENT, content_sha256=content_digest(CONTENT), findings=first.findings), owner, db)
    await resolve_rejection(db, owner, report.id, "keep_rejected", "now rejected"); await db.commit()
    assert (await _scan(db, owner)).blocked
    # Retrying an old approval does not recreate a grant revoked by a newer
    # decision. The historical action/note remains an immutable receipt.
    original = await resolve_rejection(db, owner, first.rejection_id, "allow_always", "should not replace")
    await db.commit()
    assert original.resolver_note == "first approval"
    assert (await _scan(db, owner)).blocked
    fresh = await _scan(db, owner)
    await resolve_rejection(db, owner, fresh.rejection_id, "allow_always", "new approval"); await db.commit()
    await resolve_rejection(db, owner, report.id, "keep_rejected", "old retry"); await db.commit()
    assert not (await _scan(db, owner)).blocked


@pytest.mark.asyncio
async def test_keep_rejected_revokes_outstanding_one_time_allowances(database):
    db, owner, _, _ = database
    first = await _scan(db, owner)
    await resolve_rejection(db, owner, first.rejection_id, "allow_once"); await db.commit()
    fresh = await create_rejection_from_content(SkillRejectionCreateIn(content=CONTENT, filename="SKILL.md"), owner, db)
    await resolve_rejection(db, owner, fresh.id, "keep_rejected"); await db.commit()
    assert (await _scan(db, owner)).blocked


@pytest.mark.parametrize("source", ["scan", "create"])
@pytest.mark.asyncio
async def test_credential_crossing_preview_boundary_is_redacted_before_truncation(database, source):
    db, owner, _, _ = database
    credential = "grg_" + "z" * 40
    content = "Public documentation.\n" + "x" * 460 + "\n" + credential
    if source == "scan":
        decision = await _scan(db, owner, content=content)
        row = await db.get(SkillAccessRejection, decision.rejection_id)
    else:
        row = await create_rejection_from_content(SkillRejectionCreateIn(content=content, filename="boundary.md", content_preview=content[:500]), owner, db)
    assert row.content_preview and len(row.content_preview) <= 500
    assert credential[:12] not in row.content_preview
    assert "REDACTED" in row.content_preview
