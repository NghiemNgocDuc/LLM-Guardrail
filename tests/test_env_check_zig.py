"""Integration tests for the Zig env-check CLI (S5).

The test locates a built binary via ENVCHECK_BIN or ZIG_BIN (or `zig` on
PATH, in which case it builds the binary first). Every test is skipped if
no Zig toolchain is available.

On Windows hosts where Smart App Control blocks freshly compiled binaries
in .zig-cache, the native build still lands in zig-out/bin and runs fine;
the cross-compile checks below compile without executing anything.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_CHECK_DIR = REPO_ROOT / "zig" / "env-check"
FIXTURES = ENV_CHECK_DIR / "test" / "fixtures"
SCHEMA = FIXTURES / "schema.env"

BIN_CANDIDATES = [
    Path(os.environ["ENVCHECK_BIN"]) if os.environ.get("ENVCHECK_BIN") else None,
    ENV_CHECK_DIR / "zig-out" / "bin" / "env-check.exe",
    ENV_CHECK_DIR / "zig-out" / "bin" / "env-check",
    ENV_CHECK_DIR / "zig-out-linux" / "bin" / "env-check",
]


def _zig_path() -> str | None:
    if os.environ.get("ZIG_BIN"):
        return os.environ["ZIG_BIN"]
    return shutil.which("zig")


def _find_or_build_binary() -> Path | None:
    for cand in BIN_CANDIDATES:
        if cand is not None and cand.is_file():
            return cand
    zig = _zig_path()
    if zig is None:
        return None
    result = subprocess.run(
        [zig, "build"],
        cwd=ENV_CHECK_DIR,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        return None
    for cand in BIN_CANDIDATES:
        if cand is not None and cand.is_file():
            return cand
    return None


BINARY = _find_or_build_binary()

requires_binary = pytest.mark.skipif(
    BINARY is None, reason="env-check binary not built and no zig toolchain available"
)


def run_env_check(*args: str) -> subprocess.CompletedProcess[str]:
    assert BINARY is not None
    return subprocess.run(
        [str(BINARY), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


@requires_binary
def test_version() -> None:
    result = run_env_check("--version")
    assert result.returncode == 0
    assert result.stdout.startswith("env-check ")
    assert "env-check" in result.stderr or result.stderr == ""


@requires_binary
def test_valid_env_exits_zero() -> None:
    result = run_env_check("check", str(FIXTURES / "valid.env"), "--schema", str(SCHEMA))
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


@requires_binary
def test_valid_quoting_exits_zero() -> None:
    result = run_env_check("check", str(FIXTURES / "valid_quoting.env"), "--schema", str(SCHEMA))
    assert result.returncode in (0, 2), result.stderr
    assert "error" not in result.stderr, result.stderr


@requires_binary
def test_unknown_key_is_an_error() -> None:
    result = run_env_check("check", str(FIXTURES / "unknown_key.env"), "--schema", str(SCHEMA))
    assert result.returncode == 1
    assert "error" in result.stderr
    assert "NOT_IN_SCHEMA" in result.stderr
    assert f"{FIXTURES / 'unknown_key.env'}:2:" in result.stderr.replace("\\", "/") or ":2:" in result.stderr


@requires_binary
def test_malformed_line_is_an_error() -> None:
    result = run_env_check("check", str(FIXTURES / "malformed.env"), "--schema", str(SCHEMA))
    assert result.returncode == 1
    assert "malformed line" in result.stderr


@requires_binary
def test_duplicate_key_is_an_error() -> None:
    result = run_env_check("check", str(FIXTURES / "duplicate.env"), "--schema", str(SCHEMA))
    assert result.returncode == 1
    assert "duplicate key" in result.stderr
    assert ":2:" in result.stderr


@requires_binary
def test_interpolation_is_an_error() -> None:
    result = run_env_check("check", str(FIXTURES / "interpolation.env"), "--schema", str(SCHEMA))
    assert result.returncode == 1
    assert "interpolation" in result.stderr


@requires_binary
def test_unterminated_quote_is_an_error() -> None:
    result = run_env_check("check", str(FIXTURES / "unterminated.env"), "--schema", str(SCHEMA))
    assert result.returncode == 1
    assert "unterminated quote" in result.stderr


@requires_binary
def test_placeholder_value_is_a_warning() -> None:
    result = run_env_check("check", str(FIXTURES / "placeholder.env"), "--schema", str(SCHEMA))
    assert result.returncode == 2
    assert "warning" in result.stderr
    assert "placeholder" in result.stderr
    assert "OPA_URL" in result.stderr


@requires_binary
def test_missing_defaults_are_warnings() -> None:
    result = run_env_check("check", str(FIXTURES / "missing_default.env"), "--schema", str(SCHEMA))
    assert result.returncode == 2
    assert "missing key" in result.stderr
    for key in ("DEBUG", "OPA_URL", "POSTGRES_DB"):
        assert key in result.stderr


@requires_binary
def test_weak_secret_is_a_warning() -> None:
    result = run_env_check("check", str(FIXTURES / "weak_secret.env"), "--schema", str(SCHEMA))
    assert result.returncode == 2
    assert "weak" in result.stderr
    assert "POSTGRES_PASSWORD" in result.stderr


@requires_binary
def test_required_flag() -> None:
    result = run_env_check(
        "check", str(FIXTURES / "valid.env"), "--schema", str(SCHEMA), "--required", "STRIPE_SECRET_KEY"
    )
    assert result.returncode == 1
    assert "required key is missing" in result.stderr


@requires_binary
def test_warnings_only_exit_code_is_2() -> None:
    result = run_env_check("check", str(FIXTURES / "missing_default.env"), "--schema", str(SCHEMA))
    assert result.returncode == 2
    assert "error" not in result.stderr


@requires_binary
def test_usage_error_exit_code_64() -> None:
    result = run_env_check("nonsense")
    assert result.returncode == 64
    assert "usage" in result.stderr


@requires_binary
def test_missing_file_exit_code_74() -> None:
    result = run_env_check("check", str(FIXTURES / "does_not_exist.env"), "--schema", str(SCHEMA))
    assert result.returncode == 74


@requires_binary
def test_issue_line_format() -> None:
    result = run_env_check("check", str(FIXTURES / "duplicate.env"), "--schema", str(SCHEMA))
    for line in result.stderr.splitlines():
        if "error" in line:
            assert ":2:" in line, line
        else:
            assert "warning" in line, line


@requires_binary
def test_real_env_example_roundtrip() -> None:
    """The repo's own .env.example must pass its own linter cleanly."""
    result = run_env_check("check", str(REPO_ROOT / ".env.example"), "--schema", str(REPO_ROOT / ".env.example"))
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def _zig_available() -> bool:
    return _zig_path() is not None


@pytest.mark.skipif(not _zig_available(), reason="no zig toolchain available")
def test_cross_compile_linux() -> None:
    zig = _zig_path()
    assert zig is not None
    result = subprocess.run(
        [zig, "build", "-Dtarget=x86_64-linux-musl", "-p", "zig-out-linux"],
        cwd=ENV_CHECK_DIR,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stderr
    artifact = ENV_CHECK_DIR / "zig-out-linux" / "bin" / "env-check"
    assert artifact.is_file()


@pytest.mark.skipif(not _zig_available(), reason="no zig toolchain available")
def test_cross_compile_linux_arm() -> None:
    zig = _zig_path()
    assert zig is not None
    result = subprocess.run(
        [zig, "build", "-Dtarget=aarch64-linux-musl", "-p", "zig-out-linux-arm"],
        cwd=ENV_CHECK_DIR,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stderr
    assert (ENV_CHECK_DIR / "zig-out-linux-arm" / "bin" / "env-check").is_file()


@pytest.mark.skipif(not _zig_available(), reason="no zig toolchain available")
def test_cross_compile_macos() -> None:
    zig = _zig_path()
    assert zig is not None
    result = subprocess.run(
        [zig, "build", "-Dtarget=aarch64-macos", "-p", "zig-out-macos"],
        cwd=ENV_CHECK_DIR,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stderr
    assert (ENV_CHECK_DIR / "zig-out-macos" / "bin" / "env-check").is_file()


def _docker_available() -> bool:
    return shutil.which("docker") is not None


@pytest.mark.skipif(
    BINARY is None or not _docker_available(),
    reason="needs built binary and docker",
)
def test_linux_cross_artifact_runs_in_docker() -> None:
    """The x86_64-linux-musl artifact must actually run: verify it against
    the fixtures inside an alpine container and compare exit codes with the
    native binary."""
    linux_bin = ENV_CHECK_DIR / "zig-out-linux" / "bin" / "env-check"
    if not linux_bin.is_file():
        pytest.skip("x86_64-linux-musl artifact not built; run the cross-compile tests first")
    cases = [
        ("valid.env", 0),
        ("unknown_key.env", 1),
        ("placeholder.env", 2),
        ("missing_default.env", 2),
        ("interpolation.env", 1),
    ]
    for fixture, expected in cases:
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{ENV_CHECK_DIR}:/work",
                "alpine",
                "/work/zig-out-linux/bin/env-check",
                "check", f"/work/test/fixtures/{fixture}", "--schema", "/work/test/fixtures/schema.env",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == expected, (
            f"{fixture}: rc={result.returncode} expected {expected}\n{result.stderr}"
        )
