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
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from guardrails.skill import SkillGuardrail  # noqa: E402
from app.utils.secret_redaction import scrub_text  # noqa: E402
from guardrails.skill_messages import explain_finding  # noqa: E402
from guardrails.skill_agent_packet import finding_to_dict, format_chat_control_prompt  # noqa: E402
from guardrails.skill_overrides import SkillOverrides, apply_overrides, finding_key  # noqa: E402

PAUSE_FILE = ".cursor/skill-guard-pause.json"

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


class GitScanError(RuntimeError):
    """The published skill contents could not be verified."""


def _git(root: Path, *arguments: str) -> bytes:
    try:
        proc = subprocess.run(["git", *arguments], cwd=root, capture_output=True, check=False)
    except OSError as exc:
        raise GitScanError("Git could not be run; push contents were not verified.") from exc
    if proc.returncode != 0:
        # Git stderr can include arbitrary ref/path text. Do not echo it.
        raise GitScanError("Git could not resolve or read outgoing commits. Fetch the remote history and retry.")
    return proc.stdout


def _git_committed_skill_documents(root: Path, revisions: list[str]) -> list[tuple[Path, str, str]]:
    """Read committed blobs, including intermediate outgoing versions.

    Checking each commit tree also catches skill content inherited by an
    outgoing commit. Identical blobs are scanned once across all pushed refs.
    """
    commits: list[str] = []
    seen_commits: set[str] = set()
    for revision in revisions:
        raw = _git(root, "rev-list", "--reverse", "--end-of-options", revision, "--")
        for commit in raw.decode("ascii").splitlines():
            if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
                raise GitScanError("Git returned an invalid commit identifier.")
            if commit not in seen_commits:
                seen_commits.add(commit)
                commits.append(commit)

    documents: list[tuple[Path, str, str]] = []
    seen_blobs: set[str] = set()
    for commit in commits:
        tree = _git(root, "ls-tree", "-r", "-z", commit, "--", ".cursor/skills/")
        for entry in tree.split(b"\0"):
            if not entry:
                continue
            try:
                metadata, raw_path = entry.split(b"\t", 1)
                mode, kind, raw_oid = metadata.decode("ascii").split()
                relative = raw_path.decode("utf-8")
                oid = raw_oid
            except (ValueError, UnicodeDecodeError) as exc:
                raise GitScanError("Git returned an unreadable skill tree entry.") from exc
            if not relative.startswith(".cursor/skills/") or not relative.lower().endswith(".md"):
                continue
            if kind != "blob" or mode not in {"100644", "100755"}:
                raise GitScanError("A committed Markdown skill is a link or unsupported file type; its content cannot be verified.")
            if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", oid):
                raise GitScanError("Git returned an invalid blob identifier.")
            if oid in seen_blobs:
                continue
            seen_blobs.add(oid)
            try:
                content = _git(root, "cat-file", "blob", oid).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise GitScanError("A committed Markdown skill is not UTF-8; its content cannot be verified.") from exc
            documents.append((root / relative, content, commit[:12]))
    return documents


def _git_range_skill_documents(root: Path, rev_range: str) -> list[tuple[Path, str, str]]:
    return _git_committed_skill_documents(root, [rev_range])


def _collect_documents_for_pre_push(root: Path) -> list[tuple[Path, str, str]]:
    """Read Git's pre-push refs; never substitute working-tree contents."""
    if sys.stdin.isatty():
        raise GitScanError("Pre-push mode requires Git's ref updates on stdin. Use paths for a working-tree scan.")
    revisions: list[str] = []
    for line in sys.stdin.read().splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 4:
            raise GitScanError("Malformed pre-push ref update; push contents were not verified.")
        local_sha, remote_sha = parts[1].lower(), parts[3].lower()
        if any(not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha) for sha in (local_sha, remote_sha)):
            raise GitScanError("Invalid pre-push commit identifier; push contents were not verified.")
        if set(local_sha) == {"0"}:
            continue  # A deleted remote ref publishes no local objects.
        # Resolve the tip as a commit even when rev-list would otherwise be empty.
        _git(root, "rev-parse", "--verify", f"{local_sha}^{{commit}}")
        if set(remote_sha) == {"0"}:
            revisions.append(local_sha)  # New branch: inspect all reachable history.
        else:
            _git(root, "rev-parse", "--verify", f"{remote_sha}^{{commit}}")
            revisions.append(f"{remote_sha}..{local_sha}")
    return _git_committed_skill_documents(root, revisions)


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


def _write_chat_pause(root: Path, entries: list[tuple[str, object]]) -> None:
    """Write pause state so the Cursor chat control layer can take over."""
    findings = [finding_to_dict(f) for _, f in entries]
    sources = sorted({src for src, _ in entries})
    source = ", ".join(sources[:3])
    if len(sources) > 3:
        source += f" (+{len(sources) - 3} more)"
    payload = {
        "agent_status": "paused",
        "control_layer": "cursor_chat",
        "source": source,
        "blocking_count": len(findings),
        "findings": findings,
        "chat_prompt": format_chat_control_prompt(findings, source=source),
    }
    path = root / PAUSE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("\n" + payload["chat_prompt"])
    print(f"\n↳ Wrote {path} — user must reply in **Cursor chat** (not the web dashboard).\n")


def _scan_files(
    root: Path,
    files: list[Path],
    min_rank: int,
    github_actions: bool,
    interactive: bool,
) -> int:
    documents: list[tuple[Path, str, str | None]] = []
    for path in files:
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                display = path.relative_to(root)
            except ValueError:
                display = path
            print(f"Skill Guard: skip binary or non-UTF-8 file: {scrub_text(str(display))}")
            continue
        documents.append((path, content, None))
    return _scan_documents(root, documents, min_rank, github_actions, interactive)


def _scan_documents(
    root: Path,
    documents: list[tuple[Path, str, str | None]],
    min_rank: int,
    github_actions: bool,
    interactive: bool,
) -> int:
    if not documents:
        print("Skill Guard: no files matched .cursor/skills/** — nothing to scan.")
        return 0

    guard = SkillGuardrail()
    overrides = _load_overrides(root)
    any_blocking = False
    pause_entries: list[tuple[str, object]] = []

    for path, content, revision in documents:
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
        if revision:
            display = f"{display} @ {revision}"
        display = scrub_text(str(display))

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
        for f in blocking:
            pause_entries.append((str(display), f))
        print(f"\nREJECTED {display} — agent blocked ({len(blocking)} issue(s))")
        if decision.rejection_summary:
            print(decision.rejection_summary)
        for f in blocking:
            _print_rejection(f, github_actions=github_actions, path=path)

    if any_blocking:
        _write_chat_pause(root, pause_entries)
        if interactive and sys.stdin.isatty():
            print("\nSkill Guard: push blocked. Fix the skill or re-run and choose Run once / Always allow.")
        else:
            print(
                "\nSkill Guard: push blocked. Review in dashboard → Rejected access, "
                "or report: python scripts/report_skill_rejection.py --scan <file> "
                "(with SKILL_GUARD_API_URL + SKILL_GUARD_ACCESS_TOKEN)."
            )
        return 1

    print(f"\nSkill Guard: {len(documents)} skill document(s) passed — agent may continue.")
    return 0


def _github_annotation(path: Path, line: int | None, title: str, message: str) -> None:
    def escape(value: str, *, property: bool = False) -> str:
        value = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        return value.replace(":", "%3A").replace(",", "%2C") if property else value

    rel = escape(scrub_text(path.as_posix()), property=True)
    title = escape(title, property=True)
    message = escape(message)
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
        help="Scan committed skill blobs throughout a git revision range (e.g. origin/main..HEAD)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for Run once / Always allow / Reject on each blocking finding (TTY only)",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    min_rank = _SEVERITY_RANK[args.min_severity]

    if args.pre_push or args.git_range is not None:
        if args.pre_push and args.git_range is not None:
            parser.error("Choose either --pre-push or --git-range.")
        try:
            documents = _collect_documents_for_pre_push(root) if args.pre_push else _git_range_skill_documents(root, args.git_range)
        except GitScanError as exc:
            print(f"Skill Guard: push blocked. {exc}")
            return 1
        return _scan_documents(root, documents, min_rank, args.github_actions, args.interactive and sys.stdin.isatty())
    if args.paths:
        files = [p.resolve() for p in args.paths if p.is_file()]
    else:
        files = _collect_files(root, DEFAULT_GLOBS)

    interactive = args.interactive or (args.pre_push and sys.stdin.isatty())
    return _scan_files(root, files, min_rank, args.github_actions, interactive)


if __name__ == "__main__":
    raise SystemExit(main())
