"""
Haskell `rego-lint` integration tests.

`rego-lint` (haskell/rego-lint) is an optional offline Rego syntax linter
that runs as a fast-fail pre-check inside `opa.validate` (and therefore the
/validate-rego and PATCH /policy endpoints). The binary is detected via
`REGOLINT_BIN` or PATH; every test here is skipped when it is not installed
(e.g. on Windows without a native build) — the OPA compile check remains the
authoritative gate either way.
"""
import os
import shutil
import subprocess

import pytest

from guardrails import opa

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "haskell", "rego-lint", "test", "fixtures")


def _binary():
    return os.environ.get("REGOLINT_BIN") or shutil.which("rego-lint")


def _fixture(name: str) -> str:
    return os.path.join(FIXTURES, name)


requires_binary = pytest.mark.skipif(
    _binary() is None,
    reason="rego-lint binary not available — build haskell/rego-lint (see its README) or set REGOLINT_BIN",
)


@requires_binary
def test_valid_rule_exits_zero():
    proc = subprocess.run([_binary(), _fixture("valid_rule.rego")], capture_output=True, text=True)
    assert proc.returncode == 0
    assert proc.stderr.strip() == ""
    assert proc.stdout.strip() == ""


@requires_binary
@pytest.mark.parametrize(
    "fixture,fragment",
    [
        ("invalid_unbalanced.rego", "unterminated '{'"),
        ("invalid_no_body.rego", "must have a body or value"),
        ("invalid_package_order.rego", "statement before package"),
        ("invalid_unterminated_string.rego", "unterminated string"),
        ("invalid_default.rego", "default rule requires a value"),
        ("invalid_dup_package.rego", "duplicate package"),
        ("invalid_missing_package.rego", "missing package"),
        ("invalid_stray_brace.rego", "unexpected '}'"),
        ("invalid_malformed_number.rego", "malformed number"),
        ("invalid_contains_no_body.rego", "must have a body or value"),
    ],
)
def test_invalid_fixtures_exit_nonzero_with_per_issue_lines(fixture, fragment):
    proc = subprocess.run([_binary(), _fixture(fixture)], capture_output=True, text=True)
    assert proc.returncode == 1
    assert fragment in proc.stderr
    for line in proc.stderr.strip().splitlines():
        assert ": error: " in line
        assert ":".join(line.split(":")[:2])  # FILE:LINE:COL prefix present


@requires_binary
def test_stdin_mode():
    proc = subprocess.run(
        [_binary(), "-"],
        input="package guardrails\nallow\n",
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "2:1: error: rule 'allow' must have a body or value" in proc.stderr
    clean = subprocess.run(
        [_binary(), "-"],
        input="package guardrails\nallow if { true }\n",
        capture_output=True,
        text=True,
    )
    assert clean.returncode == 0


def test_skipped_silently_when_binary_missing(monkeypatch):
    monkeypatch.delenv("REGOLINT_BIN", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _: None)
    assert opa.rego_lint("package guardrails\nallow\n") is None


@requires_binary
def test_rego_lint_fast_fail_inside_validate_without_opa(monkeypatch):
    """Invalid Rego must be rejected by the linter BEFORE the OPA round trip
    (no OPA client involved at all)."""
    monkeypatch.setenv("REGOLINT_BIN", _binary())
    monkeypatch.setattr(opa, "_client", lambda: pytest.fail("OPA client must not be touched"))
    with pytest.raises(opa.OPAValidationError, match="rego-lint"):
        opa.validate("package guardrails\nallow\n")
    # Valid Rego with a package passes the linter and reaches the OPA client
    # (which fails closed as unavailable — the authoritative check is OPA's).
    opa.reset_client()


@requires_binary
def test_valid_rego_reaches_opa_round_trip(monkeypatch):
    monkeypatch.setenv("REGOLINT_BIN", _binary())
    calls = []

    class _FakeResp:
        status_code = 200

    class _FakeClient:
        def put(self, *_a, **_k):
            calls.append("put")
            return _FakeResp()

        def delete(self, *_a, **_k):
            return _FakeResp()

    monkeypatch.setattr(opa, "_client", lambda: _FakeClient())
    opa.validate("package guardrails\nallow if { true }\n")
    assert calls == ["put"]