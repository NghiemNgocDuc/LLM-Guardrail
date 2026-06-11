"""
PII Redaction Engine
====================
Detects and replaces PII (emails, SSNs, credit cards, phone numbers, IP addresses)
with reversible placeholder tokens. The original values are stored in a mapping so
that responses from the LLM can be "unredacted" if the policy allows it.

Supports three modes controlled by org policy:
  - "block"   : legacy behaviour — reject the request entirely (handled upstream)
  - "redact"  : replace PII with placeholders, forward to LLM, restore in response
  - "off"     : no PII processing at all
"""
import re
from dataclasses import dataclass, field
from typing import Optional


# ─── PII Pattern Definitions ─────────────────────────────────────────────────

PII_PATTERNS: list[dict] = [
    {
        "name": "email",
        "label": "Email address",
        "regex": r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
        "placeholder": "[EMAIL_REDACTED_{n}]",
    },
    {
        "name": "ssn",
        "label": "Social Security Number",
        "regex": r"\b\d{3}-\d{2}-\d{4}\b",
        "placeholder": "[SSN_REDACTED_{n}]",
    },
    {
        "name": "credit_card",
        "label": "Credit card number",
        "regex": r"\b(?:\d[ \-]?){13,16}\b",
        "placeholder": "[CC_REDACTED_{n}]",
    },
    {
        "name": "phone_us",
        "label": "US phone number",
        "regex": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "placeholder": "[PHONE_REDACTED_{n}]",
    },
    {
        "name": "ip_address",
        "label": "IP address",
        "regex": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "placeholder": "[IP_REDACTED_{n}]",
    },
]


@dataclass
class RedactionResult:
    """Returned by the redactor after processing a prompt."""
    redacted_text: str
    original_text: str
    pii_found: bool
    pii_count: int = 0
    pii_types: list[str] = field(default_factory=list)
    # Mapping of placeholder → original value, used to restore in output
    mapping: dict[str, str] = field(default_factory=dict)


class PIIRedactor:
    """
    Scans text for PII patterns and replaces matches with numbered placeholders.
    Keeps an internal mapping so the operation is reversible.
    """

    def __init__(self, extra_patterns: Optional[list[dict]] = None):
        self.patterns = list(PII_PATTERNS)
        if extra_patterns:
            self.patterns.extend(extra_patterns)

    def redact(self, text: str) -> RedactionResult:
        """
        Replace all PII occurrences in *text* with placeholders.
        Returns a RedactionResult containing the cleaned text and a
        mapping that can be used to restore the originals later.
        """
        mapping: dict[str, str] = {}
        pii_types: list[str] = []
        counter = 0
        redacted = text

        for pat in self.patterns:
            compiled = re.compile(pat["regex"])
            for match in compiled.finditer(redacted):
                original_value = match.group()
                counter += 1
                placeholder = pat["placeholder"].format(n=counter)
                mapping[placeholder] = original_value
                if pat["name"] not in pii_types:
                    pii_types.append(pat["name"])
                # Replace only the first occurrence each time (they shift)
                redacted = redacted.replace(original_value, placeholder, 1)

        return RedactionResult(
            redacted_text=redacted,
            original_text=text,
            pii_found=counter > 0,
            pii_count=counter,
            pii_types=pii_types,
            mapping=mapping,
        )

    def restore(self, text: str, mapping: dict[str, str]) -> str:
        """
        Reverse the redaction — replace placeholders back with originals.
        Useful if the policy allows PII to appear in the response.
        """
        restored = text
        for placeholder, original in mapping.items():
            restored = restored.replace(placeholder, original)
        return restored
