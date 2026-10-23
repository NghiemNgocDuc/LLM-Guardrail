"""Check tracked files for common credential formats without printing values.

Intentional detection examples are allowed only for an exact, reviewed file
digest in secret-scan-allowlist.json. Any edit invalidates that approval.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = ROOT / "scripts" / "secret-scan-allowlist.json"
PATTERNS = {
    "groq_key": re.compile(r"\b" + "gsk" + r"_[A-Za-z0-9_-]{24,}\b"),
    "model_key": re.compile(r"\bsk" + r"-[A-Za-z0-9_-]{24,}\b"),
    "gateway_key": re.compile(r"\bgrg" + r"_[A-Za-z0-9_-]{32,}\b"),
    "stripe_key": re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{24,}\b"),
    "google_key": re.compile(r"\bAI" + r"za[A-Za-z0-9_-]{35}\b"),
    "github_key": re.compile(r"\b(?:gh" + r"p_[A-Za-z0-9]{30,}|github" + r"_pat_[A-Za-z0-9_]{30,})\b"),
    "slack_key": re.compile(r"\bxox" + r"[baprs]-[A-Za-z0-9-]{20,}\b"),
    "aws_key": re.compile(r"\bAK" + r"IA[0-9A-Z]{16}\b"),
    "private_key": re.compile(r"-----BEGIN (?:(?:RSA|OPENSSH|EC|DSA|ENCRYPTED) )?PRIVATE KEY-----"),
    "secret_assignment": re.compile(
        r"(?m)^[ \t]*(?:export[ \t]+)?(?:SECRET_KEY|GROQ_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY|POSTGRES_PASSWORD)"
        r"[ \t]*=[ \t]*[\"']?[^\s\"'#<>]{16,}"
    ),
    "database_password": re.compile(r"postgresql(?:\+asyncpg)?://[^\s:/<>${}]+:[^\s@<>${}]{8,}@"),
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str


def content_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def scan_content(path: str, content: str, allowlist: dict[str, str]) -> list[Finding]:
    if allowlist.get(path) == content_digest(content):
        return []
    return [
        Finding(path, content.count("\n", 0, match.start()) + 1, rule)
        for rule, pattern in PATTERNS.items()
        for match in pattern.finditer(content)
    ]


def main() -> int:
    approved = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8").split("\0")
    findings = []
    for name in filter(None, tracked):
        path = ROOT / name
        if path.is_symlink():
            raise ValueError(f"Cannot verify symlink: {name}")
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(scan_content(name, content, approved))
    for finding in findings:
        print(f"{finding.path}:{finding.line}: potential secret ({finding.rule}); value withheld")
    if findings:
        print("Remove credentials. Re-review intentional examples before updating their allowlist digest.")
        return 1
    print("No unapproved credential patterns in tracked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
