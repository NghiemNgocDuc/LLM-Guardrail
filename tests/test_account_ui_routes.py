"""Exercise server routes used by account and evidence UI actions."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Match

from app.database import get_db
from app.deps import get_current_user, hash_password, verify_password
from app.routers.auth import router as auth_router
from app.routers.managed_skills import router as skills_router


@pytest.fixture
def account():
    return SimpleNamespace(hashed_password=hash_password("existing-password"))


@pytest.fixture
def account_client(account):
    app = FastAPI()
    app.include_router(auth_router)
    session = SimpleNamespace(flushed=False)

    async def flush():
        session.flushed = True

    session.flush = flush
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: account
    with TestClient(app) as client:
        yield client, session


def test_password_change_checks_existing_password(account_client, account):
    client, session = account_client
    original_hash = account.hashed_password
    response = client.post("/auth/change-password", json={"current_password": "wrong-password", "new_password": "replacement-password"})
    assert response.status_code == 400
    assert account.hashed_password == original_hash
    assert not session.flushed


def test_password_change_persists_new_hash(account_client, account):
    client, session = account_client
    response = client.post("/auth/change-password", json={"current_password": "existing-password", "new_password": "replacement-password"})
    assert response.status_code == 200
    assert session.flushed
    assert verify_password("replacement-password", account.hashed_password)
    assert not verify_password("existing-password", account.hashed_password)


@pytest.mark.parametrize("replacement", ["short", "existing-password", "é" * 37])
def test_password_change_rejects_invalid_or_unchanged_password(account_client, account, replacement):
    client, session = account_client
    original_hash = account.hashed_password
    response = client.post("/auth/change-password", json={"current_password": "existing-password", "new_password": replacement})
    assert response.status_code in (400, 422)
    assert account.hashed_password == original_hash
    assert not session.flushed


def test_external_account_password_cannot_be_overwritten(account_client, account):
    client, session = account_client
    account.hashed_password = ""
    response = client.post("/auth/change-password", json={"current_password": "existing-password", "new_password": "replacement-password"})
    assert response.status_code == 400
    assert account.hashed_password == ""
    assert not session.flushed


def test_fixture_metrics_path_is_not_treated_as_skill_slug():
    scope = {"type": "http", "path": "/skills/managed/metrics", "method": "GET"}
    matching = [route for route in skills_router.routes if route.matches(scope)[0] == Match.FULL]
    assert matching[0].endpoint.__name__ == "skill_metrics"


def test_password_change_requires_authentication():
    app = FastAPI()
    app.include_router(auth_router)
    app.dependency_overrides[get_db] = lambda: SimpleNamespace()
    with TestClient(app) as client:
        response = client.post("/auth/change-password", json={"current_password": "existing-password", "new_password": "replacement-password"})
    assert response.status_code == 401
