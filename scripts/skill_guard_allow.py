#!/usr/bin/env python3
"""
Apply Skill Guard overrides from Cursor chat or CLI (no web UI clicks).

Examples:
  python scripts/skill_guard_allow.py always --scan .cursor/skills/my-skill/SKILL.md
  python scripts/skill_guard_allow.py always --reason database_url --reason drop_sql
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from guardrails.skill import SkillGuardrail  # noqa: E402
from guardrails.skill_overrides import SkillOverrides, apply_overrides  # noqa: E402

OVERRIDES_FILENAME = ".cursor/skill-guard-overrides.json"


def _overrides_path(root: Path) -> Path:
    return root / OVERRIDES_FILENAME


def _load_overrides(root: Path) -> SkillOverrides:
    path = _overrides_path(root)
    if not path.is_file():
        return SkillOverrides(set(), set(), set())
    return SkillOverrides.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _save_overrides(root: Path, overrides: SkillOverrides) -> None:
    path = _overrides_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overrides.to_dict(), indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Allow Skill Guard rules from chat/CLI.")
    parser.add_argument(
        "mode",
        choices=("always", "run-once"),
        help="always = persist to .cursor/skill-guard-overrides.json; run-once = not persisted",
    )
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Repository root")
    parser.add_argument(
        "--scan",
        type=Path,
        action="append",
        default=[],
        help="Scan file(s) and allow all current blocking findings",
    )
    parser.add_argument(
        "--reason",
        dest="reasons",
        action="append",
        default=[],
        metavar="CODE",
        help="Always allow this reason_code (e.g. database_url) without scanning",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    overrides = _load_overrides(root)
    guard = SkillGuardrail()
    applied = 0

    if args.scan:
        for path in args.scan:
            p = path if path.is_absolute() else root / path
            if not p.is_file():
                print(f"skill_guard_allow: file not found: {p}", file=sys.stderr)
                return 1
            result = guard.scan(p.read_text(encoding="utf-8"))
            decision = apply_overrides(result, overrides)
            for finding in decision.blocking:
                if args.mode == "always":
                    overrides.allow_always(finding)
                else:
                    overrides.allow_once(finding)
                applied += 1
                print(f"  allowed {finding.reason_code} ({finding.check})")

    for code in args.reasons:
        overrides.always_allow_reason_codes.add(code)
        applied += 1
        print(f"  allowed reason_code {code}")

    if applied == 0:
        print("skill_guard_allow: nothing to allow (use --scan and/or --reason)", file=sys.stderr)
        return 1

    if args.mode == "always":
        _save_overrides(root, overrides)
        print(f"Saved {applied} rule(s) to {_overrides_path(root)}")
    else:
        print(f"Run-once: allowed {applied} finding(s) (not written to disk — re-run scan in same process only)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
