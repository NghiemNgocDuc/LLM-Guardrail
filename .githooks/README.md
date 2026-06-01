# Git hooks

## Pre-push — Skill Guard

Runs before `git push` and scans `.cursor/skills/**` files included in the outgoing commits.

Blocks the push when the scanner finds secrets, PII, or destructive shell/SQL commands.

If the push touches skills and issues are found, the hook accepts **chat-style commands** first:

- Type **`always allow`** or **`always allow all`** once (no per-issue key presses)
- Or press Enter and choose per issue: **Run once**, **Always allow**, **Reject**

From Cursor chat, say the same phrase — the agent updates `.cursor/skill-guard-overrides.json` or runs `python scripts/skill_guard_allow.py always --scan …`.

Non-interactive CI uses `SKILL_GUARD_NON_INTERACTIVE=1` (no prompts).

If the push does not touch `.cursor/skills/`, the hook exits immediately.

## Install (once per clone)

```bash
./scripts/install-git-hooks.sh
```

Windows (PowerShell):

```powershell
.\scripts\install-git-hooks.ps1
```

This sets `core.hooksPath` to `.githooks` for this repository only.

## Manual scan

```bash
python scripts/scan_agent_skills.py
python scripts/scan_agent_skills.py --git-range origin/main..HEAD
```

GitHub Actions also runs the same scanner on pull requests and pushes (see `.github/workflows/scan-agent-skills.yml`).
