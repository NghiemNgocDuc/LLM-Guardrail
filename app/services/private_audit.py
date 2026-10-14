"""Fixed audit labels that never carry caller-authored evidence."""
from guardrails.dangerous_commands import DANGEROUS_COMMAND_PATTERNS
from guardrails.skill_messages import _REASON_MESSAGES

PRIVATE_PREVIEW = "[Content omitted in private mode]"
PRIVATE_FILENAME = "Private skill"

_REASON_CODES = frozenset(_REASON_MESSAGES) | frozenset(code for code, *_ in DANGEROUS_COMMAND_PATTERNS) | {
    "json_api_key", "json_password", "configured_provider_key", "env_exfiltration_probe",
    "prompt_injection", "jailbreak_attempt", "ml_prompt_injection", "semantic_blocked",
    "rego_rule_error", "rego_custom_rule", "secret_leakage", "schema_violation",
    "toxic_content", "contains_match", "blocked_topic", "grounding_failed",
    "external_validator_flagged", "external_validator_failed", "rate_limit",
    "clean", "sampled", "input_blocked", "output_blocked", "error",
    "guardrail_event",
}
_REASON_CODES |= frozenset(f"{prefix}_{code}" for prefix in ("warned", "review", "redacted") for code in _REASON_CODES)


def private_reason_code(value: str | None) -> str | None:
    """Keep known static codes; arbitrary policy/client prose is discarded."""
    if value is None:
        return None
    return value if isinstance(value, str) and value in _REASON_CODES else "guardrail_event"
