"""
Input Guardrails
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from app.i18n import _t_or


@dataclass
class GuardrailResult:
    allowed: bool
    check: str = ""
    reason: Optional[str] = None
    reason_code: str = "clean"
    risk_score: float = 0.0
    flagged_content: list[str] = field(default_factory=list)
    warned: bool = False  # True when mode="warn" and a rule fired but request allowed through


class InputGuardrail:
    def __init__(self, policy: dict):
        self.policy = policy

    def check(self, prompt: str) -> GuardrailResult:
        if self.policy.get("block_secrets", True):
            r = self._check_secrets(prompt)
            if not r.allowed:
                return r

        if self.policy.get("block_pii"):
            r = self._check_pii(prompt)
            if not r.allowed:
                return r

        if self.policy.get("block_prompt_injection"):
            r = self._check_injection(prompt)
            if not r.allowed:
                if self.policy.get("injection_mode", "block") == "warn":
                    return GuardrailResult(
                        allowed=True, warned=True,
                        check=r.check, reason=r.reason,
                        reason_code=f"warned_{r.reason_code}",
                        risk_score=r.risk_score,
                    )
                return r

        if self.policy.get("block_jailbreak"):
            r = self._check_jailbreak(prompt)
            if not r.allowed:
                if self.policy.get("jailbreak_mode", "block") == "warn":
                    return GuardrailResult(
                        allowed=True, warned=True,
                        check=r.check, reason=r.reason,
                        reason_code=f"warned_{r.reason_code}",
                        risk_score=r.risk_score,
                    )
                return r

        if self.policy.get("semantic_mode") in ("block", "warn"):
            r = self._check_semantic(prompt)
            if not r.allowed:
                mode = self.policy.get("semantic_mode", "block")
                if mode == "warn":
                    return GuardrailResult(
                        allowed=True, warned=True,
                        check=r.check, reason=r.reason,
                        reason_code=f"warned_{r.reason_code}",
                        risk_score=r.risk_score,
                    )
                return r

        return GuardrailResult(
            allowed=True, check="All Input Checks",
            reason=_t_or("guardrail.clean", "Clean"),
            reason_code="clean", risk_score=0.0,
        )

    def _check_pii(self, prompt: str) -> GuardrailResult:
        for p in self.policy.get("pii_patterns", []):
            if re.search(p["regex"], prompt):
                return GuardrailResult(
                    allowed=False,
                    check="PII Detection",
                    reason=_t_or("guardrail.pii_detected", "PII detected: {name}", name=p["name"]),
                    reason_code="pii_detected",
                    risk_score=0.85,
                    flagged_content=[p["name"]],
                )
        return GuardrailResult(allowed=True, check="PII Detection")

    def _check_secrets(self, prompt: str) -> GuardrailResult:
        patterns = {
            "openai_api_key":   r"\bsk-[A-Za-z0-9_-]{20,}\b",
            "anthropic_key":    r"\bsk-ant-[A-Za-z0-9_-]{20,}\b",
            "groq_api_key":     r"\bgsk_[A-Za-z0-9_-]{20,}\b",
            "github_token":     r"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}\b",
            "aws_access_key":   r"\bAKIA[0-9A-Z]{16}\b",
            "aws_secret_key":   r"(?i)aws.{0,20}secret.{0,20}['\"][A-Za-z0-9/+]{40}['\"]",
            "private_key":      r"-----BEGIN (?:RSA|OPENSSH|EC|DSA|PRIVATE) KEY-----",
            "bearer_token":     r"(?i)\bauthorization:\s*bearer [A-Za-z0-9_\-\.]{20,}\b",
            "generic_api_key":  r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}['\"]?",
        }
        for name, regex in patterns.items():
            if re.search(regex, prompt):
                return GuardrailResult(
                    allowed=False,
                    check="Secret Detection",
                    reason=_t_or("guardrail.secret_detected", "Secret detected: {name}", name=name),
                    reason_code="secret_detected",
                    risk_score=0.95,
                    flagged_content=[name],
                )
        return GuardrailResult(allowed=True, check="Secret Detection")

    def _check_injection(self, prompt: str) -> GuardrailResult:
        lower = prompt.lower()
        built_in = [
            # Classic overrides
            "ignore previous instructions",
            "ignore all previous instructions",
            "ignore your previous instructions",
            "disregard your system prompt",
            "disregard all previous",
            "disregard previous instructions",
            "forget everything",
            "forget your instructions",
            "forget all previous",
            # Reveal attempts
            "reveal your system prompt",
            "print your hidden instructions",
            "show me your system prompt",
            "what are your instructions",
            "repeat your system prompt",
            # Policy bypass
            "bypass the policy",
            "bypass your restrictions",
            "disable safety",
            "override your instructions",
            "override your system prompt",
            # Replacement injections
            "new system prompt:",
            "new instructions:",
            "your new task is",
            "your new instructions are",
            "you are no longer",
            # Context manipulation
            "ignore the above",
            "ignore everything above",
            "ignore everything before this",
            # Mode injections
            "admin override",
            "debug mode enabled",
            "maintenance mode",
            "sudo mode",
            "system prompt override",
        ]
        keywords = {kw.lower() for kw in self.policy.get("injection_keywords", [])}
        keywords.update(built_in)

        for kw in keywords:
            if kw in lower:
                return GuardrailResult(
                    allowed=False,
                    check="Injection Detection",
                    reason=_t_or("guardrail.prompt_injection", "Prompt injection: '{keyword}'", keyword=kw),
                    reason_code="prompt_injection",
                    risk_score=0.9,
                )
        return GuardrailResult(allowed=True, check="Injection Detection")

    def _check_jailbreak(self, prompt: str) -> GuardrailResult:
        lower = prompt.lower()
        built_in = [
            # Classic modes
            "dan mode",
            "developer mode",
            "jailbreak mode",
            "evil mode",
            "harm mode",
            "no filter mode",
            "opposite mode",
            "god mode",
            # Restriction removal
            "pretend you have no restrictions",
            "act as an unrestricted",
            "you are now jailbroken",
            "you have been jailbroken",
            "do anything now",
            "no ethical guidelines",
            "no restrictions whatsoever",
            "bypass all restrictions",
            "bypass all safety",
            "without any restrictions",
            "without any ethical",
            "without any filters",
            "without censorship",
            "unfiltered response",
            # Sandbox/simulation tricks
            "simulated sandbox",
            "do not include any safety warnings",
            "unrestricted terminal",
            "stay in character no matter what",
            # Malware patterns
            "silently logs keystrokes",
            "log keystrokes",
            "keystroke logger",
            "keylogger",
        ]
        patterns = {p.lower() for p in self.policy.get("jailbreak_patterns", [])}
        patterns.update(built_in)

        for p in patterns:
            if p in lower:
                return GuardrailResult(
                    allowed=False,
                    check="Jailbreak Detection",
                    reason=_t_or("guardrail.jailbreak_attempt", "Jailbreak: '{pattern}'", pattern=p),
                    reason_code="jailbreak_attempt",
                    risk_score=0.9,
                )
        return GuardrailResult(allowed=True, check="Jailbreak Detection")

    def _check_semantic(self, prompt: str) -> GuardrailResult:
        try:
            from app.services.vectorstore import find_similar_blocked
            blocked = self.policy.get("semantic_blocked_texts", [])
            if not blocked:
                return GuardrailResult(allowed=True, check="Semantic Detection")
            blocked_found, score, matched = find_similar_blocked(
                blocked, prompt, threshold=self.policy.get("semantic_threshold", 0.82)
            )
            if blocked_found:
                return GuardrailResult(
                    allowed=False,
                    check="Semantic Detection",
                    reason=_t_or("guardrail.semantic_blocked", "Semantically similar to blocked content (score={score:.2f})", score=score),
                    reason_code="semantic_blocked",
                    risk_score=score,
                )
            return GuardrailResult(allowed=True, check="Semantic Detection")
        except Exception:
            return GuardrailResult(allowed=True, check="Semantic Detection")
