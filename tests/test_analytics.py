"""Tests for GET /analytics/top-blocked-reasons."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.routers.analytics import top_blocked_reasons


class _Row:
    def __init__(self, fired_rule, cnt, last_occurred_at):
        self.fired_rule = fired_rule
        self.cnt = cnt
        self.last_occurred_at = last_occurred_at


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, stmt):
        return _FakeResult(self._rows)


def _user(org_id="org-1"):
    return SimpleNamespace(org_id=org_id)


def _run(rows, org_id="org-1"):
    return asyncio.run(top_blocked_reasons(_user(org_id), days=7, limit=10, db=_FakeDB(rows)))


def test_top_blocked_reasons_returns_count_and_latest(monkeypatch):
    ts1 = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    ts2 = datetime(2026, 8, 2, 9, 30, tzinfo=timezone.utc)
    result = _run([
        _Row("pii_detected", 3, ts1),
        _Row("prompt_injection", 1, ts2),
    ])

    assert [r.fired_rule for r in result] == ["pii_detected", "prompt_injection"]
    assert result[0].count == 3
    assert result[0].last_occurred_at == ts1
    assert result[1].count == 1
    assert result[1].last_occurred_at == ts2


def test_top_blocked_reasons_empty_set():
    assert _run([]) == []


def test_top_blocked_reasons_works_without_org(monkeypatch):
    ts = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    result = _run([_Row("secret_detected", 5, ts)], org_id=None)
    assert result[0].fired_rule == "secret_detected"
    assert result[0].count == 5