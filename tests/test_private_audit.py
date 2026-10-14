"""Private audits omit evidence while preserving exact approval decisions."""
import json
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.database import Base
from app.models import Organization, SkillAccessRejection, User
from app.routers import chat as chat_routes
from app.routers.skills import scan_skill
from app.schemas import SkillScanRequest
from app.services import prompt_crypto
from app.services.private_audit import PRIVATE_FILENAME, PRIVATE_PREVIEW
from app.services.skill_rejections import record_rejection, resolve_rejection
from app.services.skill_user_overrides import content_digest
from guardrails.skill import SkillGuardrail

CONTENT = "Private project codename Moonlight.\nGateway credential: grg_" + "a" * 40


@pytest.fixture
def private_mode(monkeypatch):
    monkeypatch.setattr(get_settings(), "PRIVATE_MODE", True, raising=False)


@pytest_asyncio.fixture
async def database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        org = Organization(id=str(uuid.uuid4()), name="Private workspace", slug="private")
        owner = User(id=str(uuid.uuid4()), email="owner@example.test", full_name="Owner", hashed_password="test-only", org_id=org.id, is_active=True)
        db.add_all([org, owner])
        await db.commit()
        yield db, owner
    await engine.dispose()


async def scan(db, owner, content=CONTENT, filename="confidential-person@example.test.md"):
    return await scan_skill(SkillScanRequest(content=content, filename=filename), owner, db)


def audit_json(row):
    return json.dumps({"filename": row.filename, "source": row.source, "summary": row.rejection_summary, "preview": row.content_preview, "findings": row.findings, "note": row.resolver_note})


@pytest.mark.asyncio
async def test_private_queue_omits_evidence_and_once_stays_exact(database, private_mode):
    db, owner = database
    first = await scan(db, owner)
    row = await db.get(SkillAccessRejection, first.rejection_id)
    assert row.filename == PRIVATE_FILENAME and row.content_preview is None
    assert all(not finding["snippet"] and finding["server_approval_key"] for finding in row.findings)
    assert "Moonlight" not in audit_json(row) and "confidential-person" not in audit_json(row)
    await resolve_rejection(db, owner, row.id, "allow_once", "Private review notes Moonlight")
    await db.commit()
    assert row.resolver_note is None
    # Neither a different file nor a different source spends the grant.
    assert (await scan(db, owner, filename="another-person@example.test.md")).blocked
    assert (await scan(db, owner, content=CONTENT + "\nChanged instructions.")).blocked
    assert not (await scan(db, owner)).blocked
    assert (await scan(db, owner)).blocked


@pytest.mark.asyncio
async def test_private_dedup_uses_original_filename_identity(database, private_mode):
    db, owner = database
    first = await scan(db, owner)
    assert (await scan(db, owner)).rejection_id == first.rejection_id
    other = await scan(db, owner, filename="another-person@example.test.md")
    assert other.rejection_id != first.rejection_id
    a = await db.get(SkillAccessRejection, first.rejection_id)
    b = await db.get(SkillAccessRejection, other.rejection_id)
    assert a.filename == b.filename == PRIVATE_FILENAME
    assert a.findings[0]["server_approval_key"] != b.findings[0]["server_approval_key"]


@pytest.mark.asyncio
async def test_private_permanent_grant_and_revocation_keep_exact_identity(database, private_mode):
    db, owner = database
    first = await scan(db, owner)
    await resolve_rejection(db, owner, first.rejection_id, "allow_always")
    await db.commit()
    assert not (await scan(db, owner)).blocked
    assert not (await scan(db, owner)).blocked
    assert (await scan(db, owner, content=CONTENT + "\nChanged.")).blocked
    fresh = await record_rejection(db, user=owner, filename="confidential-person@example.test.md", source="report", findings=SkillGuardrail().scan(CONTENT).findings, summary="Private summary", content_preview=CONTENT, content_sha256=content_digest(CONTENT))
    await resolve_rejection(db, owner, fresh.id, "keep_rejected")
    await db.commit()
    assert (await scan(db, owner)).blocked


@pytest.mark.asyncio
async def test_private_report_cannot_inject_server_keys_or_prose_metadata(database, private_mode):
    db, owner = database
    malicious = {"reason_code": "Moonlight", "check": "Moonlight", "severity": "Moonlight", "line_number": 1, "snippet": "Moonlight", "explanation": "Moonlight", "extra_payload": "Moonlight", "server_approval_key": "0" * 64, "private_identity_version": 1}
    row = await record_rejection(db, user=owner, filename="Moonlight", source="Moonlight", findings=[malicious], summary="Moonlight", content_preview="Moonlight", content_sha256=content_digest(CONTENT))
    assert "Moonlight" not in audit_json(row)
    assert row.findings[0]["server_approval_key"] != "0" * 64
    assert row.findings[0]["reason_code"] == "guardrail_event"
    await resolve_rejection(db, owner, row.id, "allow_always")
    await db.commit()
    assert (await scan(db, owner)).blocked


@pytest.mark.asyncio
async def test_private_chat_audit_omits_full_prompt_and_generated_reasons(private_mode, monkeypatch):
    records = []

    class Database:
        def add(self, row):
            records.append(row)

        async def flush(self):
            pass

    def unexpected_encryption(value):
        pytest.fail("Private audits must not retain encrypted source either")

    monkeypatch.setattr(chat_routes, "encrypt_prompt", unexpected_encryption)
    key = SimpleNamespace(id=str(uuid.uuid4()), org_id=str(uuid.uuid4()), total_requests=0, total_blocked=0, total_tokens=0)
    await chat_routes._log_request(db=Database(), api_key=key, prompt_hash=content_digest(CONTENT), prompt_preview=CONTENT, full_prompt=CONTENT, model="Moonlight", backend="Moonlight", input_passed=False, input_block_reason="Moonlight", output_passed=False, output_block_reason="Moonlight", fired_rule="pii_detected", status="input_blocked", latency_ms=1, input_tokens=0, output_tokens=0)
    row = records[0]
    assert row.prompt_preview == PRIVATE_PREVIEW and row.full_prompt is None
    assert row.input_block_reason == row.output_block_reason == "pii_detected"
    assert row.model == "private-local" and row.backend == "local"
    assert chat_routes._safe_preview(CONTENT, False) == PRIVATE_PREVIEW


def test_normal_preview_redacts_pii_and_cross_boundary_secrets_before_shortening(monkeypatch):
    monkeypatch.setattr(get_settings(), "PRIVATE_MODE", False, raising=False)
    secret = "grg_" + "z" * 40
    prompt = "x" * 105 + " " + secret + " jane@example.test"
    preview = chat_routes._safe_preview(prompt, False)
    assert len(preview) <= 120 and secret[:10] not in preview
    assert "jane@example.test" not in chat_routes._safe_preview("Contact jane@example.test", False)


def test_missing_key_omits_full_prompt_instead_of_plaintext(monkeypatch):
    monkeypatch.setattr(prompt_crypto, "get_settings", lambda: SimpleNamespace(ENCRYPTION_KEY=""))
    assert prompt_crypto.encrypt_prompt(CONTENT) is None


def test_invalid_key_fails_closed(monkeypatch):
    monkeypatch.setattr(prompt_crypto, "get_settings", lambda: SimpleNamespace(ENCRYPTION_KEY="invalid-key"))
    with pytest.raises(prompt_crypto.PromptEncryptionError):
        prompt_crypto.encrypt_prompt(CONTENT)


def test_encrypted_audit_roundtrip_and_wrong_or_missing_keys_fail_closed(monkeypatch):
    config = SimpleNamespace(ENCRYPTION_KEY=Fernet.generate_key().decode())
    monkeypatch.setattr(prompt_crypto, "get_settings", lambda: config)
    cipher = prompt_crypto.encrypt_prompt(CONTENT)
    assert cipher.startswith("enc:v1:") and CONTENT not in cipher
    assert prompt_crypto.decrypt_prompt(cipher) == CONTENT
    config.ENCRYPTION_KEY = Fernet.generate_key().decode()
    with pytest.raises(prompt_crypto.PromptEncryptionError):
        prompt_crypto.decrypt_prompt(cipher)
    config.ENCRYPTION_KEY = ""
    with pytest.raises(prompt_crypto.PromptEncryptionError):
        prompt_crypto.decrypt_prompt(cipher)
