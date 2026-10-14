"""Private mode cannot turn rejected source into a stored skill draft."""
import json
import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.database import Base
from app.models import ManagedSkill, ManagedSkillVersion, Organization, SkillAccessRejection, User
from app.routers.managed_skills import CreateSkillRequest, UpdateSkillRequest, create_skill, update_skill
from app.services.skill_rejections import resolve_rejection
from app.services.skill_store import create_managed_skill, get_managed_skill

SAFE = "Summarize public documentation."
UNSAFE = "Private codename Moonlight.\nGateway credential: grg_" + "a" * 40


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
        owner = User(id=str(uuid.uuid4()), email="owner@example.test", full_name="Owner", hashed_password="test-only", org_id=org.id, is_active=True, is_admin=True)
        db.add_all([org, owner])
        await db.commit()
        yield db, owner
    await engine.dispose()


async def create(db, owner, **changes):
    fields = dict(slug="docs", name="Docs helper", description="", content=SAFE, block_on_conflict=False)
    fields.update(changes)
    return await create_skill(CreateSkillRequest(**fields), owner, db)


@pytest.mark.parametrize("changes", [
    {"content": UNSAFE},
    {"name": "grg_" + "b" * 40},
    {"description": "Private contact jane@example.test"},
    {"content": "Execute rm -rf /"},
])
@pytest.mark.asyncio
async def test_private_create_rejects_all_flagged_authored_fields_without_storing_source(database, private_mode, changes):
    db, owner = database
    with pytest.raises(HTTPException) as rejected:
        await create(db, owner, **changes)
    assert rejected.value.status_code == 422 and rejected.value.detail["private_mode"]
    assert "Redact or remove" in rejected.value.detail["message"]
    assert await db.scalar(select(func.count()).select_from(ManagedSkill)) == 0
    assert await db.scalar(select(func.count()).select_from(ManagedSkillVersion)) == 0
    row = await db.get(SkillAccessRejection, rejected.value.detail["rejection_id"])
    assert row.source == "managed_write" and row.content_preview is None
    audit = json.dumps(row.findings) + row.rejection_summary
    assert "Moonlight" not in audit and "jane@example.test" not in audit


@pytest.mark.asyncio
async def test_private_safe_create_and_update_work_without_advisory_override(database, private_mode):
    db, owner = database
    first = await create(db, owner)
    second = await update_skill("docs", UpdateSkillRequest(content=SAFE + "\nUse concise paragraphs.", expected_revision=first["revision"]), owner, db)
    assert second["version"] == 2
    row = await get_managed_skill(db, owner.org_id, "docs")
    assert row.content == SAFE + "\nUse concise paragraphs."
    assert await db.scalar(select(func.count()).select_from(ManagedSkillVersion)) == 2


@pytest.mark.parametrize("changes", [
    {"content": UNSAFE},
    {"name": "grg_" + "b" * 40},
    {"description": "Execute DROP TABLE customers;"},
])
@pytest.mark.asyncio
async def test_private_update_rejects_content_and_metadata_without_creating_version(database, private_mode, changes):
    db, owner = database
    first = await create(db, owner)
    with pytest.raises(HTTPException) as rejected:
        await update_skill("docs", UpdateSkillRequest(**changes, expected_revision=first["revision"], block_on_conflict=False), owner, db)
    assert rejected.value.status_code == 422
    row = await get_managed_skill(db, owner.org_id, "docs")
    assert (row.name, row.description, row.content, row.version) == ("Docs helper", "", SAFE, 1)
    assert await db.scalar(select(func.count()).select_from(ManagedSkillVersion)) == 1


@pytest.mark.asyncio
async def test_private_metadata_only_update_scans_legacy_source_and_preserves_history(database, private_mode):
    db, owner = database
    legacy = await create_managed_skill(db, org_id=owner.org_id, slug="docs", name="Docs helper", description="", content=UNSAFE)
    await db.commit()
    with pytest.raises(HTTPException) as rejected:
        await update_skill("docs", UpdateSkillRequest(name="Renamed docs", expected_version=1), owner, db)
    assert rejected.value.status_code == 422
    await db.refresh(legacy)
    assert legacy.name == "Docs helper" and legacy.content == UNSAFE and legacy.version == 1
    versions = (await db.execute(select(ManagedSkillVersion))).scalars().all()
    assert len(versions) == 1 and versions[0].content == UNSAFE
    # Safe replacement is allowed; historical source is not silently rewritten.
    result = await update_skill("docs", UpdateSkillRequest(content=SAFE, expected_version=1), owner, db)
    assert result["version"] == 2
    versions = (await db.execute(select(ManagedSkillVersion).order_by(ManagedSkillVersion.version))).scalars().all()
    assert [row.content for row in versions] == [UNSAFE, SAFE]


@pytest.mark.asyncio
async def test_private_approval_never_permits_unsafe_draft_storage(database, private_mode):
    db, owner = database
    with pytest.raises(HTTPException) as first:
        await create(db, owner, content=UNSAFE)
    await resolve_rejection(db, owner, first.value.detail["rejection_id"], "allow_always")
    await db.commit()
    with pytest.raises(HTTPException) as retry:
        await create(db, owner, content=UNSAFE)
    assert retry.value.status_code == 422
    assert retry.value.detail["rejection_id"] != first.value.detail["rejection_id"]
    assert await db.scalar(select(func.count()).select_from(ManagedSkill)) == 0
    assert await db.scalar(select(func.count()).select_from(ManagedSkillVersion)) == 0


@pytest.mark.asyncio
async def test_private_stale_update_returns_conflict_without_recording_rejected_draft(database, private_mode):
    db, owner = database
    first = await create(db, owner)
    await update_skill("docs", UpdateSkillRequest(description="Public documentation", expected_revision=first["revision"]), owner, db)
    with pytest.raises(HTTPException) as stale:
        await update_skill("docs", UpdateSkillRequest(content=UNSAFE, expected_revision=first["revision"]), owner, db)
    assert stale.value.status_code == 409
    assert await db.scalar(select(func.count()).select_from(SkillAccessRejection)) == 0


@pytest.mark.asyncio
async def test_normal_mode_retains_advisory_draft_workflow(database, monkeypatch):
    monkeypatch.setattr(get_settings(), "PRIVATE_MODE", False, raising=False)
    db, owner = database
    created = await create(db, owner, content=UNSAFE)
    assert created["version"] == 1
    assert (await get_managed_skill(db, owner.org_id, "docs")).content == UNSAFE
