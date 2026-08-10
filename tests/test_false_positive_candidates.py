"""Tests for GET /analytics/false-positive-candidates."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.routers.analytics import false_positive_candidates


class _Log:
    def __init__(self, rule, status="input_blocked", preview="prompt"):
        self.id = f"log-{rule}-{preview}"
        self.status = status
        self.fired_rule = rule
        self.prompt_preview = preview
        self.created_at = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


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
        (_Log("pii_detected"), 1, None),        # disputed: thumbs-up
        (_Log("pii_detected"), 1, None),
        (_Log("toxic_content"), 1, None),
    ]
    result = _run(rows)

    assert [r["fired_rule"] for r in result] == ["pii_detected", "toxic_content"]
    assert result[0]["count"] == 2
    assert result[1]["count"] == 1
    assert result[0]["examples"][0]["positive_feedback"] is True


def test_rows_without_signal_are_excluded():
    rows = [
        (_Log("secret_detected"), -1, None),          # thumbs-down: user agreed with the block
        (_Log("jailbreak_attempt"), None, None),      # no feedback, no override
        (_Log("jailbreak_attempt"), 0, None),
    ]
    assert _run(rows) == []


def test_always_allow_override_counts_as_signal():
    overrides = {"always_allow_reason_codes": ["toxic_content"], "always_allow_keys": ["x"]}
    rows = [(_Log("toxic_content"), None, overrides)]
    result = _run(rows)

    assert len(result) == 1
    assert result[0]["fired_rule"] == "toxic_content"
    assert result[0]["examples"][0]["override_hit"] is True
    assert result[0]["examples"][0]["positive_feedback"] is False


def test_override_for_other_rules_is_not_a_signal():
    rows = [(_Log("toxic_content"), None, {"always_allow_reason_codes": ["pii_detected"]})]
    assert _run(rows) == []


def test_empty_overrides_dict_is_not_a_signal():
    rows = [(_Log("toxic_content"), None, {})]
    assert _run(rows) == []


def test_examples_capped_and_limit_applied():
    rows = [
        (_Log("pii_detected", preview=chr(97 + i)), 1, None)
        for i in range(10)
    ]
    result = _run(rows, limit=1)

    assert len(result) == 1
    assert result[0]["count"] == 10
    assert len(result[0]["examples"]) == 5  # example cap


def test_results_sorted_by_count_desc():
    rows = [
        (_Log("a"), 1, None),
        (_Log("b"), 1, None),
        (_Log("b"), 1, None),
        (_Log("b"), 1, None),
    ]
    result = _run(rows)
    assert [r["fired_rule"] for r in result] == ["b", "a"]


def test_works_without_org_scope():
    rows = [(_Log("medical_advice"), 1, None)]
    result = _run(rows, org_id=None)
    assert result[0]["fired_rule"] == "medical_advice"
    assert result[0]["count"] == 1