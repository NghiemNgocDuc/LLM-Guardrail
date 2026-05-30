"""
Input Guardrails
"""
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GuardrailResult:
    allowed: bool
    check: str = ""
    reason: Optional[str] = None
    flagged_content: list[str] = field(default_factory=list)


class InputGuardrail:
    def __init__(self, policy: dict):
        self.policy = policy

    def check(self, prompt: str) -> GuardrailResult:
        if self.policy.get("block_pii"):
            r = self._check_pii(prompt)
            if not r.allowed: return r
        if self.policy.get("block_prompt_injection"):
            r = self._check_injection(prompt)
            if not r.allowed: return r
        if self.policy.get("block_jailbreak"):
            r = self._check_jailbreak(prompt)
            if not r.allowed: return r
        return GuardrailResult(allowed=True, check="All Input Checks", reason="Clean")

    def _check_pii(self, prompt):
        for p in self.policy.get("pii_patterns", []):
            if re.search(p["regex"], prompt):
                return GuardrailResult(allowed=False, check="PII Detection", reason=f"PII detected: {p['name']}", flagged_content=[p["name"]])
        return GuardrailResult(allowed=True, check="PII Detection")

    def _check_injection(self, prompt):
        lower = prompt.lower()
        for kw in self.policy.get("injection_keywords", []):
            if kw.lower() in lower:
                return GuardrailResult(allowed=False, check="Injection Detection", reason=f"Prompt injection: '{kw}'")
        return GuardrailResult(allowed=True, check="Injection Detection")

    def _check_jailbreak(self, prompt):
        lower = prompt.lower()
        for p in self.policy.get("jailbreak_patterns", []):
            if p.lower() in lower:
                return GuardrailResult(allowed=False, check="Jailbreak Detection", reason=f"Jailbreak: '{p}'")
        return GuardrailResult(allowed=True, check="Jailbreak Detection")
