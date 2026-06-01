#!/usr/bin/env python3
"""
Scan Cursor agent skill files for secrets, PII, destructive commands, and internal details.

Exit 0 when all files are clean; exit 1 when any finding is reported.

Use --pre-push as a git pre-push hook, or --git-range to scan only files in a revision range.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from guardrails.skill import SkillGuardrail  # noqa: E402
from guardrails.skill_messages import explain_finding  # noqa: E402
from guardrails.skill_overrides import SkillOverrides, apply_overrides, finding_key  # noqa: E402

OVERRIDES_FILENAME = ".cursor/skill-guard-overrides.json"

DEFAULT_GLOBS = (
    ".cursor/skills/**/SKILL.md",
    ".cursor/skills/**/*.md",
    ".cursor/skills/**/skill.md",
)

_SEVERITY_RANK = {"medium": 1, "high": 2, "critical": 3}


def _collect_files(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file() and path not in seen:
                seen.add(path)
                files.append(path)
    return sorted(files)


def _git_diff_skill_files(root: Path, rev_range: str) -> list[Path]:
    proc = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            rev_range,
            "--",
            ".cursor/skills/",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    files: list[Path] = []
    for line in proc.stdout.splitlines():
        rel = line.strip()
        if not rel:
            continue
        path = (root / rel).resolve()
        if path.is_file():
            files.append(path)
    return sorted(set(files))


def _collect_files_for_pre_push(root: Path) -> list[Path] | None:
    """
    Read git pre-push hook stdin. Return file list to scan, or None if no skill paths changed.
    """
    if sys.stdin.isatty():
        return _collect_files(root, DEFAULT_GLOBS)

    lines = [ln for ln in sys.stdin.read().splitlines() if ln.strip()]
    if not lines:
        return _collect_files(root, DEFAULT_GLOBS)

    to_scan: set[Path] = set()
    for line in lines:
        parts = line.split()
        if len(parts) < 4:
            continue
        local_sha = parts[1]
        remote_sha = parts[3]
        if set(remote_sha) == {"0"}:
            return _collect_files(root, DEFAULT_GLOBS)
        to_scan.update(_git_diff_skill_files(root, f"{remote_sha}..{local_sha}"))

    if not to_scan:
        return None
    return sorted(to_scan)


def _overrides_path(root: Path) -> Path:
    return root / OVERRIDES_FILENAME


def _load_overrides(root: Path) -> SkillOverrides:
    path = _overrides_path(root)
    if not path.is_file():
        return SkillOverrides(set(), set(), set())
    try:
        return SkillOverrides.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return SkillOverrides(set(), set(), set())


def _save_overrides(root: Path, overrides: SkillOverrides) -> None:
    path = _overrides_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overrides.to_dict(), indent=2) + "\n", encoding="utf-8")


def _print_rejection(finding, *, github_actions: bool, path: Path | None) -> None:
    loc = f"line {finding.line_number}" if finding.line_number else "file"
    print(f"  [{finding.severity}] {finding.check} ({loc})")
    print(f"  Why: {explain_finding(finding.reason_code, finding.check)}")
    print(f"  Snippet: {finding.snippet}")
    if github_actions and path:
        _github_annotation(
            path,
            finding.line_number,
            "Skill Guard",
            explain_finding(finding.reason_code, finding.check),
        )


def _parse_batch_command(raw: str) -> str | None:
    cmd = raw.strip().lower().replace("  ", " ")
    if cmd in (
        "always allow",
        "always allow all",
        "allow all",
        "allow always",
        "a",
        "aa",
    ):
        return "always_all"
    if cmd in ("run once", "run once all", "allow once", "ro"):
        return "run_once_all"
    return None


def _interactive_resolve(
    root: Path,
    blocking: list,
    overrides: SkillOverrides,
) -> SkillOverrides:
    if os.environ.get("SKILL_GUARD_NON_INTERACTIVE") == "1":
        return overrides

    print(f"\nSkill Guard: {len(blocking)} issue(s) blocking.")
    print('  Quick (chat-style): type "always allow" or "always allow all" once — no per-issue prompts.')
    print("  Or press Enter to choose per issue: [R] run once  [A] always allow  [E] reject\n")

    batch = input('Command ("always allow all" / Enter): ').strip()
    action = _parse_batch_command(batch)
    if action == "always_all":
        for finding in blocking:
            overrides.allow_always(finding)
        _save_overrides(root, overrides)
        print(f"  → Always allowed all {len(blocking)} issue(s); saved to {_overrides_path(root)}.\n")
        return overrides
    if action == "run_once_all":
        for finding in blocking:
            overrides.allow_once(finding)
        print(f"  → Run once: allowed all {len(blocking)} issue(s) for this run only.\n")
        return overrides

    for idx, finding in enumerate(blocking, start=1):
        print(f"--- Issue {idx}/{len(blocking)} ({finding_key(finding)}) ---")
        _print_rejection(finding, github_actions=False, path=None)
        while True:
            choice = input("Choice [R/A/E] or phrase: ").strip().lower()
            batch_choice = _parse_batch_command(choice)
            if batch_choice == "always_all":
                overrides.allow_always(finding)
                _save_overrides(root, overrides)
                print(f"  → Always allowed; saved to {_overrides_path(root)}.\n")
                break
            if batch_choice == "run_once_all":
                overrides.allow_once(finding)
                print("  → Allowed for this run only.\n")
                break
            if choice in ("r", "run", "run once", "1"):
                overrides.allow_once(finding)
                print("  → Allowed for this run only.\n")
                break
            if choice in ("a", "always", "always allow", "2"):
                overrides.allow_always(finding)
                _save_overrides(root, overrides)
                print(f"  → Always allowed; saved to {_overrides_path(root)}.\n")
                break
            if choice in ("e", "reject", "3"):
                print("  → Rejected; agent remains blocked for this issue.\n")
                break
            print("  Enter R, A, or E.")

    return overrides


def _scan_files(
    root: Path,
    files: list[Path],
    min_rank: int,
    github_actions: bool,
    interactive: bool,
) -> int:
    if not files:
        print("Skill Guard: no files matched .cursor/skills/** — nothing to scan.")
        return 0

    guard = SkillGuardrail()
    overrides = _load_overrides(root)
    any_blocking = False

    for path in files:
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                display = path.relative_to(root)
            except ValueError:
                display = path
            print(f"Skill Guard: skip binary or non-UTF-8 file: {display}")
            continue

        result = guard.scan(content)
        decision = apply_overrides(result, overrides)
        blocking = [
            f
            for f in decision.blocking
            if _SEVERITY_RANK.get(f.severity, 0) >= min_rank
        ]

        try:
            display = path.relative_to(root)
        except ValueError:
            display = path

        if interactive and blocking and sys.stdin.isatty():
            overrides = _interactive_resolve(root, blocking, overrides)
            decision = apply_overrides(result, overrides)
            blocking = [
                f
                for f in decision.blocking
                if _SEVERITY_RANK.get(f.severity, 0) >= min_rank
            ]

        if not blocking:
            note = ""
            if decision.allowed:
                note = f" ({len(decision.allowed)} overridden)"
            print(f"OK  {display} ({result.line_count} lines, risk {result.risk_score:.0%}){note}")
            continue

        any_blocking = True
        print(f"\nREJECTED {display} — agent blocked ({len(blocking)} issue(s))")
        if decision.rejection_summary:
            print(decision.rejection_summary)
        for f in blocking:
            _print_rejection(f, github_actions=github_actions, path=path)

    if any_blocking:
        if interactive and sys.stdin.isatty():
            print("\nSkill Guard: push blocked. Fix the skill or re-run and choose Run once / Always allow.")
        else:
            print(
                "\nSkill Guard: push blocked. Fix findings, or run locally with "
                "`python scripts/scan_agent_skills.py --interactive` to override."
            )
        return 1

    print(f"\nSkill Guard: {len(files)} file(s) passed — agent may continue.")
    return 0


def _github_annotation(path: Path, line: int | None, title: str, message: str) -> None:
    rel = path.as_posix()
    if line:
        print(f"::error file={rel},line={line},title={title}::{message}")
    else:
        print(f"::error file={rel},title={title}::{message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan .cursor/skills for agent context leaks.")
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (default: parent of scripts/)",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Explicit files to scan (default: glob under .cursor/skills/)",
    )
    parser.add_argument(
        "--min-severity",
        choices=("medium", "high", "critical"),
        default="medium",
        help="Minimum severity that fails the run (default: medium)",
    )
    parser.add_argument(
        "--github-actions",
        action="store_true",
        help="Emit workflow commands for GitHub Actions annotations",
    )
    parser.add_argument(
        "--pre-push",
        action="store_true",
        help="Git pre-push mode: scan .cursor/skills files in outgoing commits (read refs from stdin)",
    )
    parser.add_argument(
        "--git-range",
        metavar="REV",
        help="Only scan skill files changed in a git revision range (e.g. origin/main..HEAD)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for Run once / Always allow / Reject on each blocking finding (TTY only)",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    min_rank = _SEVERITY_RANK[args.min_severity]

    if args.pre_push:
        files = _collect_files_for_pre_push(root)
        if files is None:
            print("Skill Guard: no .cursor/skills/ changes in this push — OK.")
            return 0
    elif args.git_range:
        files = _git_diff_skill_files(root, args.git_range)
        if not files:
            print(f"Skill Guard: no skill files in git range {args.git_range!r}.")
            return 0
    elif args.paths:
        files = [p.resolve() for p in args.paths if p.is_file()]
    else:
        files = _collect_files(root, DEFAULT_GLOBS)

    interactive = args.interactive or (args.pre_push and sys.stdin.isatty())
    return _scan_files(root, files, min_rank, args.github_actions, interactive)


if __name__ == "__main__":
    raise SystemExit(main())
