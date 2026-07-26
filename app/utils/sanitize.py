"""Input sanitization — strip control chars, enforce size limits, detect null bytes."""

import re
from typing import Any

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_NULL_BYTE = re.compile(r"\x00")
_STRIP_LEADING_TRAILING_WS = re.compile(r"^\s+|\s+$")
_MULTILINE_TRIM = re.compile(r"\n{4,}")


def sanitize_string(value: str, max_length: int = 32_000) -> str:
    if not isinstance(value, str):
        raise ValueError("Expected a string")
    if _NULL_BYTE.search(value):
        raise ValueError("Null byte detected in input")
    value = _CONTROL_CHARS.sub("", value)
    value = _MULTILINE_TRIM.sub("\n\n\n", value)
    return value[:max_length]


def sanitize_email(value: str) -> str:
    return sanitize_string(value.strip().lower(), 254)


def sanitize_name(value: str) -> str:
    return sanitize_string(value.strip(), 120)


def sanitize_prompt(value: str) -> str:
    return sanitize_string(value, 32_000)


def strip_object(obj: dict[str, Any], max_length: int = 32_000) -> dict[str, Any]:
    return {
        k: sanitize_string(v, max_length) if isinstance(v, str) else v
        for k, v in obj.items()
    }
