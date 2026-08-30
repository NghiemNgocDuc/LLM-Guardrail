"""
Input Guardrails — 2026 control-plane: tiered, sampled, 4-way (block/redact/warn/review)
"""
import random
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from app.i18n import _t_or
from guardrails import _engine


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
    def __init__(self, policy: dict, custom_rule_rego: str | None = None, org_id: str | None = None):
        self.policy = policy
        # Org-authored OPA/Rego custom rule (OrgPolicy.custom_rule_rego) — the
        # FINAL gate. When configured, the standard checks below run only to
        # feed their findings to the rule (the org admin has explicitly taken
        # over gating), and the rule's verdict wins. When no rule is
        # configured, behaviour is byte-for-byte the original short-circuit
        # flow.
        self.custom_rule_rego = custom_rule_rego or ""
        self.org_id = org_id or "default"

    def check(self, prompt: str) -> GuardrailResult:
        script = self.custom_rule_rego
        findings: list[dict] = []

        def record(r: GuardrailResult) -> None:
            findings.append({
                "check": r.check,
                "reason_code": r.reason_code,
                "matched": not r.allowed,
            })

        if self.policy.get("block_secrets", True):
            r = self._check_secrets(prompt)
            record(r)
            if not r.allowed and not script:
                return r
            # Env-exfiltration probes (e.g. "what is GROQ_API_KEY?", "print env")
            # must be blocked even if no literal gsk_ value is present.
            r2 = self._check_env_exfiltration(prompt)
            record(r2)
            if not r2.allowed and not script:
                return r2

        if self.policy.get("block_pii"):
            r = self._check_pii(prompt)
            record(r)
            if not r.allowed and not script:
                return r

        if self.policy.get("block_prompt_injection"):
            r = self._check_injection(prompt)
            record(r)
            if not r.allowed and not script:
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
            record(r)
            if not r.allowed and not script:
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
            record(r)
            if not r.allowed and not script:
                mode = self.policy.get("semantic_mode", "block")
                if mode == "warn":
                    return GuardrailResult(
                        allowed=True, warned=True,
                        check=r.check, reason=r.reason,
                        reason_code=f"warned_{r.reason_code}",
                        risk_score=r.risk_score,
                    )
                return r

        if script:
            return self._check_rego_custom_rule(prompt, script, findings)

        return GuardrailResult(
            allowed=True, check="All Input Checks",
            reason=_t_or("guardrail.clean", "Clean"),
            reason_code="clean", risk_score=0.0,
        )

    def _check_rego_custom_rule(
        self, prompt: str, rego: str, findings: list[dict]
    ) -> GuardrailResult:
        """Run the org's custom Rego rule (`OrgPolicy.custom_rule_rego`) in
        the OPA sidecar (guardrails/opa.py). The rule sees `prompt` plus the
        standard checks' findings and returns `{action, reason}` with action
        in block|warn|pass.

        Fail-closed: ANY failure — OPA unreachable, request timeout, HTTP
        error, or a malformed/missing decision — blocks the request with the
        error text as the reason. A broken rule must never silently skip.
        """
        from guardrails import opa

        # Tier 1 (internal draft) defaults to fail-open per 2026 tiering, Tier 3 fail-closed
        tier = self.policy.get("tier") or self.policy.get("opa_tier") or 2
        fail_mode = self.policy.get("opa_fail_mode") or self.policy.get("fail_mode") or ("open" if tier == 1 else "closed")
        try:
            action, reason = opa.evaluate(
                rego,
                org_id=self.org_id,
                prompt=prompt,
                findings=[
                    {"check": f["check"], "reason_code": f["reason_code"], "matched": f["matched"]}
                    for f in findings
                ],
            )
        except (opa.OPAUnavailableError, opa.OPAValidationError) as e:
            if fail_mode == "open":
                return GuardrailResult(
                    allowed=True, warned=True, check="OPA Custom Rule",
                    reason=f"OPA unavailable but tier {tier} fail-open: {e}", reason_code="warned_rego_rule_error", risk_score=0.5,
                )
            return GuardrailResult(
                allowed=False, check="OPA Custom Rule",
                reason=str(e), reason_code="rego_rule_error", risk_score=1.0,
            )
        if action == "block":
            return GuardrailResult(
                allowed=False, check="OPA Custom Rule", reason=reason,
                reason_code="rego_custom_rule", risk_score=1.0,
            )
        if action == "warn":
            return GuardrailResult(
                allowed=True, warned=True, check="OPA Custom Rule", reason=reason,
                reason_code="warned_rego_custom_rule", risk_score=0.5,
            )
        return GuardrailResult(allowed=True, check="OPA Custom Rule")

    def _check_pii(self, prompt: str) -> GuardrailResult:
        mode = self.policy.get("pii_mode") or self.policy.get("pii_redaction_mode") or "block"
        # logs_only / reversible: allow but flag for scrubbed logging (Bifrost pattern)
        is_logs_only = mode in ("logs_only", "reversible", "warn")
        if _engine.enabled():
            try:
                name = _engine.module().check_pii(
                    prompt, [(p["name"], p["regex"]) for p in self.policy.get("pii_patterns", [])]
                )
                if name is not None:
                    if is_logs_only:
                        return GuardrailResult(
                            allowed=True, warned=True,
                            check="PII Detection",
                            reason=_t_or("guardrail.pii_detected", "PII detected: {name}", name=name),
                            reason_code="warned_pii_detected",
                            risk_score=0.5,
                            flagged_content=[name],
                        )
                    return GuardrailResult(
                        allowed=False,
                        check="PII Detection",
                        reason=_t_or("guardrail.pii_detected", "PII detected: {name}", name=name),
                        reason_code="pii_detected",
                        risk_score=0.85,
                        flagged_content=[name],
                    )
                return GuardrailResult(allowed=True, check="PII Detection")
            except Exception:
                pass  # fall through to the Python implementation
        for p in self.policy.get("pii_patterns", []):
            if re.search(p["regex"], prompt):
                if is_logs_only:
                    return GuardrailResult(
                        allowed=True, warned=True,
                        check="PII Detection",
                        reason=_t_or("guardrail.pii_detected", "PII detected: {name}", name=p["name"]),
                        reason_code="warned_pii_detected",
                        risk_score=0.5,
                        flagged_content=[p["name"]],
                    )
                return GuardrailResult(
                    allowed=False,
                    check="PII Detection",
                    reason=_t_or("guardrail.pii_detected", "PII detected: {name}", name=p["name"]),
                    reason_code="pii_detected",
                    risk_score=0.85,
                    flagged_content=[p["name"]],
                )
        # Phase 2 fallback: heuristic NER for person names (wl1) if regex found nothing
        try:
            from guardrails.pii_redactor import PIIRedactor
            rr = PIIRedactor().redact(prompt)
            if rr.pii_found:
                if is_logs_only:
                    return GuardrailResult(allowed=True, warned=True, check="PII Detection", reason=_t_or("guardrail.pii_detected", "PII detected: {name}", name=",".join(rr.pii_types)), reason_code="warned_pii_detected", risk_score=0.5, flagged_content=rr.pii_types)
                return GuardrailResult(allowed=False, check="PII Detection", reason=_t_or("guardrail.pii_detected", "PII detected: {name}", name=",".join(rr.pii_types)), reason_code="pii_detected", risk_score=0.85, flagged_content=rr.pii_types)
        except Exception:
            pass
        return GuardrailResult(allowed=True, check="PII Detection")

    def _check_secrets(self, prompt: str) -> GuardrailResult:
        if _engine.enabled():
            try:
                name = _engine.module().check_secret(prompt)
                if name is not None:
                    return GuardrailResult(
                        allowed=False,
                        check="Secret Detection",
                        reason=_t_or("guardrail.secret_detected", "Secret detected: {name}", name=name),
                        reason_code="secret_detected",
                        risk_score=0.95,
                        flagged_content=[name],
                    )
                return GuardrailResult(allowed=True, check="Secret Detection")
            except Exception:
                pass  # fall through to the Python implementation
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

    def _check_env_exfiltration(self, prompt: str) -> GuardrailResult:
        from app.utils.secret_redaction import contains_env_exfiltration  # lazy

        hit, _ = contains_env_exfiltration(prompt)
        if hit:
            return GuardrailResult(
                allowed=False,
                check="Env Exfiltration Probe",
                reason=_t_or("guardrail.env_exfiltration", "Request appears to probe for secrets or environment variables"),
                reason_code="env_exfiltration_probe",
                risk_score=0.95,
                flagged_content=["env_probe"],
            )
        return GuardrailResult(allowed=True, check="Env Exfiltration Probe")

    def _check_injection(self, prompt: str) -> GuardrailResult:
        if _engine.enabled():
            try:
                kw = _engine.module().check_injection(
                    prompt, list(self.policy.get("injection_keywords", []))
                )
                if kw is not None:
                    return GuardrailResult(
                        allowed=False,
                        check="Injection Detection",
                        reason=_t_or("guardrail.prompt_injection", "Prompt injection: '{keyword}'", keyword=kw),
                        reason_code="prompt_injection",
                        risk_score=0.9,
                    )
                return GuardrailResult(allowed=True, check="Injection Detection")
            except Exception:
                pass  # fall through to the Python implementation
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
        if _engine.enabled():
            try:
                pat = _engine.module().check_jailbreak(
                    prompt, list(self.policy.get("jailbreak_patterns", []))
                )
                if pat is not None:
                    return GuardrailResult(
                        allowed=False,
                        check="Jailbreak Detection",
                        reason=_t_or("guardrail.jailbreak_attempt", "Jailbreak: '{pattern}'", pattern=pat),
                        reason_code="jailbreak_attempt",
                        risk_score=0.9,
                    )
                return GuardrailResult(allowed=True, check="Jailbreak Detection")
            except Exception:
                pass  # fall through to the Python implementation
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
        # Sampling for high-volume (Bifrost): skip expensive vector check with probability
        sample_rate = self.policy.get("sample_rate") or self.policy.get("semantic_sample_rate")
        if sample_rate is not None:
            try:
                if random.random() > float(sample_rate):
                    return GuardrailResult(allowed=True, check="Semantic Detection", reason="sampled", reason_code="sampled", risk_score=0.0)
            except Exception:
                pass
        try:
            from app.services.vectorstore import find_similar_blocked
            blocked = self.policy.get("semantic_blocked_texts", [])
            if not blocked:
                return GuardrailResult(allowed=True, check="Semantic Detection")
            blocked_found, score, matched = find_similar_blocked(
                blocked, prompt, threshold=self.policy.get("semantic_threshold", 0.82)
            )
            if blocked_found:
                mode = self.policy.get("semantic_mode", "block")
                if mode == "review":
                    return GuardrailResult(
                        allowed=True, warned=True,
                        check="Semantic Detection",
                        reason=_t_or("guardrail.semantic_blocked", "Semantically similar to blocked content (score={score:.2f})", score=score),
                        reason_code="review_semantic_blocked",
                        risk_score=score,
                    )
                if mode == "warn":
                    return GuardrailResult(
                        allowed=True, warned=True,
                        check="Semantic Detection",
                        reason=_t_or("guardrail.semantic_blocked", "Semantically similar to blocked content (score={score:.2f})", score=score),
                        reason_code="warned_semantic_blocked",
                        risk_score=score,
                    )
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
