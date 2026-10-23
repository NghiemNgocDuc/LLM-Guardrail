# Git hooks

## Pre-push: canonical Skill Guard

The hook runs `scripts/scan_agent_skills.py --pre-push` with Python. It reads
committed Markdown under `.cursor/skills/` throughout outgoing commit history,
including intermediate versions later reverted, and checks identical blobs once.
Local working files cannot hide unsafe committed content. New branches check
all reachable skill history. Missing Git objects, unreadable skills, and skill
symlinks block verification.

The standalone Go companion and `SKILL_GUARD_BIN` do not replace this gate.
The hook searches `.venv`, `venv312`, then `python3` / `python`; set `PYTHON` to
a working interpreter if needed. Install the repository's Python dependencies.

## Install once per clone

Run from the repository root:

```bash
./scripts/install-git-hooks.sh
```

On PowerShell:

```powershell
.\scripts\install-git-hooks.ps1
```

This sets `core.hooksPath` to `.githooks` for this repository only.

## Review and manual scans

```bash
python scripts/scan_agent_skills.py
python scripts/scan_agent_skills.py --git-range origin/main..HEAD
python scripts/scan_agent_skills.py --interactive path/to/SKILL.md
```

A blocked scan prints redacted findings and records a local review request.
An integration must honor that decision; the message does not pause an external
agent process. Review the exact content before granting a local override.
Repository-local overrides are separate from hosted workspace approvals.
See [skill logic](../docs/SKILL_LOGIC.md) for the distinction.

[GitHub Actions](../.github/workflows/scan-agent-skills.yml) also checks committed
skills on pull requests and relevant pushes using the canonical Python scanner.
