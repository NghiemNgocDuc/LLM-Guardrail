"""Output Guardrails — 2026: grounding, 4-way actions, sampling"""
import json
import random
from dataclasses import dataclass
from typing import Optional

from app.i18n import _t_or

# Multi-word phrases first — lower false-positive risk than single words.
_TOXIC_PHRASES = [
    "kill yourself",
    "kill all",
    "death to all",
    "i will kill you",
    "i'm going to kill",
    "bomb threat",
    "how to make a bomb",
    "how to build a weapon",
    "how to make explosives",
    "instructions for mass",
    "steps to commit",
    "mass shooting",
    "mass murder",
    "school shooting",
    "suicide bombing",
    "ethnic cleansing",
    "white supremacy",
    "child pornography",
    "child sexual abuse",
]

# Single keywords — kept to clearly unambiguous terms to reduce false positives.
_TOXIC_KEYWORDS = [
    "genocide",
    "massacre",
    "slaughter",
    "exterminate",
    "decapitate",
    "dismember",
    "mutilate",
    "terrorism",
    "terrorist attack",
]


@dataclass
class OutputGuardrailResult:
    allowed: bool
    check: str = ""
    reason: Optional[str] = None
    reason_code: str = "clean"
    risk_score: float = 0.0
    sanitized_output: Optional[str] = None
    warned: bool = False


class OutputGuardrail:
    def __init__(self, policy: dict, compliance_rules: dict, topic_policy: dict):
        self.policy = policy
        self.compliance = compliance_rules
        self.topics = topic_policy

    def check(self, response: str, grounding_context: str | None = None) -> OutputGuardrailResult:
        # Sampling for high-volume (Bifrost): skip expensive checks with probability
        sample_rate = self.policy.get("sample_rate") or self.policy.get("output_sample_rate")
        if sample_rate is not None:
            try:
                if random.random() > float(sample_rate):
                    return OutputGuardrailResult(allowed=True, check="Sampled", reason="sampled", reason_code="sampled", risk_score=0.0, sanitized_output=response)
            except Exception:
                pass

        # Secret leakage always blocks regardless of policy
        err = self._check_secret_leakage(response)
        if err:
            return OutputGuardrailResult(
                allowed=False,
                check="Secret Leakage",
                reason=err,
                reason_code="secret_leakage",
                risk_score=0.95,
            )

        if self.policy.get("enforce_schema"):
            err = self._validate_schema(response)
            if err:
                mode = self.policy.get("schema_mode", "block")
                if mode == "warn":
                    return OutputGuardrailResult(allowed=True, warned=True, check="Schema Validation", reason=err, reason_code="warned_schema_violation", risk_score=0.3, sanitized_output=response)
                if mode == "review":
                    return OutputGuardrailResult(allowed=True, warned=True, check="Schema Validation", reason=err, reason_code="review_schema_violation", risk_score=0.4, sanitized_output=response)
                return OutputGuardrailResult(
                    allowed=False, check="Schema Validation",
                    reason=err, reason_code="schema_violation", risk_score=0.6,
                )

        if self.policy.get("block_toxic_content"):
            err = self._check_toxicity(response)
            if err:
                mode = self.policy.get("toxic_mode", "block")
                if mode == "warn":
                    return OutputGuardrailResult(
                        allowed=True, warned=True,
                        check="Toxicity Filter", reason=err,
                        reason_code="warned_toxic_content", risk_score=0.6,
                        sanitized_output=response,
                    )
                if mode == "review":
                    return OutputGuardrailResult(
                        allowed=True, warned=True,
                        check="Toxicity Filter", reason=err,
                        reason_code="review_toxic_content", risk_score=0.6,
                        sanitized_output=response,
                    )
                if mode == "redact":
                    # redact toxic phrases with placeholder
                    sanitized = response
                    for phrase in _TOXIC_PHRASES + _TOXIC_KEYWORDS:
                        sanitized = sanitized.replace(phrase, "[REDACTED:TOXIC]")
                    return OutputGuardrailResult(
                        allowed=True, warned=True,
                        check="Toxicity Filter", reason=err,
                        reason_code="redacted_toxic_content", risk_score=0.5,
                        sanitized_output=sanitized,
                    )
                return OutputGuardrailResult(
                    allowed=False, check="Toxicity Filter",
                    reason=err, reason_code="toxic_content", risk_score=0.8,
                )

        err = self._check_topic_policy(response)
        if err:
            mode = self.policy.get("topic_mode", "block")
            if mode == "warn":
                return OutputGuardrailResult(allowed=True, warned=True, check="Topic Policy", reason=err, reason_code="warned_blocked_topic", risk_score=0.4, sanitized_output=response)
            if mode == "review":
                return OutputGuardrailResult(allowed=True, warned=True, check="Topic Policy", reason=err, reason_code="review_blocked_topic", risk_score=0.5, sanitized_output=response)
            return OutputGuardrailResult(
                allowed=False, check="Topic Policy",
                reason=err, reason_code="blocked_topic", risk_score=0.75,
            )

        # Grounding / hallucination check (requires context)
        if grounding_context is not None or self.policy.get("grounding_required"):
            err = self._check_grounding(response, grounding_context or self.policy.get("grounding_context", ""))
            if err:
                mode = self.policy.get("grounding_mode", "block")
                if mode == "warn":
                    return OutputGuardrailResult(allowed=True, warned=True, check="Grounding", reason=err, reason_code="warned_grounding", risk_score=0.6, sanitized_output=response)
                if mode == "review":
                    return OutputGuardrailResult(allowed=True, warned=True, check="Grounding", reason=err, reason_code="review_grounding", risk_score=0.7, sanitized_output=response)
                return OutputGuardrailResult(allowed=False, check="Grounding", reason=err, reason_code="grounding_failed", risk_score=0.8)

        err = self._check_external_validators(response)
        if err:
            # external_validator_mode: "block" (default) | "warn" | "review"
            mode = self.policy.get("external_validator_mode", "block")
            if mode == "warn":
                return OutputGuardrailResult(
                    allowed=True, warned=True,
                    check="External Validators", reason=err,
                    reason_code="external_validator_flagged", risk_score=0.5,
                    sanitized_output=response,
                )
            if mode == "review":
                return OutputGuardrailResult(
                    allowed=True, warned=True,
                    check="External Validators", reason=err,
                    reason_code="review_external_validator", risk_score=0.5,
                    sanitized_output=response,
                )
            return OutputGuardrailResult(
                allowed=False, check="External Validators",
                reason=err, reason_code="external_validator_failed", risk_score=0.5,
            )

        return OutputGuardrailResult(
            allowed=True, check="All Output Checks",
            reason_code="clean", risk_score=0.0, sanitized_output=response,
        )

    def _check_secret_leakage(self, response: str) -> Optional[str]:
        from app.utils.secret_redaction import contains_secret  # lazy

        hit, kind = contains_secret(response)
        if hit:
            return _t_or(
                "guardrail.secret_leakage",
                "Potential credential leakage detected ({kind})",
                kind=kind or "secret",
            )
        # Keep the old broad heuristic as a safety net (e.g. non-standard prefixes)
        lower = response.lower()
        if "api_key=" in lower or "authorization: bearer" in lower:
            return _t_or("guardrail.secret_leakage", "Potential credential leakage detected")
        return None

    def _validate_schema(self, response: str) -> Optional[str]:
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            return _t_or("guardrail.schema_invalid_json", "Response is not valid JSON")
        missing = [f for f in self.policy.get("required_fields", []) if f not in data]
        if missing:
            return _t_or("guardrail.schema_missing_fields", "Missing fields: {missing}", missing=missing)
        return None

    def _check_toxicity(self, response: str) -> Optional[str]:
        lower = response.lower()
        for phrase in _TOXIC_PHRASES:
            if phrase in lower:
                return _t_or("guardrail.toxic_content", "Toxic content detected: '{term}'", term=phrase)
        for word in _TOXIC_KEYWORDS:
            if word in lower:
                return _t_or("guardrail.toxic_content", "Toxic content detected: '{term}'", term=word)
        return None

    def _check_topic_policy(self, response: str) -> Optional[str]:
        lower = response.lower()
        for topic in self.topics.get("blocked_topics", []):
            if topic.lower() in lower:
                return _t_or("guardrail.blocked_topic", "Blocked topic: '{topic}'", topic=topic)
        if self.compliance.get("block_medical_advice"):
            for sig in ["you should take", "dosage", "prescription", "diagnos"]:
                if sig in lower:
                    return _t_or("guardrail.medical_advice", "Medical advice detected")
        return None

    def _check_grounding(self, response: str, context: str) -> Optional[str]:
        """Hallucination / grounding check — ensure response is supported by context."""
        if not context or not self.policy.get("grounding_required"):
            return None
        # Simple heuristic: if context is provided, response should share at least one 3-gram
        # Real impl would use vector similarity; this is a cheap fail-closed stub
        import re
        ctx_tokens = set(re.findall(r"\w+", context.lower()))
        resp_tokens = set(re.findall(r"\w+", response.lower()))
        if not resp_tokens:
            return None
        overlap = len(ctx_tokens & resp_tokens) / max(len(resp_tokens), 1)
        threshold = float(self.policy.get("grounding_threshold", 0.3))
        if overlap < threshold:
            return _t_or("guardrail.grounding_failed", "Response not grounded in provided context (overlap {overlap:.2f} < {threshold})", overlap=overlap, threshold=threshold)
        return None

    def _check_external_validators(self, response: str) -> Optional[str]:
        """Run guardrails-ai-style external validators configured via
        output_rules.external_validators (see app/services/guardrail_validators.py)."""
        config = self.policy.get("external_validators")
        if not config:
            return None
        from app.services.guardrail_validators import run_validators  # noqa: PLC0415
        passed, name, message = run_validators(response, config)
        if not passed:
            return f"External validator '{name}' failed: {message}"
        return None
