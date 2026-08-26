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
    # Generic api_key = value assignment (best-effort)
    "generic_api_key": re.compile(r"(?i)\b(?:api[_-]?key|groq[_-]?api[_-]?key|openai[_-]?api[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}['\"]?"),
    # Explicit env-name mention — often exfiltration attempts include the literal
    # env var name even without a value (e.g. "what is GROQ_API_KEY?").
    # We do NOT redact every occurrence globally (too noisy), but the input
    # guardrail blocks it. For scrubbing we only redact when a value-like suffix
    # follows.
    "env_assignment": re.compile(r"(?i)\b(?:GROQ_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY)\s*[:=]\s*[^\s\"']{8,}"),
}

# Attempts to make the model reveal env / secrets.
_ENV_EXFIL_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?i)\bGROQ_API_KEY\b"),
    re.compile(r"(?i)\bOPENAI_API_KEY\b"),
    re.compile(r"(?i)\bANTHROPIC_API_KEY\b"),
    re.compile(r"(?i)\bGEMINI_API_KEY\b"),
    re.compile(r"(?i)\bprint\s*\(\s*(?:os\.)?environ"),
    re.compile(r"(?i)\bprocess\.env\b"),
    re.compile(r"(?i)\bshow\s+me\s+.*\b(?:secret|api[_-]?key|env)\b"),
    re.compile(r"(?i)\bwhat\s+is\s+.*\b(?:groq|openai|anthropic)\b.*\bkey\b"),
    re.compile(r"(?i)\b(?:reveal|expose|leak|dump)\b.*\b(?:key|secret|token|env)\b"),
    re.compile(r"(?i)\b(?:cat|print|echo)\b.*\.env\b"),
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


def contains_secret(text: str) -> tuple[bool, str | None]:
    """Return (True, kind) if *text* matches any secret pattern."""
    if not text:
        return False, None
    for kind, pat in _SECRET_PATTERNS.items():
        if pat.search(text):
            return True, kind
    # literal configured key
    for sec in _configured_secrets():
        if sec and sec in text:
            return True, "configured_provider_key"
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
