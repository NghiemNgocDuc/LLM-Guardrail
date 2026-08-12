"""Fixture-driven skill guardrail tests.

These read the same files under fixtures/skills/ that the Go port
(cli/guardrail-scan) scans, so drift between the Python and Go
implementations is caught by the Go parity test (parity_test.go).
"""

from pathlib import Path

import pytest

from guardrails.skill import SkillGuardrail

pytestmark = pytest.mark.usefixtures("engine_mode")

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "skills"


def _scan(name: str):
    return SkillGuardrail().scan((FIXTURES / name).read_text(encoding="utf-8"))


def test_fixture_clean_skill():
    result = _scan("clean-skill.md")
    assert result.safe
    assert result.findings == []


def test_fixture_gateway_key():
    result = _scan("gateway-key-skill.md")
    assert any(f.reason_code == "gateway_api_key" for f in result.findings)


def test_fixture_database_url():
    result = _scan("database-url-skill.md")
    codes = {f.reason_code for f in result.findings}
    assert "database_url" in codes
    assert "private_ip" in codes


def test_fixture_hardcoded_credential_line():
    result = _scan("hardcoded-credential-skill.md")
    cred = next(f for f in result.findings if f.reason_code == "credential_assignment")
    assert cred.line_number == 2


def test_fixture_drop_table():
    result = _scan("drop-table-skill.md")
    drop = next(f for f in result.findings if f.reason_code == "drop_sql")
    assert drop.category == "destructive_command"
    assert drop.severity == "critical"


def test_fixture_rm_rf_root():
    result = _scan("rm-rf-root-skill.md")
    assert any(f.reason_code == "rm_rf_destructive" for f in result.findings)


def test_fixture_curl_pipe_shell():
    result = _scan("curl-pipe-shell-skill.md")
    assert any(f.reason_code == "curl_pipe_shell" for f in result.findings)


def test_fixture_rm_rf_dist_clean():
    result = _scan("rm-rf-dist-skill.md")
    assert not any(f.reason_code == "rm_rf_destructive" for f in result.findings)


def test_fixture_multi_finding_order():
    result = _scan("multi-finding-skill.md")
    codes = [f.reason_code for f in result.findings]
    assert codes == [
        "drop_sql",
        "secret_detected",
        "database_url",
        "private_ip",
        "internal_path",
    ]
    assert result.risk_score == 0.95
