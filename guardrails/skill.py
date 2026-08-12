"""
Agent skill / instruction guardrails — detect sensitive data and destructive commands
before they reach an agent context.

Use for Cursor skills, system prompts, MCP instructions, and other long-lived agent context
that should not contain credentials, PII, internal infrastructure details, or runnable
commands that can damage the host system.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from guardrails import _engine
from guardrails.dangerous_commands import DANGEROUS_COMMAND_PATTERNS

_DEFAULT_INPUT_POLICY = {
    "block_secrets": True,
    "block_pii": True,
    "pii_patterns": [
        {"name": "credit_card", "regex": r"\b(?:\d[ -]?){13,16}\b"},
        {"name": "ssn", "regex": r"\b\d{3}-\d{2}-\d{4}\b"},
        {"name": "email", "regex": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"},
    ],
    "block_prompt_injection": False,
    "block_jailbreak": False,
}

_SKILL_PATTERNS: list[tuple[str, str, str, float]] = [
    ("gateway_api_key", "Gateway API key", r"\bgrg_[A-Za-z0-9_-]{20,}\b", 0.95),
    (
        "database_url",
        "Database connection URL",
        r"\b(?:postgres(?:ql)?|mysql|mongodb|redis)(?:\+[a-z0-9]+)?://[^\s\"']+",
        0.92,
    ),
    (
        "credential_assignment",
        "Hard-coded credential",
        r"(?i)(?:api[_-]?key|secret|password|token|auth)\s*[:=]\s*['\"]?[^\s'\"#,]{8,}",
        0.88,
    ),
    ("bearer_token", "Bearer token", r"(?i)Bearer\s+[A-Za-z0-9._\-]{20,}", 0.9),
    ("env_assignment", ".env-style secret", r"(?im)^(?:[A-Z][A-Z0-9_]*)\s*=\s*[^\s#]+", 0.75),
    (
        "private_ip",
        "Private network address",
        r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b",
        0.55,
    ),
    (
        "internal_path",
        "Internal filesystem path",
        r"(?:/[a-z0-9._-]+){2,}(?:\.ssh|/etc/|/var/|/home/)|(?:[A-Z]:\\Users\\)",
        0.5,
    ),
]

_SECRET_LINE_PATTERNS = {
    # Prefixes are split to avoid triggering CI secret scanners on pattern strings.
    "groq_api_key": r"\b" "gsk" r"_[A-Za-z0-9_-]{20,}\b",
    "openai_api_key": r"\b" "sk" r"-[A-Za-z0-9_-]{20,}\b",
    "github_token": r"\b(?:" "ghp" r"_|" "github" r"_pat_)[A-Za-z0-9_]{20,}\b",
    "aws_access_key": r"\b" "AKIA" r"[0-9A-Z]{16}\b",
    "private_key": r"-----BEGIN (?:RSA|OPENSSH|EC|DSA|PRIVATE) KEY-----",
}

_SNIPPET_MAX = 72


@dataclass
class SkillFinding:
    category: str
    severity: str
    check: str
    reason: str
    reason_code: str
    line_number: int | None = None
    snippet: str = ""
    risk_score: float = 0.0


@dataclass
class SkillScanResult:
    safe: bool
    risk_score: float
    findings: list[SkillFinding] = field(default_factory=list)
    line_count: int = 0
    char_count: int = 0


def _redact_snippet(text: str) -> str:
    s = " ".join(text.strip().split())
    if len(s) <= _SNIPPET_MAX:
        return s
    return s[: _SNIPPET_MAX - 3] + "..."


def _severity(score: float) -> str:
    if score >= 0.9:
        return "critical"
    if score >= 0.75:
        return "high"
    return "medium"


class SkillGuardrail:
    def scan(self, content: str) -> SkillScanResult:
        if _engine.enabled():
            try:
                data = _engine.module().scan_skill(content)
                if data is None:
                    return SkillScanResult(safe=True, risk_score=0.0, line_count=0, char_count=0)
                findings = [
                    SkillFinding(
                        category=f["category"],
                        severity=f["severity"],
                        check=f["check"],
                        reason=f["reason"],
                        reason_code=f["reason_code"],
                        line_number=f["line_number"],
                        snippet=f["snippet"],
                        risk_score=f["risk_score"],
                    )
                    for f in data["findings"]
                ]
                return SkillScanResult(
                    safe=len(findings) == 0,
                    risk_score=data["risk_score"],
                    findings=findings,
                    line_count=data["line_count"],
                    char_count=data["char_count"],
                )
            except Exception:
                pass  # fall through to the Python implementation
        if not content or not content.strip():
            return SkillScanResult(safe=True, risk_score=0.0, line_count=0, char_count=0)

        lines = content.splitlines()
        findings: list[SkillFinding] = []
        seen: set[tuple[str, int | None, str]] = set()

        def add(
            category: str,
            check: str,
            reason: str,
            reason_code: str,
            risk_score: float,
            line_number: int | None,
            snippet: str,
        ) -> None:
            key = (reason_code, line_number, snippet[:40])
            if key in seen:
                return
            seen.add(key)
            findings.append(
                SkillFinding(
                    category=category,
                    severity=_severity(risk_score),
                    check=check,
                    reason=reason,
                    reason_code=reason_code,
                    line_number=line_number,
                    snippet=_redact_snippet(snippet),
                    risk_score=risk_score,
                )
            )

        for line_no, line in enumerate(lines, start=1):
            for code, check_name, regex, score in DANGEROUS_COMMAND_PATTERNS:
                if re.search(regex, line):
                    add(
                        "destructive_command",
                        check_name,
                        f"{check_name} on line {line_no}",
                        code,
                        score,
                        line_no,
                        line,
                    )

            for code, check_name, regex, score in _SKILL_PATTERNS:
                if re.search(regex, line):
                    add(
                        "agent_context",
                        check_name,
                        f"{check_name} on line {line_no}",
                        code,
                        score,
                        line_no,
                        line,
                    )

            for code, regex in _SECRET_LINE_PATTERNS.items():
                if re.search(regex, line):
                    add(
                        "secret",
                        "Secret Detection",
                        f"Secret detected: {code} (line {line_no})",
                        "secret_detected",
                        0.95,
                        line_no,
                        line,
                    )

            for p in _DEFAULT_INPUT_POLICY.get("pii_patterns", []):
                if re.search(p["regex"], line):
                    add(
                        "pii",
                        "PII Detection",
                        f"PII detected: {p['name']} (line {line_no})",
                        "pii_detected",
                        0.85,
                        line_no,
                        line,
                    )

        risk = max((f.risk_score for f in findings), default=0.0)
        return SkillScanResult(
            safe=len(findings) == 0,
            risk_score=risk,
            findings=sorted(findings, key=lambda f: (-f.risk_score, f.line_number or 0)),
            line_count=len(lines),
            char_count=len(content),
        )
