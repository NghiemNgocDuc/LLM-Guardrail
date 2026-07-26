"""Shared default guardrail policy constants."""

DEFAULT_INPUT_RULES = {
    "block_secrets": True,
    "block_pii": True,
    "pii_patterns": [
        {"name": "credit_card", "regex": r"\b(?:\d[ -]?){13,16}\b"},
        {"name": "ssn",         "regex": r"\b\d{3}-\d{2}-\d{4}\b"},
        {"name": "email",       "regex": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"},
    ],
    "block_prompt_injection": True,
    "injection_keywords": [
        "ignore previous instructions",
        "disregard your system prompt",
        "forget everything",
        "reveal your system prompt",
        "print your hidden instructions",
        "bypass the policy",
        "disable safety",
    ],
    "block_jailbreak": True,
    "jailbreak_patterns": [
        "DAN mode",
        "developer mode",
        "pretend you have no restrictions",
        "act as an unrestricted",
        "you are now jailbroken",
        "simulated sandbox",
        "do not include any safety warnings",
        "unrestricted terminal",
        "silently logs keystrokes",
        "log keystrokes",
        "keystroke logger",
        "keylogger",
    ],
}

DEFAULT_OUTPUT_RULES = {
    "enforce_schema": False,
    "block_toxic_content": True,
    "required_fields": [],
}

DEFAULT_TOPIC_POLICY = {"blocked_topics": ["competitor products", "medical advice"]}

DEFAULT_COMPLIANCE = {"block_medical_advice": True, "never_discuss_competitors": True}
