"""Git push checks must scan the commits being published, not local edits."""
import io
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import scan_agent_skills as scanner


ZERO = "0" * 40
SAFE = "# Documentation\nSummarize public documentation.\n"
UNSAFE = "Credential: " + "g" + "sk_" + "Z" * 32 + "\n"


def git(root, *args):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=True)
    return result.stdout.decode("utf-8").strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Skill Gate Test")
    git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "README.md").write_text("Test fixture\n", encoding="utf-8")
    git(tmp_path, "add", "README.md")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def commit_skill(repo, content, *, filename="SKILL.md"):
    skill = repo / ".cursor" / "skills" / "sample" / filename
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(content, encoding="utf-8")
    git(repo, "add", "--", str(skill.relative_to(repo)))
    git(repo, "commit", "-qm", "skill version")
    return git(repo, "rev-parse", "HEAD"), skill


def pre_push(repo, monkeypatch, updates):
    monkeypatch.setattr(sys, "stdin", io.StringIO(updates))
    return scanner.main(["--root", str(repo), "--pre-push"])


def update(local, remote, ref="main"):
    return f"refs/heads/{ref} {local} refs/heads/{ref} {remote}\n"


def test_unsafe_commit_cannot_be_hidden_by_clean_working_tree(repo, monkeypatch, capsys):
    base = git(repo, "rev-parse", "HEAD")
    tip, skill = commit_skill(repo, UNSAFE)
    skill.write_text(SAFE, encoding="utf-8")
    assert pre_push(repo, monkeypatch, update(tip, base)) == 1
    output = capsys.readouterr().out
    assert "REJECTED" in output and tip[:12] in output
    assert UNSAFE.strip() not in output and "Z" * 32 not in output
    pause = (repo / scanner.PAUSE_FILE).read_text(encoding="utf-8")
    assert "Z" * 32 not in pause


def test_clean_commit_is_scanned_even_with_unsafe_working_tree(repo, monkeypatch, capsys):
    base = git(repo, "rev-parse", "HEAD")
    tip, skill = commit_skill(repo, SAFE)
    skill.write_text(UNSAFE, encoding="utf-8")
    assert pre_push(repo, monkeypatch, update(tip, base)) == 0
    assert "REJECTED" not in capsys.readouterr().out


def test_intermediate_unsafe_commit_is_blocked_after_a_clean_revert(repo, monkeypatch):
    base = git(repo, "rev-parse", "HEAD")
    commit_skill(repo, UNSAFE)
    tip, _ = commit_skill(repo, SAFE)
    assert pre_push(repo, monkeypatch, update(tip, base)) == 1


def test_git_range_also_reads_all_outgoing_committed_versions(repo, capsys):
    base = git(repo, "rev-parse", "HEAD")
    commit_skill(repo, UNSAFE)
    tip, skill = commit_skill(repo, SAFE)
    skill.write_text("Another clean local edit", encoding="utf-8")
    assert scanner.main(["--root", str(repo), "--git-range", f"{base}..{tip}"]) == 1
    assert "Z" * 32 not in capsys.readouterr().out


def test_new_branch_checks_its_reachable_committed_history(repo, monkeypatch):
    commit_skill(repo, UNSAFE)
    tip, skill = commit_skill(repo, SAFE)
    assert pre_push(repo, monkeypatch, update(tip, ZERO, "new-branch")) == 1


def test_deleted_ref_publishes_no_objects_and_does_not_scan_local_edits(repo, monkeypatch):
    remote, skill = commit_skill(repo, SAFE)
    skill.write_text(UNSAFE, encoding="utf-8")
    assert pre_push(repo, monkeypatch, update(ZERO, remote)) == 0


def test_multiple_updates_do_not_short_circuit_after_a_new_clean_ref(repo, monkeypatch):
    base = git(repo, "rev-parse", "HEAD")
    clean, _ = commit_skill(repo, SAFE)
    unsafe, _ = commit_skill(repo, UNSAFE)
    updates = update(clean, ZERO, "new-clean") + update(unsafe, clean, "unsafe")
    assert pre_push(repo, monkeypatch, updates) == 1


def test_repeated_blobs_across_commits_and_refs_are_scanned_once(repo, monkeypatch):
    base = git(repo, "rev-parse", "HEAD")
    tip, _ = commit_skill(repo, SAFE)
    (repo / "README.md").write_text("Updated unrelated doc\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-qm", "unrelated")
    final = git(repo, "rev-parse", "HEAD")
    scans = []
    canonical = scanner.SkillGuardrail.scan

    def track(self, content):
        scans.append(content)
        return canonical(self, content)

    monkeypatch.setattr(scanner.SkillGuardrail, "scan", track)
    assert pre_push(repo, monkeypatch, update(final, base, "a") + update(tip, ZERO, "b")) == 0
    assert scans == [SAFE]


@pytest.mark.parametrize("updates", ["malformed\n", update("1" * 40, ZERO), update("not-an-object", ZERO), update("1" * 40, "2" * 40)])
def test_malformed_or_missing_commits_fail_closed(repo, monkeypatch, updates, capsys):
    assert pre_push(repo, monkeypatch, updates) == 1
    assert "push blocked" in capsys.readouterr().out


@pytest.mark.parametrize("revision", ["missing-branch..HEAD", ""])
def test_git_range_resolution_failure_is_not_reported_as_no_changes(repo, capsys, revision):
    assert scanner.main(["--root", str(repo), "--git-range", revision]) == 1
    assert "push blocked" in capsys.readouterr().out


def test_git_execution_error_fails_closed(repo, monkeypatch, capsys):
    def unavailable(*args, **kwargs):
        raise OSError("example error text must not be echoed")

    monkeypatch.setattr(scanner.subprocess, "run", unavailable)
    assert scanner.main(["--root", str(repo), "--git-range", "HEAD"]) == 1
    output = capsys.readouterr().out
    assert "push blocked" in output
    assert "example error text" not in output


def test_unreadable_committed_markdown_fails_closed(repo, monkeypatch):
    base = git(repo, "rev-parse", "HEAD")
    skill = repo / ".cursor" / "skills" / "binary" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_bytes(b"\xff\xfe\x00")
    git(repo, "add", "--", str(skill.relative_to(repo)))
    git(repo, "commit", "-qm", "invalid text")
    assert pre_push(repo, monkeypatch, update(git(repo, "rev-parse", "HEAD"), base)) == 1


def test_committed_skill_symlink_fails_closed(repo, monkeypatch):
    base = git(repo, "rev-parse", "HEAD")
    oid = git(repo, "hash-object", "-w", "README.md")
    git(repo, "update-index", "--add", "--cacheinfo", f"120000,{oid},.cursor/skills/link/SKILL.md")
    git(repo, "commit", "-qm", "skill link")
    assert pre_push(repo, monkeypatch, update(git(repo, "rev-parse", "HEAD"), base)) == 1


def test_explicit_local_overrides_keep_existing_cli_behavior(repo, monkeypatch):
    base = git(repo, "rev-parse", "HEAD")
    tip, _ = commit_skill(repo, UNSAFE)
    findings = scanner.SkillGuardrail().scan(UNSAFE).findings
    overrides = scanner.SkillOverrides(set(), set(), set())
    for finding in findings:
        overrides.allow_always(finding)
    scanner._save_overrides(repo, overrides)
    assert pre_push(repo, monkeypatch, update(tip, base)) == 0


def test_workflow_annotation_cannot_inject_commands_from_filenames(capsys):
    scanner._github_annotation(Path(".cursor/skills/a%\n::warning::injected,property/SKILL.md"), 2, "Skill, Guard", "Reason\n::warning::injected")
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("::error file=")
    assert "%25%0A%3A%3Awarning%3A%3A" in lines[0]
    assert "title=Skill%2C Guard" in lines[0]
    assert "Reason%0A::warning::injected" in lines[0]


def test_secret_values_in_committed_filenames_are_redacted(repo, monkeypatch, capsys):
    base = git(repo, "rev-parse", "HEAD")
    filename = "g" + "sk_" + "Y" * 32 + ".md"
    tip, _ = commit_skill(repo, UNSAFE, filename=filename)
    monkeypatch.setattr(sys, "stdin", io.StringIO(update(tip, base)))
    assert scanner.main(["--root", str(repo), "--pre-push", "--github-actions"]) == 1
    output = capsys.readouterr().out
    assert "Y" * 32 not in output
    assert "Y" * 32 not in (repo / scanner.PAUSE_FILE).read_text(encoding="utf-8")
