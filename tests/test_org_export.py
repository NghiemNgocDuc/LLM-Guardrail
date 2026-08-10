"""Tests for GET /org/export and POST /org/rotate-webhook-secret."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.org import export_org_data, rotate_webhook_secret


def _log(rule="pii_detected", status="input_blocked"):
    return SimpleNamespace(
        id="req-1",
        status=status,
        model="gpt-4o",
        backend="openai",
        latency_ms=120,
        input_passed=False,
        output_passed=None,
        input_block_reason="PII detected: email",
        output_block_reason=None,
        fired_rule=rule,
        input_tokens=0,
        output_tokens=0,
        created_at=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc),
    )


class _CountResult:
    def __init__(self, total):
        self._total = total

    def scalar(self):
        return self._total


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _ExportDB:
    """Routes count queries vs row queries by scanning the compiled SQL."""

    def __init__(self, total, rows):
        self._total = total
        self._rows = rows

    async def execute(self, stmt):
        if "count(" in str(stmt):
            return _CountResult(self._total)
        return _RowsResult(self._rows)


class _PolicyResult:
    def __init__(self, policy):
        self._policy = policy

    def scalar_one_or_none(self):
        return self._policy


class _PolicyDB:
    def __init__(self, policy):
        self._policy = policy
        self.flushed = False

    async def execute(self, stmt):
        return _PolicyResult(self._policy)

    async def flush(self):
        self.flushed = True


def _admin(org_id="org-1", is_admin=True):
    return SimpleNamespace(org_id=org_id, is_admin=is_admin)


def _run_export(db, user):
    return asyncio.run(export_org_data(user, days=30, page=1, page_size=100, db=db))


# ── GET /org/export ──────────────────────────────────────────────────────

def test_export_returns_paginated_rows():
    rows = [(_log(), "alice@example.com"), (_log(rule="toxic_content", status="output_blocked"), "bob@example.com")]
    result = _run_export(_ExportDB(total=7, rows=rows), _admin())

    assert result["total"] == 7
    assert result["page"] == 1
    assert result["page_size"] == 100
    assert len(result["items"]) == 2

    item = result["items"][0]
    assert item["user_email"] == "alice@example.com"
    assert item["fired_rule"] == "pii_detected"
    assert item["status"] == "input_blocked"
    assert item["created_at"] == "2026-08-01T12:00:00+00:00"
    assert item["request_id"] == item["id"]

    # sensitive fields never leave the server
    for key in ("full_prompt", "hashed_password", "prompt_hash"):
        assert key not in item


def test_export_empty_org():
    result = _run_export(_ExportDB(total=0, rows=[]), _admin())
    assert result["total"] == 0
    assert result["items"] == []


def test_export_requires_admin():
    with pytest.raises(HTTPException) as exc:
        _run_export(_ExportDB(total=0, rows=[]), _admin(is_admin=False))
    assert exc.value.status_code == 403


def test_export_requires_org():
    with pytest.raises(HTTPException) as exc:
        _run_export(_ExportDB(total=0, rows=[]), _admin(org_id=None))
    assert exc.value.status_code == 404


# ── POST /org/rotate-webhook-secret ──────────────────────────────────────

def _policy(compliance_rules=None):
    return SimpleNamespace(compliance_rules=dict(compliance_rules or {}))


def test_rotate_webhook_secret_stores_and_returns_once():
    policy = _policy({"webhook_url": "https://hooks.example.com/x"})
    db = _PolicyDB(policy)

    result = asyncio.run(rotate_webhook_secret(_admin(), db))

    assert db.flushed is True
    assert len(result.webhook_secret) >= 32
    assert policy.compliance_rules["webhook_secret"] == result.webhook_secret
    assert policy.compliance_rules["webhook_url"] == "https://hooks.example.com/x"  # untouched
    assert result.created_at is not None


def test_rotate_requires_admin():
    db = _PolicyDB(_policy())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(rotate_webhook_secret(_admin(is_admin=False), db))
    assert exc.value.status_code == 403


def test_rotate_requires_org():
    db = _PolicyDB(_policy())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(rotate_webhook_secret(_admin(org_id=None), db))
    assert exc.value.status_code == 404


def test_rotate_requires_policy():
    db = _PolicyDB(None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(rotate_webhook_secret(_admin(), db))
    assert exc.value.status_code == 404