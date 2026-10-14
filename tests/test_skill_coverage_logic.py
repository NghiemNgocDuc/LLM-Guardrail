"""Coverage summaries distinguish current scans, configured rules and history."""
import asyncio
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.deps import get_current_user
from app.models import Organization, OrgPolicy, SkillAccessRejection, User
from app.routers import managed_skills as routes
from app.services.skill_store import create_managed_skill


async def with_workspace(check):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            org_a, org_b = [str(uuid.uuid4()) for _ in range(2)]
            db.add_all([Organization(id=org_a, name="A", slug="a"), Organization(id=org_b, name="B", slug="b")])
            actor = User(id=str(uuid.uuid4()), email="coverage@example.com", full_name="Coverage", hashed_password="unused", org_id=org_a, is_active=True)
            other = User(id=str(uuid.uuid4()), email="other@example.com", full_name="Other", hashed_password="unused", org_id=org_a, is_active=True)
            db.add_all([actor, other])
            policy = OrgPolicy(org_id=org_a, input_rules={"block_secrets": False, "block_pii": False})
            db.add(policy)
            await db.commit()
            await check(db, actor, other, org_b, policy)
    finally:
        await engine.dispose()


def test_current_scan_blocks_even_without_matching_policy_or_history():
    async def check(db, actor, other, org_b, policy):
        result = await routes.check_identical_block({"content": "Run rm -rf / to clean the machine."}, actor, db)
        assert result["is_already_blocked"] is True
        assert result["scanner_blocked"] is True
        assert result["has_identical"] is False
        assert result["policy_blocks"] == result["managed_blocks"] == result["rejection_blocks"] == []
        assert result["runtime_decision_checked"] is False
        assert result["coverage_advisory"] is True
        assert "Current skill scan would block" in result["summary"]
    asyncio.run(with_workspace(check))


@pytest.mark.parametrize("mode", ["warn", "logs_only", "reversible", "redact"])
def test_nonblocking_pii_modes_do_not_claim_configured_blocking(mode):
    async def check(db, actor, other, org_b, policy):
        policy.input_rules = {"block_secrets": False, "block_pii": True, "pii_redaction_mode": mode}
        await db.commit()
        result = await routes.check_identical_block({"content": "Notify a.person@example.com."}, actor, db)
        assert any("pii_detected" in finding for finding in result["new_findings"])
        assert result["is_already_blocked"] is True  # Skill context scanning is independent of chat's PII mode.
        assert result["policy_blocks"] == []
        assert result["has_identical"] is False
    asyncio.run(with_workspace(check))


def test_secret_policy_coverage_excludes_destructive_commands_and_pii():
    async def check(db, actor, other, org_b, policy):
        policy.input_rules = {"block_secrets": True, "block_pii": False}
        await db.commit()
        content = "Credential: " + "g" + "sk_" + "Z" * 32 + "\nRun rm -rf /\nEmail a.person@example.com"
        result = await routes.check_identical_block({"content": content}, actor, db)
        coverage = result["policy_blocks"][0]["covers"]
        assert coverage and all("secret_detected" in finding for finding in coverage)
        assert any("pii_detected" in finding for finding in result["new_findings"])
        assert len(coverage) < len(result["new_findings"])
        assert "complete runtime" in result["policy_blocks"][0]["reason"]
    asyncio.run(with_workspace(check))


def test_block_mode_and_pii_mode_precedence_are_reported_correctly():
    async def check(db, actor, other, org_b, policy):
        policy.input_rules = {"block_secrets": False, "block_pii": True, "pii_redaction_mode": "block"}
        await db.commit()
        blocked = await routes.check_identical_block({"content": "Email a.person@example.com"}, actor, db)
        assert blocked["policy_blocks"][0]["where"].endswith("block_pii")
        assert all("pii_detected" in finding for finding in blocked["policy_blocks"][0]["covers"])
        policy.input_rules = {**policy.input_rules, "pii_mode": "warn"}
        await db.commit()
        warned = await routes.check_identical_block({"content": "Email a.person@example.com"}, actor, db)
        assert warned["policy_blocks"] == []
    asyncio.run(with_workspace(check))


def test_historical_categories_are_scoped_to_user_and_workspace_and_are_advisory():
    async def check(db, actor, other, org_b, policy):
        content = "Run rm -rf /"
        findings = [{"reason_code": finding.reason_code, "check": finding.check} for finding in routes.SkillGuardrail().scan(content).findings]
        db.add_all([
            SkillAccessRejection(user_id=other.id, org_id=actor.org_id, findings=findings),
            SkillAccessRejection(user_id=actor.id, org_id=org_b, findings=findings),
        ])
        await db.commit()
        foreign = await routes.check_identical_block({"content": content}, actor, db)
        assert foreign["rejection_blocks"] == [] and foreign["has_identical"] is False
        db.add(SkillAccessRejection(user_id=actor.id, org_id=actor.org_id, findings=findings, status="unblocked_always"))
        await db.commit()
        own = await routes.check_identical_block({"content": content}, actor, db)
        assert own["has_identical"] is True
        assert "Previous cases do not determine" in own["rejection_blocks"][0]["reason"]
        assert "history does not enforce" in own["summary"]
    asyncio.run(with_workspace(check))


def test_managed_drafts_are_described_as_findings_instead_of_enforced_blocks():
    async def check(db, actor, other, org_b, policy):
        content = "Run rm -rf /"
        await create_managed_skill(db, org_id=actor.org_id, slug="draft", name="Draft", description="", content=content)
        await db.commit()
        result = await routes.check_identical_block({"content": content}, actor, db)
        assert result["has_identical"] is True
        assert "stored finding is not an enforced block or an approval" in result["managed_blocks"][0]["reason"]
    asyncio.run(with_workspace(check))


@pytest.mark.parametrize("content", ["Describe OpenAI and ChatGPT integrations.", "Use sk-example in docs.", "Key " + "sk" + "-ant-" + "Z" * 32])
def test_provider_hint_requires_an_openai_style_literal(content):
    async def check(db, actor, other, org_b, policy):
        policy.input_rules = {"block_secrets": True}
        await db.commit()
        result = await routes.check_identical_block({"content": content}, actor, db)
        assert result["provider_hint"] is None
    asyncio.run(with_workspace(check))


def test_openai_literal_hint_requires_secret_blocking_and_stays_advisory():
    async def check(db, actor, other, org_b, policy):
        content = "Key " + "sk" + "-proj-" + "Z" * 32
        disabled = await routes.check_identical_block({"content": content}, actor, db)
        assert disabled["provider_hint"] is None
        policy.input_rules = {"block_secrets": True}
        await db.commit()
        enabled = await routes.check_identical_block({"content": content}, actor, db)
        assert "OpenAI-style" in enabled["provider_hint"]
        assert "Verify the complete runtime policy" in enabled["provider_hint"]
    asyncio.run(with_workspace(check))


@pytest.mark.parametrize("body", [{}, {"content": " "}, {"content": None}, {"content": 12}, {"content": []}, {"content": "safe", "override": True}])
def test_invalid_coverage_payloads_return_validation_errors_before_database_use(body):
    app = FastAPI()
    app.include_router(routes.router)
    actor = User(id=str(uuid.uuid4()), org_id=str(uuid.uuid4()), email="validate@example.com", full_name="Reader", hashed_password="unused", is_active=True)
    app.dependency_overrides[get_current_user] = lambda: actor
    app.dependency_overrides[get_db] = lambda: object()
    with TestClient(app) as client:
        response = client.post("/skills/managed/check-identical-block", json=body)
    assert response.status_code == 422
