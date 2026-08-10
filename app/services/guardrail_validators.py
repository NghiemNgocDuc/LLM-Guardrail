"""
External output validators — run plain, dependency-free validators that mirror
the guardrails-ai `Validator` interface (validate(value, metadata) →
ValidationResult), plus "competitor detection", against LLM output before it is
delivered.

Admins enable them per policy via output_rules:

    output_rules: {
      "external_validators": [
        {"name": "ValidLength", "kwargs": {"min": 5, "max": 2000}},
        {"name": "RegexMatch",  "kwargs": {"regex": "^[A-Z].*[.!?]$"}},
        {"name": "DenyList",    "kwargs": {"list": ["competitor products"]}},
        {"name": "AllowList",   "kwargs": {"list": ["yes", "no"]}},
        {"name": "RequiredFields", "kwargs": {"fields": ["answer", "citations"]}},
      ]
    }

The kwargs follow guardrails-ai's conventions (min/max, regex, list,
case_sensitive) so the same policy blob keeps working if you later swap in the
real `guardrails` package (it is an optional dependency).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass
class ValidationResult:
    outcome: str  # "pass" | "fail"
    message: str = ""


class BaseValidator:
    name = "base"

    def validate(self, value: str, metadata: dict | None = None) -> ValidationResult:  # noqa: ARG002
        raise NotImplementedError


class ValidLengthValidator(BaseValidator):
    """guardrails-ai ValidLength equivalent: value must be within [min, max]."""

    name = "ValidLength"

    def __init__(self, min: int = 0, max: int = 10_000):  # noqa: A002
        self.min, self.max = min, max

    def validate(self, value: str, metadata: dict | None = None) -> ValidationResult:
        length = len(value)
        if length < self.min:
            return ValidationResult("fail", f"Response too short ({length} chars, min {self.min})")
        if length > self.max:
            return ValidationResult("fail", f"Response too long ({length} chars, max {self.max})")
        return ValidationResult("pass")


class RegexMatchValidator(BaseValidator):
    """guardrails-ai RegexMatch equivalent: value must match the pattern."""

    name = "RegexMatch"

    def __init__(self, regex: str):
        self.regex = re.compile(regex)

    def validate(self, value: str, metadata: dict | None = None) -> ValidationResult:
        if self.regex.search(value):
            return ValidationResult("pass")
        return ValidationResult("fail", f"Response does not match required pattern")


class DenyListValidator(BaseValidator):
    """guardrails-ai DenyList equivalent: reject output containing any term."""

    name = "DenyList"

    def __init__(self, list: list[str], case_sensitive: bool = False, match_exact: bool = False):  # noqa: A002
        self.terms = list
        self.case_sensitive = case_sensitive
        self.match_exact = match_exact

    def validate(self, value: str, metadata: dict | None = None) -> ValidationResult:
        check = value if self.case_sensitive else value.lower()
        terms = self.terms if self.case_sensitive else [t.lower() for t in self.terms]
        for term in terms:
            if (check == term) if self.match_exact else (term in check):
                return ValidationResult("fail", f"Response contains denied term: '{term}'")
        return ValidationResult("pass")


class AllowListValidator(BaseValidator):
    """guardrails-ai AllowList equivalent: reject output that is not one of the terms."""

    name = "AllowList"

    def __init__(self, list: list[str], case_sensitive: bool = False):  # noqa: A002
        self.terms = list
        self.case_sensitive = case_sensitive

    def validate(self, value: str, metadata: dict | None = None) -> ValidationResult:
        stripped = value.strip().lower() if not self.case_sensitive else value.strip()
        allowed = self.terms if self.case_sensitive else [t.lower() for t in self.terms]
        if stripped in allowed:
            return ValidationResult("pass")
        return ValidationResult("fail", "Response is not one of the allowed values")


class RequiredFieldsValidator(BaseValidator):
    """JSON output must contain every listed field (superset of schema checks)."""

    name = "RequiredFields"

    def __init__(self, fields: list[str]):
        self.fields = fields

    def validate(self, value: str, metadata: dict | None = None) -> ValidationResult:
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return ValidationResult("fail", "Response is not valid JSON")
        missing = [f for f in self.fields if f not in data]
        if missing:
            return ValidationResult("fail", f"Missing fields: {missing}")
        return ValidationResult("pass")


class CompetitorDetector(BaseValidator):
    """Block output that names/promotes configured competitor brands."""

    name = "CompetitorDetector"

    def __init__(self, brands: list[str]):
        self.brands = [b.lower() for b in brands]

    def validate(self, value: str, metadata: dict | None = None) -> ValidationResult:
        lower = value.lower()
        for brand in self.brands:
            if brand in lower:
                return ValidationResult("fail", f"Response mentions competitor: '{brand}'")
        return ValidationResult("pass")


# The `guardrails` package (guardrails-ai) is an optional drop-in: validators
# registered here are our built-ins, which share the same names and kwarg
# conventions. If the package is installed, its Validator classes can be
# referenced by full import path ("guardrails.validators.ValidLength").
_BUILTINS: dict[str, type[BaseValidator]] = {
    "ValidLength": ValidLengthValidator,
    "RegexMatch": RegexMatchValidator,
    "DenyList": DenyListValidator,
    "AllowList": AllowListValidator,
    "RequiredFields": RequiredFieldsValidator,
    "CompetitorDetector": CompetitorDetector,
}


def build_validator(name: str, kwargs: dict | None = None) -> BaseValidator | None:
    kwargs = dict(kwargs or {})
    cls = _BUILTINS.get(name)
    if cls is not None:
        return cls(**kwargs)
    if name.startswith("guardrails."):
        try:
            import guardrails.validators  # noqa: PLC0415 — optional dependency
            return guardrails.validators.get_validator(name.split(".")[-1], **kwargs)
        except Exception:
            return None
    return None


def run_validators(response: str, config: list[dict] | None) -> tuple[bool, str, str]:
    """Run a policy's external_validators against the response.

    Returns (passed, validator_name, fail_message). Stops at the first failure.
    """
    for entry in config or []:
        name = entry.get("name", "")
        validator = build_validator(name, entry.get("kwargs"))
        if validator is None:
            return False, name, f"Unknown validator: {name}"
        result = validator.validate(response)
        if result.outcome != "pass":
            return False, name, result.message or f"Validator '{name}' failed"
    return True, "", ""