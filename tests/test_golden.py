"""
Golden-test harness for guardrail verdicts.

Each fixture in tests/golden/cases.json runs the real InputGuardrail /
OutputGuardrail and compares the verdict (allowed, reason_code, warned)
against the recorded expectation — protecting against silent regressions
in the rule pipeline.

Regenerate expectations after an intentional behaviour change:

    GOLDEN_UPDATE=1 python -m pytest tests/test_golden.py -q

The harness rewrites only the "expect" block of each case.
"""
import json
import os
import pathlib

import pytest

from guardrails.input import InputGuardrail
from guardrails.output import OutputGuardrail

pytestmark = pytest.mark.usefixtures("engine_mode")

_GOLDEN_FILE = pathlib.Path(__file__).parent / "golden" / "cases.json"

_INPUT_DEFAULTS = {
    "block_secrets": True,
    "block_pii": True,
    "pii_patterns": [
        {"name": "credit_card", "regex": r"\b(?:\d[ -]?){13,16}\b"},
        {"name": "ssn", "regex": r"\b\d{3}-\d{2}-\d{4}\b"},
        {"name": "email", "regex": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"},
    ],
    "block_prompt_injection": True,
    "block_jailbreak": True,
}

_OUTPUT_DEFAULTS = {
    "policy": {"enforce_schema": False, "block_toxic_content": True},
    "compliance": {"block_medical_advice": True},
    "topics": {"blocked_topics": []},
}


def _verdict(case: dict) -> dict:
    if case["kind"] == "input":
        policy = dict(_INPUT_DEFAULTS)
        policy.update(case.get("policy") or {})
        result = InputGuardrail(policy).check(case["input"])
    else:
        policy = dict(_OUTPUT_DEFAULTS["policy"])
        policy.update(case.get("policy") or {})
        compliance = dict(_OUTPUT_DEFAULTS["compliance"])
        compliance.update(case.get("compliance") or {})
        topics = dict(_OUTPUT_DEFAULTS["topics"])
        topics.update(case.get("topics") or {})
        result = OutputGuardrail(policy, compliance, topics).check(case["response"])
    return {
        "allowed": bool(result.allowed),
        "reason_code": result.reason_code,
        "warned": bool(result.warned),
    }


def _load_cases() -> list[dict]:
    data = json.loads(_GOLDEN_FILE.read_text(encoding="utf-8"))
    if os.environ.get("GOLDEN_UPDATE") == "1":
        for case in data["cases"]:
            case["expect"] = _verdict(case)
        _GOLDEN_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
        )
    return data["cases"]


def test_golden_verdicts_match():
    failures = []
    for case in _load_cases():
        actual = _verdict(case)
        expected = case.get("expect", {})
        missing = [k for k in expected if k not in actual]
        mismatched = [k for k in expected if k in actual and actual[k] != expected[k]]
        if missing or mismatched:
            failures.append(f"{case['id']}: expected {expected}, got {actual}")
    assert not failures, "Golden verdict mismatches:\n" + "\n".join(failures)


def test_golden_cases_are_sane():
    for case in _load_cases():
        assert case.get("id"), "every golden case needs an id"
        assert case["kind"] in ("input", "output"), f"{case['id']}: bad kind"
        assert case.get("input") or case.get("response"), f"{case['id']}: missing input/response"
        assert "expect" in case, f"{case['id']}: missing expect block"