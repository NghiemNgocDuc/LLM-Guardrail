"""Advisory skill comparisons, scoped to the complete tenant/policy snapshot."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from app.utils.secret_redaction import contains_secret
from guardrails.skill import SkillGuardrail, is_prohibited_instruction, redact_skill_excerpt

_CACHE: OrderedDict[str, "ConflictCheckResult"] = OrderedDict()
_CACHE_LOCK = RLock()
_CACHE_MAX = 1024


def _cache_key(content: str, org_policy: dict | None, existing_skills: list[dict[str, Any]], org_id: str | None = None) -> str:
    snapshot = {"content": content, "org_id": org_id, "policy": org_policy or {}, "existing_skills": existing_skills}
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


_OPPOSING_PAIRS = [
    ("never share api keys", "share api keys", "API key sharing"),
    ("never expose secrets", "expose secrets", "Secret exposure"),
    ("never disclose secrets", "disclose secrets", "Secret disclosure"),
    ("do not print env", "print env", "Environment leakage"),
    ("never include credentials", "include credentials", "Credential inclusion"),
    ("never hardcode credentials", "hardcode credentials", "Hardcoded credential"),
    ("never leak api key", "leak api key", "API key leakage"),
    ("do not reveal secrets", "reveal secrets", "Secret reveal"),
    ("never echo secrets", "echo secrets", "Secret echo"),
    ("block secrets", "allow secrets", "Secret policy"),
    ("never run rm -rf", "run rm -rf", "Destructive command"),
    ("never execute shell", "execute shell", "Shell execution"),
    ("read-only", "write files", "Write permission"),
]
_CLAUSES = re.compile(r"(?<=[;.!?])\s+|\b(?:but|however|instead|then|nevertheless)\b", re.I)
_PII_INSTRUCTION_RE = re.compile(r"(?i)\b(?:collect\s+ssn|collect\s+credit\s+card|gather\s+pii|store\s+email)\b")


@dataclass
class SkillConflict:
    type: str
    severity: str
    reason: str
    reason_code: str
    evidence: str = ""
    conflicting_skill_slug: str | None = None
    conflicting_skill_name: str | None = None
    line_number: int | None = None
    remediation: str = ""


@dataclass
class ConflictCheckResult:
    has_conflict: bool
    conflicts: list[SkillConflict] = field(default_factory=list)
    # Legacy hard-block eligibility: critical advisory findings, independent of save.
    blocked_by_policy: bool = False
    policy_findings: list[dict[str, Any]] = field(default_factory=list)
    safe: bool = True
    summary: str = ""


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _isolated_has(text_low: str, phrase: str, negated: str | None = None) -> bool:
    negated_spans = [(match.start(), match.end()) for match in re.finditer(re.escape(negated), text_low)] if negated else []
    for match in re.finditer(re.escape(phrase), text_low):
        if any(start <= match.start() and match.end() <= end for start, end in negated_spans):
            continue
        if not is_prohibited_instruction(text_low, match.start()):
            return True
    return False


def _find_directive_conflicts(new_content: str, existing_skills: list[dict[str, Any]]) -> list[SkillConflict]:
    low = new_content.lower(); conflicts = []
    for existing in existing_skills:
        old = (existing.get("content") or "").lower()
        slug = redact_skill_excerpt(str(existing.get("slug") or existing.get("name") or "existing"), 160)
        name = redact_skill_excerpt(str(existing.get("name") or slug), 160)
        for safe, unsafe, label in _OPPOSING_PAIRS:
            old_safe = safe in old; new_safe = safe in low
            old_unsafe = _isolated_has(old, unsafe, safe); new_unsafe = _isolated_has(low, unsafe, safe)
            if (old_safe and new_unsafe) or (old_unsafe and new_safe):
                leaking = old_safe and new_unsafe
                severity = "critical" if leaking and ("api key" in label.lower() or "secret" in label.lower()) else "high"
                conflicts.append(SkillConflict(type="directive_conflict", severity=severity,
                    reason=f"Directive conflict on '{label}': new skill opposes '{slug}'", reason_code="directive_conflict",
                    evidence=f"Existing '{slug}' has '{safe if old_safe else unsafe}' — new has '{unsafe if new_unsafe else safe}'",
                    conflicting_skill_slug=slug, conflicting_skill_name=name,
                    remediation="Resolve the opposing directives before distributing the skill."))
    return conflicts


def _unprohibited_matches(content: str, pattern: re.Pattern):
    for clause in _CLAUSES.split(content):
        for match in pattern.finditer(clause):
            if not is_prohibited_instruction(clause, match.start()):
                yield match


def check_skill_conflicts(new_content: str, *, existing_skills: list[dict[str, Any]] | None = None,
                          org_policy: dict[str, Any] | None = None, org_id: str | None = None) -> ConflictCheckResult:
    existing_skills = deepcopy(existing_skills or [])
    org_policy = deepcopy(org_policy or {})
    key = _cache_key(new_content, org_policy, existing_skills, org_id)
    with _CACHE_LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return deepcopy(_CACHE[key])

    conflicts: list[SkillConflict] = []
    policy_findings: list[dict[str, Any]] = []
    credential_codes = {"gateway_api_key", "database_url", "credential_assignment", "bearer_token", "env_assignment"}
    for finding in SkillGuardrail().scan(new_content).findings:
        kind = "secret_leak" if finding.category == "secret" or finding.reason_code in credential_codes else "env_exfiltration" if finding.category == "env_exfiltration" else "destructive_command" if finding.category == "destructive_command" else "pii_leak" if finding.category == "pii" else "policy_conflict"
        remediation = "Remove credential values and disclosure instructions; refer to a server-side environment variable or secret manager." if kind in {"secret_leak", "env_exfiltration"} else "Remove personal data from agent context." if kind == "pii_leak" else "Replace destructive commands with a scoped, reversible operation." if kind == "destructive_command" else "Remove sensitive infrastructure details from the shared agent context."
        conflicts.append(SkillConflict(type=kind, severity=finding.severity, reason=f"{finding.check} detected on line {finding.line_number}",
            reason_code=finding.reason_code, evidence=finding.snippet, line_number=finding.line_number, remediation=remediation))
        policy_findings.append({"category": finding.category, "reason_code": finding.reason_code, "check": finding.check})

    conflicts.extend(_find_directive_conflicts(new_content, existing_skills))
    if org_policy.get("block_pii") and next(_unprohibited_matches(new_content, _PII_INSTRUCTION_RE), None) is not None:
        if not any(conflict.type == "pii_leak" for conflict in conflicts):
            conflicts.append(SkillConflict(type="pii_leak", severity="high", reason="Skill requests PII collection while the organization blocks PII",
                reason_code="pii_instruction_conflict", remediation="Do not collect personal identifiers in agent instructions."))

    # A synchronous heuristic is reproducible and never silently sends context
    # to an external model. Semantic judging belongs in an explicit, awaited API.
    from guardrails.semantic import heuristic_implicit
    implicit, evidence = heuristic_implicit(new_content)
    if implicit:
        conflicts.append(SkillConflict(type="pii_leak", severity="high", reason="Implicit identifying description detected", reason_code="implicit_pii",
            evidence=redact_skill_excerpt(evidence, 80), remediation="Remove or generalize the identifying description."))

    has_conflict = bool(conflicts)
    critical = sum(conflict.severity == "critical" for conflict in conflicts)
    result = ConflictCheckResult(has_conflict=has_conflict, conflicts=conflicts, blocked_by_policy=critical > 0,
        policy_findings=policy_findings, safe=not has_conflict,
        summary=f"Conflict detected: {len(conflicts)} issue(s) ({critical} critical). Review findings and opposing directives." if has_conflict else "No conflicts: new skill is compatible with current guardrails and existing skills.")
    with _CACHE_LOCK:
        _CACHE[key] = deepcopy(result); _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)
    return result


def _safe_live_url(value: str) -> str:
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("live_url must not contain control characters")
    parsed = urlsplit(value)
    if parsed.scheme not in {"", "http", "https"} or (not parsed.scheme and (not value.startswith("/") or value.startswith("//"))) or (parsed.scheme and not parsed.netloc):
        raise ValueError("live_url must be an HTTP(S) URL or a root-relative path")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("live_url must not include credentials")
    credential_parameter = re.compile(r"(?:^|[_-])(?:key|token|bearer|auth|authorization|password|secret|credential)(?:$|[_-])", re.I)
    if contains_secret(value)[0] or any(credential_parameter.search(name) or contains_secret(parameter_value)[0] for name, parameter_value in parse_qsl(parsed.query, keep_blank_values=True)):
        raise ValueError("live_url must not include credential query parameters")
    return value


def build_skill_md(slug: str, name: str, description: str, content: str, version: int,
                   content_hash: str | None = None, update_mode: str = "overwrite", live_url: str | None = None) -> str:
    """Wrap byte-exact source content in safely quoted managed metadata."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", slug):
        raise ValueError("invalid managed skill slug")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ValueError("skill version must be a positive integer")
    full_hash = _hash(content); short_hash = content_hash or full_hash[:12]
    mode = update_mode if update_mode in {"overwrite", "versioned"} else "overwrite"
    live = _safe_live_url(live_url or f"/skills/live/{slug}")
    # JSON strings are valid double-quoted YAML scalars, including embedded newlines.
    quote = lambda value: json.dumps(str(value), ensure_ascii=False)
    metadata_description = redact_skill_excerpt(description or name, 1000)
    header = (f"---\nname: {quote(slug)}\ndescription: {quote(metadata_description)}\nversion: {version}\n"
        f"hash: {quote(short_hash)}\nfull_hash: {quote(full_hash)}\nmanaged_by: llm-guardrails\nupdate_mode: {mode}\n"
        f"live_url: {quote(live)}\ndownloaded_at: {quote(_dt.datetime.now(_dt.timezone.utc).isoformat())}\n---\n\n")
    filename = "SKILL.md" if mode == "overwrite" else f"SKILL.v{version}.md"
    behavior = "Overwrite installation" if mode == "overwrite" else "Versioned installation"
    install = f".cursor/skills/{slug}/{filename}"
    guidance = f"> **{behavior}** — fetch the intended version and install it at `{install}`. " + ("Replace the existing file explicitly." if mode == "overwrite" else "Keep prior files if needed and configure the consumer to select the intended version.") + " This document does not fetch, install, or update itself.\n\n"
    reporting = ("\n\n---\n**Report blocked — coding agent must report back:**\n"
        "If AI Guardrails blocks this skill, report the status, reason_code, reason, X-Request-ID and X-Correlation-ID to the user. "
        "Report via POST /skills/rejections/report or show the block in chat. Do not hide blocks.\n")
    return header + guidance + content + reporting
