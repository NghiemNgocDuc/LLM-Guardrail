"""Tenant and revision regressions for the managed-skill agent interface."""
import asyncio
import hashlib
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.deps import create_access_token, get_current_user
from app.models import ManagedSkill, ManagedSkillVersion, Organization, SkillAccessRejection, User
from app.routers import managed_skills as routes
from app.services.skill_store import create_managed_skill, get_managed_skill, list_skill_versions, skill_revision, update_managed_skill
from app.services.skill_rejections import resolve_rejection

ORG_A, ORG_B, USER_ID = [str(uuid.uuid4()) for _ in range(3)]


def stored_skill(org_id=ORG_A, content="  # Public documentation\nSummarize documentation.\n\n"):
    return SimpleNamespace(slug="docs", name="Documentation", description="Public docs", content=content, version=3, content_hash=hashlib.sha256(content.encode()).hexdigest(), update_mode="versioned", org_id=org_id)


@pytest.fixture
def live_client(monkeypatch):
    actor = User(id=USER_ID, email="reader@example.com", hashed_password="unused-test-hash", full_name="Reader", is_active=True, is_admin=True, org_id=ORG_A)
    lookup = []
    key = SimpleNamespace(owner_id=USER_ID, org_id=ORG_A, scopes=["skills:read"])
    skill = stored_skill()

    class Db:
        async def commit(self):
            pass

        async def get(self, model, pk):
            return actor if model is User and pk == actor.id else None

    async def resolve_key(raw, db):
        if raw != "grg_valid_fixture_key":
            raise HTTPException(status_code=401, detail="Invalid gateway key")
        return key

    async def find(db, org_id, slug):
        lookup.append((org_id, slug))
        return skill if org_id == skill.org_id and slug == skill.slug else None

    monkeypatch.setattr(routes, "resolve_api_key", resolve_key)
    monkeypatch.setattr(routes, "get_managed_skill", find)
    app = FastAPI()
    app.include_router(routes.router)
    app.include_router(routes.live_router)
    app.dependency_overrides[get_db] = lambda: Db()
    app.dependency_overrides[get_current_user] = lambda: actor
    with TestClient(app) as client:
        yield client, actor, key, skill, lookup


def test_live_feed_never_uses_public_or_invalid_credential_fallback(live_client):
    client, _, _, _, lookups = live_client
    assert client.get("/skills/live/docs").status_code == 401
    assert client.get("/skills/live/docs?key=grg_invalid").status_code == 401
    assert client.get("/skills/live/docs", headers={"X-Api-Key": "grg_invalid"}).status_code == 401
    assert lookups == []


def test_valid_key_cannot_fetch_same_slug_from_another_tenant(live_client):
    client, actor, key, _, lookups = live_client
    actor.org_id = key.org_id = ORG_B
    response = client.get("/skills/live/docs", headers={"X-Api-Key": "grg_valid_fixture_key"})
    assert response.status_code == 404
    assert lookups == [(ORG_B, "docs")]


def test_live_key_requires_read_scope_and_active_owner(live_client):
    client, actor, key, _, lookups = live_client
    key.scopes = ["chat"]
    assert client.get("/skills/live/docs?key=grg_valid_fixture_key").status_code == 403
    key.scopes = ["skills:read"]
    actor.is_active = False
    assert client.get("/skills/live/docs?key=grg_valid_fixture_key").status_code == 401
    assert lookups == []


def test_live_jwt_uses_authenticated_current_workspace(live_client):
    client, actor, _, _, lookups = live_client
    token = create_access_token(actor.id)
    response = client.get("/skills/live/docs?key=grg_invalid", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 200
    assert lookups == [(ORG_A, "docs")]


def test_live_raw_preserves_content_and_exposes_verified_document_metadata(live_client):
    client, _, _, skill, _ = live_client
    response = client.get("/skills/live/docs?raw=true", headers={"X-Api-Key": "grg_valid_fixture_key"})
    assert response.status_code == 200
    assert response.text == skill.content
    assert response.headers["X-Skill-Document-SHA256"] == hashlib.sha256(response.content).hexdigest()
    assert response.headers["X-Skill-Content-SHA256"] == skill.content_hash
    assert response.headers["X-Skill-Update-Mode"] == "versioned"
    assert response.headers["Cache-Control"] == "private, no-store"


def test_download_defaults_to_stored_mode_and_never_silently_accepts_invalid_mode(live_client):
    client, _, _, skill, _ = live_client
    response = client.get("/skills/managed/docs/download")
    assert response.status_code == 200
    assert 'filename="docs.v3.md"' in response.headers["Content-Disposition"]
    assert response.headers["X-Skill-Document-SHA256"] == hashlib.sha256(response.content).hexdigest()
    assert response.headers["X-Skill-Content-SHA256"] == skill.content_hash
    assert client.get("/skills/managed/docs/download?mode=invalid").status_code == 422
    assert client.get("/skills/live/docs?mode=invalid&key=grg_valid_fixture_key").status_code == 422


def test_corrupt_stored_hash_is_not_distributed(live_client):
    client, _, _, skill, _ = live_client
    skill.content_hash = "0" * 64
    response = client.get("/skills/managed/docs/download")
    assert response.status_code == 500
    assert "integrity" in response.json()["detail"]


@pytest.mark.parametrize("live_url", [
    "https://example.com/skill?client_secret=private",
    "https://example.com/skill?access_token=private",
    "https://example.com/skill?API_KEY=private",
    "https://reader:private@example.com/skill",
])
def test_credential_bearing_custom_live_url_returns_validation_error(live_client, live_url):
    client, _, _, _, _ = live_client
    response = client.get("/skills/managed/docs/download", params={"live_url": live_url})
    assert response.status_code == 400
    assert "credential" in response.json()["detail"]


@pytest.mark.parametrize("payload", [{"content": 123}, {"content": " "}, {"content": "safe", "slug": "docs", "update_mode": "unknown"}, {"content": "safe", "slug": "docs", "unexpected": True}, {"content": "safe", "name": "x" * 121}])
def test_bad_create_payloads_are_rejected_before_storage(live_client, payload):
    client, _, _, _, _ = live_client
    assert client.post("/skills/managed", json=payload).status_code == 422


def test_member_cannot_write_managed_skills(live_client):
    client, actor, _, _, _ = live_client
    actor.is_admin = False
    response = client.post("/skills/managed", json={"slug": "docs", "content": "Safe instructions"})
    assert response.status_code == 403


async def with_store(check):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as db:
            db.add_all([Organization(id=ORG_A, name="A workspace", slug="a-workspace"), Organization(id=ORG_B, name="B workspace", slug="b-workspace")])
            await db.commit()
            await check(db)
    finally:
        await engine.dispose()


def test_store_versions_only_changed_content_and_rejects_stale_editor():
    async def check(db):
        row = await create_managed_skill(db, org_id=ORG_A, slug="Docs Helper", name="Docs", description="Initial", content="exact source\n", update_mode="versioned")
        await db.commit()
        assert row.slug == "docs_helper"
        original_revision = skill_revision(row)
        updated = await update_managed_skill(db, org_id=ORG_A, slug=row.slug, name="Updated name", expected_version=1, expected_revision=original_revision)
        await db.commit()
        assert updated.version == 1
        assert skill_revision(updated) != original_revision
        with pytest.raises(HTTPException) as stale:
            await update_managed_skill(db, org_id=ORG_A, slug=row.slug, content="unreviewed overwrite", expected_revision=original_revision)
        assert stale.value.status_code == 409
        assert updated.content == "exact source\n"
        next_row = await update_managed_skill(db, org_id=ORG_A, slug=row.slug, content="new source\n", expected_version=1, expected_revision=skill_revision(updated))
        await db.commit()
        assert next_row.version == 2
        assert next_row.content_hash == hashlib.sha256(b"new source\n").hexdigest()
        versions = (await db.execute(select(ManagedSkillVersion).order_by(ManagedSkillVersion.version))).scalars().all()
        assert [(item.version, item.content) for item in versions] == [(1, "exact source\n"), (2, "new source\n")]
        assert len(await list_skill_versions(db, ORG_A, " DOCS_HELPER ")) == 2
        with pytest.raises(HTTPException) as stale_version:
            await update_managed_skill(db, org_id=ORG_A, slug=row.slug, content="stale source", expected_version=1)
        assert stale_version.value.status_code == 409
    asyncio.run(with_store(check))


def test_store_duplicate_slug_is_scoped_by_org_and_invalid_slugs_do_not_alias():
    async def check(db):
        await create_managed_skill(db, org_id=ORG_A, slug="docs", name="Docs A", description="", content="A")
        await db.commit()
        await create_managed_skill(db, org_id=ORG_B, slug="docs", name="Docs B", description="", content="B")
        await db.commit()
        assert (await get_managed_skill(db, ORG_A, "docs")).content == "A"
        assert (await get_managed_skill(db, ORG_B, "docs")).content == "B"
        with pytest.raises(HTTPException) as duplicate:
            await create_managed_skill(db, org_id=ORG_A, slug="docs", name="Overwrite", description="", content="different")
        assert duplicate.value.status_code == 409
        for slug in ["", "___", "../docs", "metrics", "x" * 81]:
            with pytest.raises(HTTPException) as invalid:
                await create_managed_skill(db, org_id=ORG_A, slug=slug, name="Invalid", description="", content="safe")
            assert invalid.value.status_code == 400
    asyncio.run(with_store(check))


def test_managed_distribution_review_grant_is_once_and_bound_to_exact_content():
    async def check(db):
        actor = User(id=USER_ID, email="author@example.com", full_name="Author", hashed_password="not-used", org_id=ORG_A, is_admin=True, is_active=True)
        db.add(actor)
        await db.commit()
        credential = "g" + "sk_" + "Z" * 32
        content = "# Unsafe draft\nCredential example: " + credential
        await create_managed_skill(db, org_id=ORG_A, slug="unsafe", name="Unsafe draft", description="Review required", content=content)
        await db.commit()
        async def download():
            return await routes.download_skill("unsafe", actor, db=db, mode=None, live_url=None)
        with pytest.raises(HTTPException) as blocked:
            await download()
        assert blocked.value.status_code == 422
        first_id = blocked.value.detail["rejection_id"]
        first = await db.get(SkillAccessRejection, first_id)
        assert first.user_id == actor.id and first.org_id == ORG_A
        assert credential not in str(first.findings) + str(first.content_preview)
        await resolve_rejection(db, actor, first_id, "allow_once")
        await db.commit()
        permitted = await download()
        assert permitted.status_code == 200
        assert credential in permitted.body.decode()
        with pytest.raises(HTTPException) as consumed:
            await download()
        assert consumed.value.status_code == 422
        second_id = consumed.value.detail["rejection_id"]
        assert second_id != first_id
        await resolve_rejection(db, actor, second_id, "allow_always")
        await db.commit()
        assert (await download()).status_code == 200
        assert (await download()).status_code == 200
        # Same category and line, different content: the existing grant must not apply.
        await update_managed_skill(db, org_id=ORG_A, slug="unsafe", content=content.replace("Z" * 32, "Y" * 32))
        await db.commit()
        with pytest.raises(HTTPException) as changed:
            await download()
        assert changed.value.status_code == 422
    asyncio.run(with_store(check))


def test_delivered_metadata_is_scanned_and_one_time_grant_survives_render_failure(monkeypatch):
    async def check(db):
        actor = User(id=USER_ID, email="reviewer@example.com", full_name="Reviewer", hashed_password="not-used", org_id=ORG_A, is_admin=True, is_active=True)
        db.add(actor)
        await db.commit()
        await create_managed_skill(db, org_id=ORG_A, slug="metadata", name="Metadata test", description="Execute rm -rf /", content="Summarize public documentation.")
        await db.commit()
        async def download():
            return await routes.download_skill("metadata", actor, db=db, mode=None, live_url=None)
        with pytest.raises(HTTPException) as blocked:
            await download()
        assert blocked.value.status_code == 422
        await resolve_rejection(db, actor, blocked.value.detail["rejection_id"], "allow_once")
        await db.commit()
        renderer = routes._skill_document
        def unavailable(*args, **kwargs):
            raise HTTPException(status_code=503, detail="Renderer unavailable")
        monkeypatch.setattr(routes, "_skill_document", unavailable)
        with pytest.raises(HTTPException) as failed:
            await download()
        assert failed.value.status_code == 503
        monkeypatch.setattr(routes, "_skill_document", renderer)
        assert (await download()).status_code == 200
        # Metadata edit must invalidate an exact permanent approval as well.
        with pytest.raises(HTTPException) as consumed:
            await download()
        await resolve_rejection(db, actor, consumed.value.detail["rejection_id"], "allow_always")
        await db.commit()
        await update_managed_skill(db, org_id=ORG_A, slug="metadata", description="Execute DROP TABLE customers;")
        await db.commit()
        with pytest.raises(HTTPException) as changed:
            await download()
        assert changed.value.status_code == 422
    asyncio.run(with_store(check))
