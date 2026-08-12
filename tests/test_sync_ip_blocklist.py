"""Unit tests for scripts/sync_ip_blocklist.py (pure logic — no Redis, DB, or nft).

Covers the blocklist construction rules: union of explicit blocked_ips and
Redis repeat offenders above the threshold, IPv4-only validation, dedupe,
sorting, and the full-rebuild ruleset rendering (stale entries vanish by
construction on the next sync).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from sync_ip_blocklist import build_blocklist, render_ruleset  # noqa: E402


def test_explicit_ips_always_included():
    ips = build_blocklist(["10.0.0.1", "192.168.0.5"], {}, threshold=3)
    assert ips == ["10.0.0.1", "192.168.0.5"]


def test_redis_violations_above_threshold_included():
    violations = {"203.0.113.9": 3, "203.0.113.10": 2, "203.0.113.11": 99}
    ips = build_blocklist([], violations, threshold=3)
    assert ips == ["203.0.113.11", "203.0.113.9"]  # lexicographic sort


def test_threshold_is_inclusive():
    assert "203.0.113.9" in build_blocklist([], {"203.0.113.9": 3}, threshold=3)
    assert "203.0.113.9" not in build_blocklist([], {"203.0.113.9": 2}, threshold=3)


def test_invalid_and_ipv6_skipped():
    violations = {"not-an-ip": 99, "203.0.113.1": 3}
    explicit = ["2001:db8::1", "999.1.1.1", ""]
    ips = build_blocklist(explicit, violations, threshold=3)
    assert ips == ["203.0.113.1"]


def test_deduped_and_sorted():
    ips = build_blocklist(
        ["203.0.113.5", "10.0.0.1", "203.0.113.5"],
        {"203.0.113.1": 3, "10.0.0.1": 9},
        threshold=3,
    )
    assert ips == ["10.0.0.1", "203.0.113.1", "203.0.113.5"]


def test_whitespace_stripped():
    ips = build_blocklist([" 203.0.113.2 "], {}, threshold=3)
    assert ips == ["203.0.113.2"]


def test_empty_blocklist_renders_flush_only():
    ruleset = render_ruleset([])
    assert ruleset == "flush set inet guardrails blocklist\n"


def test_ruleset_is_full_rebuild():
    ruleset = render_ruleset(["10.0.0.1", "203.0.113.9"])
    assert ruleset == (
        "flush set inet guardrails blocklist\n"
        "add element inet guardrails blocklist { 10.0.0.1, 203.0.113.9 }\n"
    )


def test_stale_ips_disappear_on_next_sync():
    first = render_ruleset(build_blocklist([], {"203.0.113.1": 3}, threshold=3))
    assert "203.0.113.1" in first
    second = render_ruleset(build_blocklist([], {}, threshold=3))
    assert "203.0.113.1" not in second
    assert "add element" not in second
