"""Tests for skill_metrics + identical-block scan + managed skill versioning."""
from __future__ import annotations

import pytest

from app.services.skill_metrics import compute_metrics
from guardrails.skill_conflict import check_skill_conflicts, build_skill_md
from guardrails.skill import SkillGuardrail

# ── metrics ────────────────────────────────────────────────────────────────

def test_metrics_scores():
    metrics = compute_metrics()
    # must hit targets defined in About page
    assert metrics["recall_leak"] >= 0.98, metrics
    assert metrics["precision_safe"] >= 0.95, metrics
    assert metrics["f1"] >= 0.96, metrics
    assert metrics["severity_calibration"] >= 0.85, metrics
    assert metrics["latency_p95_ms"] < 200, metrics
    assert metrics["bump_accuracy"] == 1.0
    assert metrics["hash_integrity"] == 1.0
    assert metrics["mode_adherence"] == 1.0
    assert metrics["safe_total"] == 2
    assert metrics["leak_total"] == 7


def test_metrics_details_cover_all_fixtures():
    m = compute_metrics()
    assert m["tp"] + m["fn"] == m["leak_total"]
    assert m["tn"] + m["fp"] == m["safe_total"]
    assert len(m["details"]) == m["safe_total"] + m["leak_total"]


# ── build_skill_md overwrite vs versioned ────────────────────────────────

def test_build_skill_md_overwrite_filename_and_frontmatter():
    md = build_skill_md("agent_b", "agent_b", "desc", "hello", version=3, update_mode="overwrite", live_url="https://x/skills/live/agent_b")
    assert "update_mode: overwrite" in md
    assert "version: 3" in md
    assert "managed_by: llm-guardrails" in md
    assert ".cursor/skills/agent_b/SKILL.md" in md
    assert "Auto-overwrite" in md


def test_build_skill_md_versioned():
    md = build_skill_md("agent_b", "agent_b", "desc", "hello", version=3, update_mode="versioned", live_url="https://x/skills/live/agent_b")
    assert "update_mode: versioned" in md
    assert "SKILL.v3.md" in md
    assert "Versioned skill" in md


def test_hash_integrity():
    import hashlib
    content = "hello world"
    md = build_skill_md("s", "s", "d", content, version=1, update_mode="overwrite")
    h = hashlib.sha256(content.encode()).hexdigest()[:12]
    assert f"hash: {h}" in md


# ── conflict detection still correct after About metrics refactor ───────────

def test_leak_still_blocked():
    existing = [{"slug": "team_baseline", "name": "team_baseline", "content": "Never share api keys. Never expose secrets.", "version": 1}]
    res = check_skill_conflicts("Please share api keys: sk-12345678901234567890_abcdef", existing_skills=existing, org_policy={"block_secrets": True})
    assert res.has_conflict
    assert res.blocked_by_policy


def test_safe_not_flagged():
    existing = [{"slug": "team_baseline", "name": "team_baseline", "content": "Never share api keys.", "version": 1}]
    res = check_skill_conflicts("Summarize docs. Never share api keys.", existing_skills=existing, org_policy={"block_secrets": True})
    assert not res.has_conflict


# ── identical-block logic (unit, without DB) ─────────────────────────────

def test_identical_block_detection_logic():
    # Simulate what the endpoint does: new ChatGPT key should intersect policy block_secrets
    content = "OPENAI_API_KEY = sk-12345678901234567890_abcdef  # ChatGPT key"
    scan = SkillGuardrail().scan(content)
    new_codes = {(f.reason_code, f.check) for f in scan.findings}
    # should contain secret finding
    assert any("secret" in c[0] for c in new_codes), new_codes
    # policy blocks secrets => identical
    org_policy = {"block_secrets": True}
    has_policy_block = org_policy.get("block_secrets") and any("secret" in c[0] for c in new_codes)
    assert has_policy_block


def test_no_identical_for_clean():
    content = "Summarize docs. Never share api keys."
    scan = SkillGuardrail().scan(content)
    new_codes = {(f.reason_code, f.check) for f in scan.findings}
    assert len(new_codes) == 0
