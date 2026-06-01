#!/usr/bin/env python3
"""Write Skill Guard user decision for the Cursor agent to read (resume after pause)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from guardrails.skill_agent_packet import build_agent_packet, format_packet_for_chat  # noqa: E402

DECISION_FILE = ".cursor/skill-guard-decision.json"
PAUSE_FILE = ".cursor/skill-guard-pause.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record Skill Guard pause decision for the agent.")
    parser.add_argument("action", choices=("run_once", "always_allow", "reject"))
    parser.add_argument("--reason", dest="reasons", action="append", default=[], metavar="CODE")
    parser.add_argument("--finding-key", dest="keys", action="append", default=[])
    parser.add_argument("--scope", default="all")
    parser.add_argument("--message", default="", help="Optional note for the agent")
    parser.add_argument("--filename", default=None)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--print-chat", action="store_true", help="Print markdown for Cursor chat")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    findings = []
    for key in args.keys:
        code = key.split(":")[0] if ":" in key else key
        findings.append({"finding_key": key, "reason_code": code, "line_number": 0})
    for code in args.reasons:
        findings.append({"finding_key": f"{code}:0", "reason_code": code, "line_number": 0})

    packet = build_agent_packet(
        args.action,
        findings=findings,
        scope=args.scope,
        user_message=args.message,
        filename=args.filename,
    )

    out = root / DECISION_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")

    pause = root / PAUSE_FILE
    if pause.is_file():
        pause.unlink()

    print(f"Wrote {out}")
    if args.print_chat:
        print()
        print(format_packet_for_chat(packet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
