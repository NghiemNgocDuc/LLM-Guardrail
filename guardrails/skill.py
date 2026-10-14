"""
Agent skill / instruction guardrails — detect sensitive data and destructive commands
before they reach an agent context.

Use for Cursor skills, system prompts, MCP instructions, and other long-lived agent context
that should not contain credentials, PII, internal infrastructure details, or runnable
commands that can damage the host system.
"""
from __future__ import annotations

import re
import math
from dataclasses import dataclass, field

from guardrails import _engine
from guardrails.dangerous_commands import DANGEROUS_COMMAND_PATTERNS
from app.utils.secret_redaction import _configured_secrets, contains_secret, scrub_text

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
    "private_key": r"-----BEGIN (?:(?:(?:RSA|OPENSSH|EC|DSA|ENCRYPTED) )?PRIVATE KEY|PGP PRIVATE KEY BLOCK)-----",
    # JSON generic api_key / password (wl2 dataset uses random high-entropy values)
    "json_api_key": r'(?i)["\']?api[_-]?key["\']?\s*[:=]\s*["\']?[A-Za-z0-9_\-\.\/\+=]{16,}["\']?',
    "json_password": r'(?i)["\']?password["\']?\s*[:=]\s*["\'][^"\']{8,}["\']',
}

_SNIPPET_MAX = 72
_NEGATION_RE = re.compile(r"(?i)\b(?:never|do\s+not|don't|dont|must\s+not|should\s+not|avoid|forbid|prohibit)\b")
_CLAUSE_BOUNDARY_RE = re.compile(r"(?<=[;.!?])\s+|\b(?:but|however|instead|then|nevertheless)\b", re.I)
_REFERENCE_VALUE_RE = re.compile(
    r"(?:\$\{[A-Z_][A-Z0-9_]*\}|\$[A-Z_][A-Z0-9_]*|\$env:[A-Z_][A-Z0-9_]*|"
    r"(?:os\.(?:getenv|environ\.get)|getenv)\(\s*['\"][A-Z_][A-Z0-9_]*['\"]\s*(?:,\s*(?:None|null|undefined|['\"]{2})\s*)?\)|"
    r"(?:os\.environ|process\.env)\[\s*['\"][A-Z_][A-Z0-9_]*['\"]\s*\]|"
    r"(?:process\.env|settings|config|import\.meta\.env)\.[A-Z_][A-Z0-9_]*)"
)
_SENSITIVE_ENV_RE = re.compile(r"(?:^|_)(?:API_KEY|KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIALS?|AUTH|DSN)(?:_|$)|(?:DATABASE|REDIS)_URL$", re.I)
_DISCLOSURE_PATTERNS = [
    re.compile(r"(?i)\b(?:share|expose|reveal|leak|print|echo|dump|include|send|output)\s+[^\n;.!?]{0,40}?\b(?:api[\s_-]*keys?|secrets?|credentials?|tokens?|env(?:ironment)?|passwords?|(?:GROQ|OPENAI|ANTHROPIC|GEMINI)_API_KEY)\b"),
    re.compile(r"(?i)\b(?:print|echo|dump|cat|show|reveal|expose)\b[^\n;!?]{0,100}(?:\.env\b|\benviron\b|os\.environ|process\.env)"),
    re.compile(r"(?i)\b(?:what\s+is|show\s+me)\b[^\n;!?]{0,100}\b(?:api[_\s-]*key|secret|password|token|env|(?:groq|openai|anthropic|gemini)[_\s-]*(?:api[_\s-]*)?key)\b|\b(?:print|console\.log|console\.info|echo|dump)\s*\([^\n;!?]{0,100}(?:os\.(?:environ|getenv)|process\.env|(?:GROQ|OPENAI|ANTHROPIC|GEMINI)_API_KEY)"),
]


def unsafe_disclosure_instructions(content: str) -> list[tuple[int, str]]:
    """Find disclosure actions, excluding local prohibitions and token metrics."""
    found: list[tuple[int, str]] = []
    if not re.search(r"(?i)\b(?:share|expose|reveal|leak|print|echo|dump|include|send|output|cat|show|what|console)\b", content):
        return found
    for number, line in enumerate(content.splitlines(), 1):
        for clause in _CLAUSE_BOUNDARY_RE.split(line):
            for pattern in _DISCLOSURE_PATTERNS:
                for match in pattern.finditer(clause):
                    suffix = clause[match.end():]
                    token_metric = re.search(r"(?i)\btokens?$", match.group(0)) and re.match(r"(?i)\s+(?:usage|counts?|budget|balance|limits?|statistics|throughput)\b", suffix)
                    if not token_metric and not is_prohibited_instruction(clause, match.start()):
                        found.append((number, match.group(0)))
    return found


def is_prohibited_instruction(text: str, start: int) -> bool:
    """Recognize local prohibitions; another sentence's 'never' is irrelevant."""
    prefix = text[max(0, start - 240):start]
    prefix = _CLAUSE_BOUNDARY_RE.split(prefix)[-1]
    matches = list(_NEGATION_RE.finditer(prefix))
    if not matches:
        return False
    tail = prefix[matches[-1].end():].strip(" \t:`*\"'")
    words = r"(?:ever|always|actually|automatically|intentionally|explicitly|silently|run|execute|invoke|use|print|show|disclose|share|expose|reveal|dump|collect|store|include|echo|allow|leak|send|output|the|following|command|commands|sudo)"
    if not tail or re.fullmatch(rf"(?i)(?:{words}\s*){{1,6}}", tail):
        return True
    # One prohibition can govern coordinated verbs: 'never share keys or expose secrets'.
    return bool(re.match(rf"(?i){words}\b", tail) and re.search(r"(?i)\b(?:and|or)(?:\s+also)?$", tail))


def _reference_assignment(line: str, match: re.Match) -> bool:
    delimiter = re.search(r"[:=]", match.group(0))
    if delimiter is None:
        return False
    rhs = line[match.start() + delimiter.end():].lstrip()
    if rhs[:1] in {"'", '"'}:
        quote = rhs[0]
        end = rhs.find(quote, 1)
        return end >= 0 and _REFERENCE_VALUE_RE.fullmatch(rhs[1:end]) is not None
    reference = _REFERENCE_VALUE_RE.match(rhs)
    return bool(reference and (reference.end() == len(rhs) or rhs[reference.end()] in " \t;,#)"))


def _actionable_match(code: str, line: str, match: re.Match) -> bool:
    if code in {"credential_assignment", "env_assignment", "json_api_key", "json_password"}:
        if code == "env_assignment":
            name = match.group(0).split("=", 1)[0].strip()
            if not _SENSITIVE_ENV_RE.search(name) or name.upper().split("_")[-1] in {"COUNT", "COUNTS", "LIMIT", "LIMITS", "BUDGET", "MODE", "METHOD", "ENABLED", "DISABLED", "NAME", "NAMES", "FLAG", "PATTERN", "RULE", "TYPE", "FORMAT"}:
                return False
        return not _reference_assignment(line, match)
    return True


def redact_skill_excerpt(text: str, max_length: int = _SNIPPET_MAX) -> str:
    """Remove sensitive values before shortening diagnostic evidence."""
    redacted = scrub_text(text)
    for regex in _SECRET_LINE_PATTERNS.values():
        redacted = re.sub(regex, "[REDACTED:SECRET]", redacted)
    for code, _, regex, _ in _SKILL_PATTERNS:
        redacted = re.sub(regex, "[REDACTED:CONTEXT]" if code in {"private_ip", "internal_path"} else "[REDACTED:SECRET]", redacted)
    for pattern in _DEFAULT_INPUT_POLICY["pii_patterns"]:
        redacted = re.sub(pattern["regex"], "[REDACTED:PII]", redacted)
    collapsed = " ".join(redacted.strip().split())
    return collapsed if len(collapsed) <= max_length else collapsed[:max(0, max_length - 3)] + "..."


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
    return redact_skill_excerpt(text)


def _severity(score: float) -> str:
    if score >= 0.9:
        return "critical"
    if score >= 0.75:
        return "high"
    return "medium"


class SkillGuardrail:
    def scan(self, content: str) -> SkillScanResult:
        if not content or not content.strip():
            return SkillScanResult(safe=True, risk_score=0.0, line_count=0, char_count=0)
        # The compiled scanner predates scoped prohibitions and reference-valued
        # assignments. Keep those inputs on the canonical Python path.
        disclosures = unsafe_disclosure_instructions(content)
        needs_python = bool(disclosures or _NEGATION_RE.search(content) or re.search(r"(?m)\b\w+\s*[:=]", content) or re.search(_SECRET_LINE_PATTERNS["private_key"], content) or contains_secret(content)[0])
        if _engine.enabled() and not needs_python:
            try:
                data = _engine.module().scan_skill(content)
                if data is None:
                    if content.strip():
                        raise ValueError("compiled scanner returned no result for nonempty content")
                    return SkillScanResult(safe=True, risk_score=0.0, line_count=0, char_count=0)
                scores = [float(data["risk_score"]), *(float(f["risk_score"]) for f in data["findings"])]
                if not all(math.isfinite(score) and 0 <= score <= 1 for score in scores):
                    raise ValueError("skill risk scores must be finite fractions between zero and one")
                findings = [
                    SkillFinding(
                        category=f["category"],
                        severity=_severity(float(f["risk_score"])),
                        check=f["check"],
                        reason=f["reason"],
                        reason_code=f["reason_code"],
                        line_number=f["line_number"],
                        snippet=_redact_snippet(f["snippet"]),
                        risk_score=float(f["risk_score"]),
                    )
                    for f in data["findings"]
                ]
                return SkillScanResult(
                    safe=len(findings) == 0,
                    risk_score=max((f.risk_score for f in findings), default=0.0),
                    findings=findings,
                    line_count=len(content.splitlines()),
                    char_count=len(content),
                )
            except Exception:
                pass  # fall through to the Python implementation
        if not content or not content.strip():
            return SkillScanResult(safe=True, risk_score=0.0, line_count=0, char_count=0)

        lines = content.splitlines()
        private_key_lines: set[int] = set()
        in_private_key = False
        for number, line in enumerate(lines, 1):
            if re.search(_SECRET_LINE_PATTERNS["private_key"], line):
                in_private_key = True
            if in_private_key:
                private_key_lines.add(number)
            if in_private_key and re.search(r"-----END (?:(?:(?:RSA|OPENSSH|EC|DSA|ENCRYPTED) )?PRIVATE KEY|PGP PRIVATE KEY BLOCK)-----", line):
                in_private_key = False
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
                    snippet="[REDACTED:SECRET]" if line_number in private_key_lines else _redact_snippet(snippet),
                    risk_score=risk_score,
                )
            )

        for line_no, line in enumerate(lines, start=1):
            clauses = _CLAUSE_BOUNDARY_RE.split(line)
            for code, check_name, regex, score in DANGEROUS_COMMAND_PATTERNS:
                if any(not is_prohibited_instruction(clause, match.start()) for clause in clauses for match in re.finditer(regex, clause)):
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
                if any(_actionable_match(code, line, match) for match in re.finditer(regex, line)):
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
                if any(_actionable_match(code, line, match) for match in re.finditer(regex, line)):
                    add(
                        "secret",
                        "Secret Detection",
                        f"Secret detected: {code} (line {line_no})",
                        "secret_detected",
                        0.95,
                        line_no,
                        line,
                    )

            secret_hit, secret_kind = contains_secret(line)
            # References such as password=os.getenv("PASSWORD") contain no value.
            assignments = [match for match in re.finditer(r"(?i)\b(?:api[_-]?key|secret|password|token|auth|[A-Z][A-Z0-9_]*)['\"]?\s*[:=]", line)
                           if _SENSITIVE_ENV_RE.search(match.group(0).split("=", 1)[0].split(":", 1)[0].strip(" '\"").replace("-", "_"))]
            reference_only = secret_kind in {"generic_api_key", "env_assignment"} and bool(assignments) and all(_reference_assignment(line, match) for match in assignments) and not any(value in line for value in _configured_secrets())
            credential_codes = {"gateway_api_key", "database_url", "credential_assignment", "bearer_token", "env_assignment"}
            already_found = any(f.line_number == line_no and (f.category == "secret" or f.reason_code in credential_codes) for f in findings)
            if secret_hit and not reference_only and not already_found:
                add("secret", "Secret Detection", f"Secret detected: {secret_kind} (line {line_no})", "secret_detected", 0.95, line_no, line)

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

        for line_number, evidence in disclosures:
            add("env_exfiltration", "Credential Disclosure Instruction", f"Credential disclosure instruction on line {line_number}", "env_exfiltration_probe", 0.95, line_number, evidence)

        risk = max((f.risk_score for f in findings), default=0.0)
        return SkillScanResult(
            safe=len(findings) == 0,
            risk_score=risk,
            findings=sorted(findings, key=lambda f: (-f.risk_score, f.line_number or 0)),
            line_count=len(lines),
            char_count=len(content),
        )
