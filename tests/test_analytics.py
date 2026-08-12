"""Tests for GET /analytics/top-blocked-reasons (view-backed).

The endpoint reads mv_blocked_reasons_daily and sums the per-org per-day rows
back into one row per fired rule. The fake DB below stands in for the view.
"""
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
    """Emulates the endpoint's SQL: group per-org per-day rows by fired_rule,
    sum counts, take max last_occurred_at, sort by count desc, limit."""

    def __init__(self, rows):
        self._rows = rows

    def all(self):
        by_rule: dict[str, _Row] = {}
        for r in self._rows:
            agg = by_rule.setdefault(r.fired_rule, _Row(r.fired_rule, 0, r.last_occurred_at))
            agg.cnt += r.cnt
            if r.last_occurred_at and (agg.last_occurred_at is None or r.last_occurred_at > agg.last_occurred_at):
                agg.last_occurred_at = r.last_occurred_at
        return sorted(by_rule.values(), key=lambda r: r.cnt, reverse=True)[:10]


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, stmt):
        return _FakeResult(self._rows)


def _user(org_id="org-1"):
    return SimpleNamespace(org_id=org_id)


def _run(rows, org_id="org-1"):
    return asyncio.run(top_blocked_reasons(_user(org_id), days=7, limit=10, db=_FakeDB(rows)))


def test_top_blocked_reasons_returns_count_and_latest():
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


def test_top_blocked_reasons_sums_days_per_rule():
    # Two daily rows for the same rule must collapse into one with the sum of
    # counts and the max last_occurred_at.
    ts1 = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    ts2 = datetime(2026, 8, 2, 9, 30, tzinfo=timezone.utc)
    ts3 = datetime(2026, 8, 2, 14, 0, tzinfo=timezone.utc)
    result = _run([
        _Row("secret_detected", 2, ts1),
        _Row("secret_detected", 5, ts2),
        _Row("pii_detected", 1, ts3),
    ])

    assert [r.fired_rule for r in result] == ["secret_detected", "pii_detected"]
    assert result[0].count == 7
    assert result[0].last_occurred_at == ts2


def test_top_blocked_reasons_empty_set():
    assert _run([]) == []


def test_top_blocked_reasons_works_without_org():
    ts = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    result = _run([_Row("secret_detected", 5, ts)], org_id=None)
    assert result[0].fired_rule == "secret_detected"
    assert result[0].count == 5