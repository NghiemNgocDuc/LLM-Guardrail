"""Agent credentials cannot gain privileges through fallback authentication."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, get_db
import app.deps as deps
from app.models import APIKey, Organization, OrgMembership, User
from app.routers import chat, openai_compat


@asynccontextmanager
async def key_store(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async def no_ban(*args, **kwargs):
        pass
    monkeypatch.setattr("app.services.api_key_protection.check_ban_or_raise", no_ban)
    monkeypatch.setattr(deps, "verify_api_key", lambda raw, hashed: hashed == "fixture-hash")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            a = Organization(id=str(uuid.uuid4()), name="A", slug="a")
            b = Organization(id=str(uuid.uuid4()), name="B", slug="b")
            user = User(id=str(uuid.uuid4()), org_id=a.id, email="agent@example.com", full_name="Agent", hashed_password="fixture", is_active=True)
            raw = "grg_" + "x" * 40
            key = APIKey(id=str(uuid.uuid4()), owner_id=user.id, org_id=a.id, name="Agent", key_prefix=raw[:12], key_hash="fixture-hash", is_active=True, scopes=["chat"], budget_tokens=None)
            db.add_all([a, b, user, key]); await db.commit()
            yield db, user, key, a, b, raw
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_disabled_owner_and_removed_membership_invalidate_agent_keys(monkeypatch):
    async with key_store(monkeypatch) as (db, user, key, a, b, raw):
        assert await deps.resolve_api_key(raw, db) is key
        user.is_active = False; await db.commit()
        with pytest.raises(HTTPException) as error:
            await deps.resolve_api_key(raw, db)
        assert error.value.status_code == 401
        user.is_active = True; user.org_id = b.id; await db.commit()
        with pytest.raises(HTTPException) as error:
            await deps.resolve_api_key(raw, db)
        assert error.value.status_code == 403
        membership = OrgMembership(user_id=user.id, org_id=a.id)
        db.add(membership); await db.commit()
        assert await deps.resolve_api_key(raw, db) is key
        await db.delete(membership); await db.commit()
        with pytest.raises(HTTPException) as error:
            await deps.resolve_api_key(raw, db)
        assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_jwt_uses_only_current_workspace_and_skips_expired_keys(monkeypatch):
    async with key_store(monkeypatch) as (db, user, key, a, b, raw):
        now = datetime.now(timezone.utc)
        key.created_at = now - timedelta(days=3)
        db.add_all([
            APIKey(owner_id=user.id, org_id=b.id, name="Other workspace", key_prefix="other", key_hash="other-fixture-hash", is_active=True, created_at=now),
            APIKey(owner_id=user.id, org_id=a.id, name="Expired", key_prefix="expired", key_hash="expired-fixture-hash", is_active=True, expires_at=now-timedelta(days=1), created_at=now-timedelta(days=1)),
        ]); await db.commit()
        assert await deps.api_key_for_user(user, db) is key
        async def not_clerk(token):
            raise HTTPException(status_code=401, detail="Not a Clerk token")
        monkeypatch.setattr(deps.settings, "CLERK_SECRET_KEY", "configured-test-clerk")
        monkeypatch.setattr(deps, "_verify_clerk_token", not_clerk)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=deps.create_access_token(user.id))
        assert await deps.get_api_key_auth(None, credentials, db) is key
        key.budget_tokens = 5; key.budget_used = 5; await db.commit()
        with pytest.raises(HTTPException) as error:
            await deps.get_api_key_auth(None, credentials, db)
        assert error.value.status_code == 429


@pytest.mark.asyncio
async def test_expired_and_revoked_keys_fail_before_provider(monkeypatch):
    async with key_store(monkeypatch) as (db, user, key, a, b, raw):
        key.expires_at = datetime.now(timezone.utc)-timedelta(minutes=1)
        await db.commit(); await db.refresh(key)  # SQLite returns naive UTC timestamps.
        with pytest.raises(HTTPException) as error:
            await deps.resolve_api_key(raw, db)
        assert error.value.status_code == 401
        key.expires_at = None; key.is_active = False; await db.commit()
        with pytest.raises(HTTPException) as error:
            await deps.resolve_api_key(raw, db)
        assert error.value.status_code == 401


@pytest.mark.parametrize("scopes,expected", [(None, ["chat"]), ([], []), (["skills:read"], ["skills:read"])])
def test_explicit_empty_scopes_never_acquire_legacy_chat(scopes, expected):
    assert deps.api_key_scopes(SimpleNamespace(scopes=scopes)) == expected


@pytest.mark.parametrize("path,payload", [
    ("/chat", {"prompt": "Public docs"}),
    ("/chat/stream", {"prompt": "Public docs"}),
    ("/v1/chat/completions", {"messages": [{"role": "user", "content": "Public docs"}]}),
])
@pytest.mark.parametrize("scopes", [[], ["skills:read"]])
def test_rest_agent_routes_deny_ungranted_chat_before_database_or_provider(path, payload, scopes):
    class NoDatabaseCalls:
        async def execute(self, statement):
            raise AssertionError("Unscoped requests must fail before policy/provider work")
    app = FastAPI(); app.include_router(chat.router); app.include_router(openai_compat.router)
    app.dependency_overrides[deps.get_api_key_auth] = lambda: SimpleNamespace(scopes=scopes)
    app.dependency_overrides[get_db] = lambda: NoDatabaseCalls()
    with TestClient(app) as client:
        assert client.post(path, json=payload).status_code == 403


def test_stream_only_key_cannot_make_nonstream_requests():
    app = FastAPI(); app.include_router(chat.router); app.include_router(openai_compat.router)
    app.dependency_overrides[deps.get_api_key_auth] = lambda: SimpleNamespace(scopes=["chat:stream"])
    app.dependency_overrides[get_db] = lambda: None
    with TestClient(app) as client:
        assert client.post("/chat", json={"prompt": "Public docs"}).status_code == 403
        assert client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "Public docs"}], "stream": False}).status_code == 403


@pytest.mark.parametrize("path,payload", [
    ("/chat/stream", {"prompt": "Public docs"}),
    ("/v1/chat/completions", {"messages": [{"role": "user", "content": "Public docs"}], "stream": True}),
])
def test_stream_only_key_reaches_stream_policy_gate(path, payload):
    class PolicyGate:
        async def execute(self, statement):
            raise HTTPException(status_code=418, detail="Reached the policy gate without calling a provider")
    app = FastAPI(); app.include_router(chat.router); app.include_router(openai_compat.router)
    app.dependency_overrides[deps.get_api_key_auth] = lambda: SimpleNamespace(scopes=["chat:stream"], org_id=str(uuid.uuid4()))
    app.dependency_overrides[get_db] = lambda: PolicyGate()
    with TestClient(app) as client:
        assert client.post(path, json=payload).status_code == 418
