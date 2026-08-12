"""Tests for GET /analytics/false-positive-candidates (view-backed).

The endpoint reads mv_false_positive_candidates_daily — one row per disputed
request, with the feedback/override join already applied by the view — and
groups by fired rule. The fake DB below stands in for the view.
"""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.routers.analytics import false_positive_candidates


class _Row:
    def __init__(self, rule, preview="prompt", positive=False, override=False,
                 status="input_blocked"):
        self.request_log_id = f"log-{rule}-{preview}"
        self.status = status
        self.fired_rule = rule
        self.prompt_preview = preview
        self.created_at = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        self.positive_feedback = positive
        self.override_hit = override


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return self


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, stmt):
        return _Result(self._rows)


def _user(org_id="org-1"):
    return SimpleNamespace(org_id=org_id)


def _run(rows, org_id="org-1", limit=10):
    return asyncio.run(false_positive_candidates(_user(org_id), days=7, limit=limit, db=_FakeDB(rows)))


def test_positive_feedback_rows_are_candidates():
    rows = [
        _Row("pii_detected", preview="a", positive=True),
        _Row("pii_detected", preview="b", positive=True),
        _Row("toxic_content", preview="c", positive=True),
    ]
    result = _run(rows)

    assert [r["fired_rule"] for r in result] == ["pii_detected", "toxic_content"]
    assert result[0]["count"] == 2
    assert result[1]["count"] == 1
    assert result[0]["examples"][0]["positive_feedback"] is True


def test_always_allow_override_counts_as_signal():
    rows = [_Row("toxic_content", positive=False, override=True)]
    result = _run(rows)

    assert len(result) == 1
    assert result[0]["fired_rule"] == "toxic_content"
    assert result[0]["examples"][0]["override_hit"] is True
    assert result[0]["examples"][0]["positive_feedback"] is False


def test_examples_capped_and_limit_applied():
    rows = [
        _Row("pii_detected", preview=chr(97 + i), positive=True)
        for i in range(10)
    ]
    result = _run(rows, limit=1)

    assert len(result) == 1
    assert result[0]["count"] == 10
    assert len(result[0]["examples"]) == 5  # example cap


def test_results_sorted_by_count_desc():
    rows = [
        _Row("a", preview="a", positive=True),
        _Row("b", preview="b", positive=True),
        _Row("b", preview="c", positive=True),
        _Row("b", preview="d", positive=True),
    ]
    result = _run(rows)
    assert [r["fired_rule"] for r in result] == ["b", "a"]


def test_works_without_org_scope():
    rows = [_Row("medical_advice", positive=True)]
    result = _run(rows, org_id=None)
    assert result[0]["fired_rule"] == "medical_advice"
    assert result[0]["count"] == 1
