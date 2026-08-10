"""Tests for POST /policy/diff."""
import asyncio

from app.routers.policy import diff_policy
from app.schemas import PolicyDiffRequest


def _run(policy_a, policy_b):
    return asyncio.run(diff_policy(PolicyDiffRequest(policy_a=policy_a, policy_b=policy_b), object()))


def _full_policy(**overrides):
    base = {
        "input_rules": {"block_secrets": True, "block_jailbreak": True},
        "output_rules": {"block_toxic_content": True},
        "topic_policy": {"blocked_topics": ["medical advice"]},
        "compliance_rules": {"block_medical_advice": True},
        "llm_backend": "groq",
        "llm_model": "llama-3.3-70b-versatile",
        "rate_limit_rpm": 60,
        "rate_limit_rpd": 1000,
    }
    base.update(overrides)
    return base


def test_no_diff_when_identical():
    p = _full_policy()
    assert _run(p, _full_policy()) == []


def test_all_fields_differ():
    a = _full_policy()
    b = _full_policy(
        input_rules={"block_secrets": False, "block_jailbreak": False},
        output_rules={"block_toxic_content": False},
        topic_policy={"blocked_topics": []},
        compliance_rules={"block_medical_advice": False},
        llm_backend="anthropic",
        llm_model="claude-sonnet-4",
        rate_limit_rpm=10,
        rate_limit_rpd=100,
    )
    result = _run(a, b)

    assert {e.field for e in result} == {
        "input_rules", "output_rules", "topic_policy", "compliance_rules",
        "llm_backend", "llm_model", "rate_limit_rpm", "rate_limit_rpd",
    }
    by_field = {e.field: e for e in result}
    assert by_field["llm_backend"].before == "groq"
    assert by_field["llm_backend"].after == "anthropic"
    assert by_field["rate_limit_rpm"].before == 60
    assert by_field["rate_limit_rpm"].after == 10


def test_single_field_diff():
    a = _full_policy()
    b = _full_policy(llm_model="claude-sonnet-4-20250514")
    result = _run(a, b)

    assert len(result) == 1
    assert result[0].field == "llm_model"
    assert result[0].before == "llama-3.3-70b-versatile"
    assert result[0].after == "claude-sonnet-4-20250514"


def test_nested_blob_compared_wholesale():
    a = _full_policy(input_rules={
        "block_pii": True,
        "pii_patterns": [{"name": "ssn", "regex": r"\b\d{3}-\d{2}-\d{4}\b"}],
    })
    b = _full_policy(input_rules={
        "block_pii": True,
        "pii_patterns": [{"name": "credit_card", "regex": r"\b(?:\d[ -]?){13,16}\b"}],
    })
    result = _run(a, b)

    assert len(result) == 1
    assert result[0].field == "input_rules"
    assert result[0].before["pii_patterns"][0]["name"] == "ssn"
    assert result[0].after["pii_patterns"][0]["name"] == "credit_card"


def test_missing_field_reported_with_none_side():
    a = _full_policy()
    a.pop("rate_limit_rpd")
    result = _run(a, _full_policy())

    assert len(result) == 1
    assert result[0].field == "rate_limit_rpd"
    assert result[0].before is None
    assert result[0].after == 1000