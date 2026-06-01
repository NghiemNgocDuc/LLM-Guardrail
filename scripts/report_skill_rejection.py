#!/usr/bin/env python3
"""
Report a Skill Guard rejection to the dashboard (requires login token).

  export SKILL_GUARD_API_URL=https://your-app.onrender.com
  export SKILL_GUARD_ACCESS_TOKEN=<jwt access token from browser localStorage>

  python scripts/report_skill_rejection.py --scan .cursor/skills/my-skill/SKILL.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from guardrails.skill import SkillGuardrail  # noqa: E402
from guardrails.skill_overrides import apply_overrides, finding_key  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", type=Path, required=True, help="Skill file to scan and report if blocked")
    parser.add_argument("--source", default="git_push")
    args = parser.parse_args(argv)

    base = os.environ.get("SKILL_GUARD_API_URL", "").rstrip("/")
    token = os.environ.get("SKILL_GUARD_ACCESS_TOKEN", "")
    if not base or not token:
        print("Set SKILL_GUARD_API_URL and SKILL_GUARD_ACCESS_TOKEN", file=sys.stderr)
        return 1

    path = args.scan.resolve()
    content = path.read_text(encoding="utf-8")
    result = SkillGuardrail().scan(content)
    from guardrails.skill_overrides import SkillOverrides

    decision = apply_overrides(result, SkillOverrides(set(), set(), set()))
    if not decision.blocking:
        print("No blocking findings — nothing to report.")
        return 0

    findings = [
        {
            "finding_key": finding_key(f),
            "category": f.category,
            "severity": f.severity,
            "check": f.check,
            "reason": f.reason or "",
            "reason_code": f.reason_code,
            "explanation": f.reason or "",
            "line_number": f.line_number,
            "snippet": f.snippet,
            "risk_score": f.risk_score,
        }
        for f in decision.blocking
    ]

    import httpx

    r = httpx.post(
        f"{base}/skills/rejections/report",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "filename": path.name,
            "source": args.source,
            "rejection_summary": decision.rejection_summary,
            "content_preview": content[:500],
            "findings": findings,
        },
        timeout=30,
    )
    if r.status_code >= 400:
        print(r.text, file=sys.stderr)
        return 1
    print("Reported to dashboard:", r.json().get("id"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
