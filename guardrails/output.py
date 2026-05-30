"""Output Guardrails"""
import json
from dataclasses import dataclass, field
from typing import Optional

TOXIC_KEYWORDS = ["hate", "kill", "violence"]


@dataclass
class OutputGuardrailResult:
    allowed: bool
    check: str = ""
    reason: Optional[str] = None
    sanitized_output: Optional[str] = None


class OutputGuardrail:
    def __init__(self, policy: dict, compliance_rules: dict, topic_policy: dict):
        self.policy = policy
        self.compliance = compliance_rules
        self.topics = topic_policy

    def check(self, response: str) -> OutputGuardrailResult:
        if self.policy.get("enforce_schema"):
            err = self._validate_schema(response)
            if err: return OutputGuardrailResult(allowed=False, check="Schema Validation", reason=err)

        if self.policy.get("block_toxic_content"):
            err = self._check_toxicity(response)
            if err: return OutputGuardrailResult(allowed=False, check="Toxicity Filter", reason=err)

        err = self._check_topic_policy(response)
        if err: return OutputGuardrailResult(allowed=False, check="Topic Policy", reason=err)

        return OutputGuardrailResult(allowed=True, check="All Output Checks", sanitized_output=response)

    def _validate_schema(self, response):
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            return "Response is not valid JSON"
        missing = [f for f in self.policy.get("required_fields", []) if f not in data]
        return f"Missing fields: {missing}" if missing else None

    def _check_toxicity(self, response):
        lower = response.lower()
        for w in TOXIC_KEYWORDS:
            if w in lower:
                return f"Toxic content detected: '{w}'"
        return None

    def _check_topic_policy(self, response):
        lower = response.lower()
        for topic in self.topics.get("blocked_topics", []):
            if topic.lower() in lower:
                return f"Blocked topic: '{topic}'"
        if self.compliance.get("block_medical_advice"):
            for sig in ["you should take", "dosage", "prescription", "diagnos"]:
                if sig in lower:
                    return "Medical advice detected"
        return None
