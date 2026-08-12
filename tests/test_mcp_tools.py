"""Tests for the scan_repo and explain_policy MCP tools."""
import asyncio
import json

import pytest

from app.mcp_server import (
    MAX_CONTENT_CHARS,
    TOOL_REGISTRY,
    _call_tool,
    _validate_tool_call,
)

pytestmark = pytest.mark.usefixtures("engine_mode")


def _call(name: str, args: dict):
    return asyncio.run(_call_tool(name, args))


def _ok(name: str, args: dict) -> dict:
    resp = _call(name, args)
    assert resp.get("isError") is False, resp
    return json.loads(resp["content"][0]["text"])


# ─── scan_repo ────────────────────────────────────────────────────────────────


def test_scan_repo_registered():
    assert "scan_repo" in TOOL_REGISTRY
    assert _validate_tool_call("scan_repo", {"files_json": "[]"}) is not None
    assert _validate_tool_call(
        "scan_repo", {"files_json": json.dumps([{"filename": "a.md", "content": "hi"}])}
    ) is None


def test_scan_repo_happy_path():
    files = [
        {"filename": "clean/SKILL.md", "content": "Run tests before merging."},
        {"filename": "config/keys.md", "content": "password=s3cret_value"},
        {"filename": "ops/cleanup.md", "content": "Cleanup script: DROP TABLE users;"},
    ]
    data = _ok("scan_repo", {"files_json": json.dumps(files)})
    assert data["summary"]["files_scanned"] == 3
    assert data["summary"]["files_with_findings"] == 2
    assert data["summary"]["overall_risk_score"] == 0.95
    by_severity = data["summary"]["findings_by_severity"]
    assert by_severity == {"critical": 1, "high": 2, "medium": 0}

    by_file = {r["filename"]: r for r in data["results"]}
    assert by_file["clean/SKILL.md"]["safe"] is True
    assert by_file["clean/SKILL.md"]["findings"] == []
    assert by_file["config/keys.md"]["safe"] is False
    assert any(
        f["reason_code"] == "credential_assignment"
        for f in by_file["config/keys.md"]["findings"]
    )
    assert by_file["ops/cleanup.md"]["risk_score"] == 0.95
    drop = next(
        f for f in by_file["ops/cleanup.md"]["findings"]
        if f["reason_code"] == "drop_sql"
    )
    assert drop["severity"] == "critical"
    assert drop["line_number"] == 1


def test_scan_repo_rejects_malformed_json():
    resp = _call("scan_repo", {"files_json": "{not json"})
    assert resp.get("isError") is True
    assert "valid JSON" in json.loads(resp["content"][0]["text"])["error"]

    resp = _call("scan_repo", {"files_json": "[1, 2]"})
    assert resp.get("isError") is True


def test_scan_repo_rejects_non_array():
    resp = _call("scan_repo", {"files_json": json.dumps({"filename": "a.md", "content": "x"})})
    assert resp.get("isError") is True


def test_scan_repo_rejects_empty_file_list():
    resp = _call("scan_repo", {"files_json": "[]"})
    assert resp.get("isError") is True
    assert _validate_tool_call("scan_repo", {"files_json": "[]"}) is not None
    assert _validate_tool_call("scan_repo", {"files_json": ""}) is not None


def test_scan_repo_rejects_oversized_file():
    files = [{"filename": "big.md", "content": "x" * (MAX_CONTENT_CHARS + 1)}]
    resp = _call("scan_repo", {"files_json": json.dumps(files)})
    assert resp.get("isError") is True


def test_scan_repo_rejects_too_many_files():
    files = [{"filename": f"f{i}.md", "content": "ok"} for i in range(201)]
    resp = _call("scan_repo", {"files_json": json.dumps(files)})
    assert resp.get("isError") is True


def test_scan_repo_rejects_entries_with_missing_or_blank_fields():
    for entry in (
        {"content": "x"},
        {"filename": "a.md"},
        {"filename": "", "content": "x"},
        {"filename": "a.md", "content": "  "},
        {"filename": "a" * 300, "content": "x"},
    ):
        resp = _call("scan_repo", {"files_json": json.dumps([entry])})
        assert resp.get("isError") is True, entry


# ─── explain_policy ───────────────────────────────────────────────────────────


def test_explain_policy_registered():
    assert "explain_policy" in TOOL_REGISTRY
    assert _validate_tool_call("explain_policy", {"policy_json": json.dumps({})}) is None
    assert _validate_tool_call("explain_policy", {"policy_json": ""}) is not None


def test_explain_policy_happy_path():
    policy = {
        "input_rules": {
            "block_secrets": True,
            "block_pii": True,
            "pii_patterns": [
                {"name": "email", "regex": r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}"},
                {"name": "credit_card", "regex": r"\b\d{4}-\d{4}-\d{4}-\d{4}\b"},
            ],
            "block_prompt_injection": True,
            "injection_keywords": ["ignore system instructions"],
            "block_jailbreak": True,
            "jailbreak_mode": "warn",
            "semantic_mode": "block",
            "semantic_blocked_texts": ["internal pricing", "undisclosed roadmap"],
            "semantic_threshold": 0.75,
        },
        "output_rules": {
            "enforce_schema": True,
            "required_fields": ["answer", "citations"],
            "block_toxic_content": True,
        },
        "topic_policy": {"blocked_topics": ["medical advice", "competitor products"]},
        "compliance_rules": {"block_medical_advice": True, "never_discuss_competitors": True},
    }
    data = _ok("explain_policy", {"policy_json": json.dumps(policy)})
    summary = data["summary"]
    assert "blocks prompts containing secrets" in summary
    assert "PII (email, credit_card)" in summary
    assert "plus 1 custom keyword(s)" in summary
    assert "warns instead of blocking jailbreak attempts" in summary
    assert "semantic similarity block is enabled for 2 blocked phrase(s) at threshold 0.75" in summary
    assert "required fields: answer, citations" in summary
    assert "blocks toxic content" in summary
    assert "blocks responses covering topics: medical advice, competitor products" in summary
    assert "blocks medical-advice statements" in summary
    assert "credential leakage in responses always blocks" in summary


def test_explain_policy_reports_disabled_rules_and_defaults():
    data = _ok("explain_policy", {"policy_json": "{}"})
    summary = data["summary"]
    assert "blocks prompts containing secrets" in summary
    assert "PII detection is disabled" in summary
    assert "prompt-injection detection is disabled" in summary
    assert "jailbreak detection is disabled" in summary
    assert "semantic similarity blocking is disabled" in summary
    assert "credential leakage in responses always blocks" in summary
    assert "JSON schema enforcement is disabled" in summary
    assert "toxic-content filtering is disabled" in summary


def test_explain_policy_rejects_malformed_json():
    resp = _call("explain_policy", {"policy_json": "{not json"})
    assert resp.get("isError") is True
    assert "valid JSON" in json.loads(resp["content"][0]["text"])["error"]


def test_explain_policy_rejects_non_object_json():
    resp = _call("explain_policy", {"policy_json": "[1, 2, 3]"})
    assert resp.get("isError") is True
    assert "JSON object" in json.loads(resp["content"][0]["text"])["error"]


def test_explain_policy_rejects_missing_or_blank_input():
    for args in ({"policy_json": ""}, {"policy_json": "   "}, {}):
        resp = _call("explain_policy", args)
        assert resp.get("isError") is True, args


def test_explain_policy_rejects_oversized_policy():
    resp = _call("explain_policy", {"policy_json": "{" + ("x" * 10_001) + "}"})
    assert resp.get("isError") is True