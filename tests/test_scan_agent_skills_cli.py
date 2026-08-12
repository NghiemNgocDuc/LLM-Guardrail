import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "scan_agent_skills.py"

pytestmark = pytest.mark.usefixtures("engine_mode")


def test_scan_cli_passes_on_safe_example_skill():
    path = REPO_ROOT / ".cursor" / "skills" / "example-safe" / "SKILL.md"
    assert path.is_file()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK" in proc.stdout


def test_scan_cli_fails_on_leaked_secret(tmp_path):
    bad = tmp_path / "SKILL.md"
    bad.write_text("staging key: grg_" + "a" * 40 + "\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(bad)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "REJECTED" in proc.stdout
    assert "Why:" in proc.stdout
