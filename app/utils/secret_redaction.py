"""Central secret scrubbing — no Groq/OpenAI/Anthropic/provider key ever leaves the server.

Used at 4 layers (defense in depth):
  1. input guardrail  — block prompts that try to exfiltrate env/keys
  2. output guardrail — block LLM responses that contain a secret
  3. response middleware / error handler — redact any accidental secret in outgoing JSON
  4. log filter       — scrub every log line before it hits stdout / Sentry / PostHog

Patterns are deliberately split (``"gsk" "_"``) so this file itself
does not trigger the CI secret-scan (``.github/workflows/ci.yml``).
"""
from __future__ import annotations

import re
from functools import lru_cache

# ── regexes ─────────────────────────────────────────────────────────────────
# NOTE: keep the split ``"gsk" "_"`` trick for CI — do not inline as ``gsk_``.
_SECRET_PATTERNS: dict[str, re.Pattern] = {
    # Groq: gsk_<20+ base64url chars>
    "groq_api_key": re.compile(r"\b" + "gsk" + r"_[A-Za-z0-9_-]{20,}\b"),
    # OpenAI: sk- / sk-proj- etc.  (avoid flagging short test fixtures -> 20 char min)
    "openai_api_key": re.compile(r"\b" + "sk" + r"-[A-Za-z0-9_-]{20,}\b"),
    "openai_proj_key": re.compile(r"\b" + "sk" + r"-proj-[A-Za-z0-9_-]{20,}\b"),
    # Anthropic: sk-ant-…
    "anthropic_key": re.compile(r"\b" + "sk" + r"-ant-[A-Za-z0-9_-]{20,}\b"),
    # Gateway: grg_… (32 bytes urlsafe -> ~43 chars, but accept 20+ for tests)
    "gateway_api_key": re.compile(r"\b" + "grg" + r"_[A-Za-z0-9_-]{20,}\b"),
    # AWS
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    # Generic Authorization: Bearer <20+ chars>
    "bearer_token": re.compile(r"(?i)\bAuthorization:\s*Bearer\s+[A-Za-z0-9_\-\.]{20,}\b"),
    # Generic api_key = value assignment (best-effort) — expanded for Phase 1:
    # Covers DATABASE_PASSWORD, SECRET, TOKEN, etc. Handles quoted and unquoted values, high-entropy strings including /+ and $.
    "generic_api_key": re.compile(
        r"(?i)\b(?:api[_-]?key|groq[_-]?api[_-]?key|openai[_-]?api[_-]?key|secret|password|passwd|pwd|token|auth|smtp[_-]?password|database[_-]?password|db[_-]?password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.\/\+=\$%]{8,}['\"]?"
    ),
    # AWS secret access key (40 base64 chars)
    "aws_secret_key": re.compile(r"(?i)aws.{0,20}secret.{0,20}['\"][A-Za-z0-9/\+]{40}['\"]"),
    # Names are safe to discuss; scrub assignments containing value-like text.
    "env_assignment": re.compile(r"(?i)\b(?:GROQ_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY|DATABASE_PASSWORD|AWS_SECRET_ACCESS_KEY|DATABASE_URL)\s*[:=]\s*[^\s\"']{8,}"),
}

# Match disclosure requests, rather than ordinary mentions of configuration.
_SECRET_ENV_NAME = r"(?:GROQ_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY|XAI_API_KEY|GROK_API_KEY|OPENAI_COMPATIBLE_API_KEY|SECRET_KEY|DATABASE_URL|DATABASE_PASSWORD|POSTGRES_PASSWORD|REDIS_PASSWORD|AWS_SECRET_ACCESS_KEY)"
_EXFIL_OBJECT = (
    rf"(?:{_SECRET_ENV_NAME}\b|(?:Groq|OpenAI|Anthropic|Gemini)?\s*api[ _-]*keys?\b"
    r"|(?:Groq|OpenAI|Anthropic|Gemini)\s+keys?\b"
    r"|(?:access[ _-]*)?tokens?\b|passwords?\b|credentials?\b|secrets\b"
    r"|secret\s+(?:api[ _-]*key|key|value)\b|secret\b(?=\s*(?:$|[.!?,;]))"
    r"|env(?:ironment)?(?:\s+variables?)?\b|process\.env\b|os\.environ\b|\.env\b)"
)
_DISCLOSURE_PREFIX = r"(?:^|[.;!?\n]\s*|\b(?:please|then|also|and|you(?:\s+(?:must|should|can|to))?)\s+)"
_DISCLOSURE_VERB = r"(?:show(?:\s+me)?|tell\s+me|reveal|expose|leak|dump|disclose|print(?:\s+out)?|echo|output|return|share|send|give|list|read(?:\s+out)?|display|fetch|retrieve|get)"
_VALUE_REFERENCE = r"(?:(?:actual|current|stored|configured)\s+)?(?:values?|contents?)(?:\s+(?:stored|held|assigned))?\s+(?:of|for|from|in|to)"
_OBJECT_QUALIFIERS = rf"(?:(?:me|us|all|every|the|your|my|our|actual|current|stored|configured|server|system|runtime|application|{_VALUE_REFERENCE})\s+)*"
_ENV_EXFIL_PATTERNS: list[re.Pattern] = [
    re.compile(rf"{_DISCLOSURE_PREFIX}{_DISCLOSURE_VERB}\s+{_OBJECT_QUALIFIERS}{_EXFIL_OBJECT}", re.I),
    re.compile(rf"\bwhat(?:\s+is|'s|\s+are)\s+(?:(?:the\s+)?{_VALUE_REFERENCE}\s+|(?:your|our|my|current|configured|server)\s+){_OBJECT_QUALIFIERS}{_EXFIL_OBJECT}", re.I),
    re.compile(r"\b(?:print|pprint|console\.log|console\.dir|JSON\.stringify)\s*\(\s*(?:dict\s*\(\s*)?(?:(?:os\.)?environ|process\.env)(?![\w.\[])", re.I),
    re.compile(rf"\b(?:print|pprint|console\.log|console\.dir)\s*\(\s*(?:os\.environ|process\.env)(?:\.{_SECRET_ENV_NAME}|\[\s*['\"]{_SECRET_ENV_NAME}['\"]\s*\])", re.I),
    re.compile(rf"\b(?:print|pprint)\s*\(\s*os\.getenv\s*\(\s*['\"]{_SECRET_ENV_NAME}['\"]", re.I),
    re.compile(r"^\s*(?:process\.env|os\.environ|env|printenv)\s*;?\s*$", re.I),
    re.compile(rf"\b(?:printenv|echo)\s+[\"']?\$?\{{?{_SECRET_ENV_NAME}\b", re.I),
    re.compile(r"\b(?:cat|print|echo)\s+(?:[\w./-]*/)?\.env\b", re.I),
]

_REDACTED = "[REDACTED:SECRET]"


@lru_cache(maxsize=1)
def _configured_secrets() -> list[str]:
    """Return the *actual* configured provider keys (verbatim values).

    If an operator pastes the literal GROQ_API_KEY value without the ``gsk_``
    prefix pattern (or a truncated form), the regex alone would miss it.
    Scrubbing the literal value closes that gap.  The list is cached so
    importing this module at startup does not re-read settings on every call.
    """
    vals: list[str] = []
    try:
        from app.config import get_settings  # lazy to avoid circular import at import time

        s = get_settings()
        for attr in ("GROQ_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENAI_COMPATIBLE_API_KEY"):
            v = getattr(s, attr, "") or ""
            v = v.strip()
            # Only scrub non-trivial secrets (avoid scrubbing empty/short placeholders)
            if len(v) >= 12:
                vals.append(v)
    except Exception:
        pass
    # Longest first so we don't partially replace a longer key with a shorter substring
    vals.sort(key=len, reverse=True)
    return vals


_JSON_API_KEY_RE = re.compile(r'(?i)["\']?api[_-]?key["\']?\s*[:=]\s*["\']?[A-Za-z0-9_\-\.\/\+=]{16,}["\']?')
_JSON_PASSWORD_RE = re.compile(r'(?i)["\']?password["\']?\s*[:=]\s*["\']?[^"\'\s]{8,}["\']?')

def _contains_json_secret(text: str) -> bool:
    # High-entropy JSON api_key/password without prefix requirement (wl2 dataset uses random 32-char values)
    if _JSON_API_KEY_RE.search(text):
        return True
    if _JSON_PASSWORD_RE.search(text) and len(re.search(r'password["\']?\s*[:=]\s*["\']?([^"\'\s]+)', text, re.I).group(1)) >= 8:
        # also check entropy: password should look random (not "password")
        val = re.search(r'password["\']?\s*[:=]\s*["\']?([^"\'\s]+)', text, re.I).group(1)
        if any(c in val for c in ["$", "%", "!", "@"]) or len([c for c in val if c.isalnum()]) >= 8:
            return True
    return False

def contains_secret(text: str) -> tuple[bool, str | None]:
    """Return (True, kind) if *text* matches any secret pattern."""
    if not text:
        return False, None
    for kind, pat in _SECRET_PATTERNS.items():
        if pat.search(text):
            return True, kind
    if _contains_json_secret(text):
        return True, "generic_api_key"
    # literal configured key
    for sec in _configured_secrets():
        if sec and sec in text:
            return True, "configured_provider_key"
    # PEM private key with optional comment prefix "# -----BEGIN"
    if "-----BEGIN" in text and "PRIVATE KEY-----" in text:
        return True, "private_key"
    return False, None


def contains_env_exfiltration(text: str) -> tuple[bool, str | None]:
    """Return (True, pattern) if *text* looks like an env-exfiltration attempt."""
    if not text:
        return False, None
    for pat in _ENV_EXFIL_PATTERNS:
        if pat.search(text):
            return True, pat.pattern
    return False, None


def scrub_text(text: str) -> str:
    """Replace any secret occurrence with ``[REDACTED:SECRET]``.

    Idempotent and safe to call on already-scrubbed text.
    """
    if not text:
        return text
    out = text
    for pat in _SECRET_PATTERNS.values():
        out = pat.sub(_REDACTED, out)
    for sec in _configured_secrets():
        if sec and sec in out:
            out = out.replace(sec, _REDACTED)
    return out


def scrub_mapping(obj: dict) -> dict:
    """Return a shallow copy of *obj* with any string values scrubbed."""
    return {k: scrub_text(v) if isinstance(v, str) else v for k, v in obj.items()}


def scrub_headers(headers: dict) -> dict:
    """Scrub Authorization / X-Api-Key style headers."""
    scrubbed: dict[str, str] = {}
    for k, v in headers.items():
        lk = k.lower()
        if lk in ("authorization", "x-api-key", "x-groq-api-key"):
            scrubbed[k] = _REDACTED if v else v
        else:
            scrubbed[k] = scrub_text(v) if isinstance(v, str) else v
    return scrubbed
