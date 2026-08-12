"""
MCP (Model Context Protocol) server for the LLM Guardrails Gateway.

Exposes guardrail functionality as MCP tools so AI assistants can:
  - Scan agent skills / instruction files for secrets, PII, and dangerous commands
  - Scan batches of skill files / a whole repo in one call (scan_repo)
  - Explain what a JSON guardrail policy actually does (explain_policy)
  - Check prompts against input guardrails (injection, jailbreak, secrets, PII)
  - Check LLM responses against output guardrails (toxicity, topics, leaks)
  - Route prompts through the full guardrail gateway to any LLM backend
  - Redact PII from text

Uses JSON-RPC over SSE (Server-Sent Events) for MCP transport.
Mounts into the FastAPI app at /mcp.

                === SECURITY ===
  SSE transport requires authentication via X-Api-Key header or
  Authorization: Bearer <grg_key>. All inputs are size-limited.
  The chat tool is restricted to API keys with the "chat" scope.
  Tool calls are audited to the request log.

Standalone stdio mode (local only — no auth):
  python -m app.mcp_server

SSE mode (requires auth):
  The server is available at http://localhost:8080/mcp/sse via the FastAPI app.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from guardrails.input import InputGuardrail
from guardrails.output import OutputGuardrail
from guardrails.pii_redactor import PIIRedactor
from guardrails.skill import SkillGuardrail

logger = logging.getLogger(__name__)

TOOL_REGISTRY: dict[str, dict[str, Any]] = {}

# ─── Constants ────────────────────────────────────────────────────────────────

MAX_CONTENT_CHARS = 256_000
MAX_PROMPT_CHARS = 32_000
MAX_OUTPUT_CHARS = 64_000
MAX_FILENAME_CHARS = 255
MAX_SCAN_FILES = 200
RATE_LIMIT_RPM_DEFAULT = 30
RATE_LIMIT_RPD_DEFAULT = 500
GATEWAY_KEY_PREFIX = "grg_"
SSE_SESSION_TIMEOUT = 300.0

# ─── Default guardrail policy ─────────────────────────────────────────────────

INPUT_RULES: dict = {
    "block_secrets": True,
    "block_pii": True,
    "pii_patterns": [
        {"name": "credit_card", "regex": r"\b(?:\d[ -]?){13,16}\b"},
        {"name": "ssn",         "regex": r"\b\d{3}-\d{2}-\d{4}\b"},
        {"name": "email",       "regex": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"},
    ],
    "block_prompt_injection": True,
    "injection_keywords": [
        "ignore previous instructions", "disregard your system prompt",
        "forget everything", "reveal your system prompt",
        "print your hidden instructions", "bypass the policy", "disable safety",
    ],
    "block_jailbreak": True,
    "jailbreak_patterns": [
        "DAN mode", "developer mode", "pretend you have no restrictions",
        "act as an unrestricted", "you are now jailbroken", "simulated sandbox",
        "do not include any safety warnings", "unrestricted terminal",
        "silently logs keystrokes", "log keystrokes", "keystroke logger", "keylogger",
    ],
}

OUTPUT_RULES: dict = {"enforce_schema": False, "block_toxic_content": True, "required_fields": []}
TOPIC_POLICY: dict = {"blocked_topics": ["competitor products", "medical advice"]}
COMPLIANCE: dict = {"block_medical_advice": True, "never_discuss_competitors": True}


# ─── Tool registration ────────────────────────────────────────────────────────

def tool(name: str | None = None, description: str = "", input_schema: dict[str, Any] | None = None):
    def decorator(fn: Callable) -> Callable:
        tool_name = name or fn.__name__
        TOOL_REGISTRY[tool_name] = {
            "name": tool_name,
            "description": description,
            "input_schema": input_schema or _infer_schema(fn),
            "fn": fn,
        }
        return fn
    return decorator


def _infer_schema(fn: Callable) -> dict[str, Any]:
    import inspect
    sig = inspect.signature(fn)
    properties = {}
    required = []
    for param_name, param in sig.parameters.items():
        ann = param.annotation
        js_type = "string"
        if ann is int:
            js_type = "number"
        elif ann is float:
            js_type = "number"
        elif ann is bool:
            js_type = "boolean"
        props: dict[str, Any] = {"type": js_type}
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
        elif param.default is not None:
            props["default"] = param.default
        properties[param_name] = props
    return {"type": "object", "properties": properties, "required": required}


# ─── Input validation ─────────────────────────────────────────────────────────

@dataclass
class ValidationError:
    message: str


def _validate_scan_skill(**kw) -> ValidationError | None:
    content = kw.get("content", "")
    if not content or not content.strip():
        return ValidationError("content must be non-empty")
    if len(content) > MAX_CONTENT_CHARS:
        return ValidationError(f"content exceeds {MAX_CONTENT_CHARS} characters")
    filename = kw.get("filename")
    if filename and len(filename) > MAX_FILENAME_CHARS:
        return ValidationError(f"filename exceeds {MAX_FILENAME_CHARS} characters")
    return None


def _validate_check_input(**kw) -> ValidationError | None:
    prompt = kw.get("prompt", "")
    if not prompt or not prompt.strip():
        return ValidationError("prompt must be non-empty")
    if len(prompt) > MAX_PROMPT_CHARS:
        return ValidationError(f"prompt exceeds {MAX_PROMPT_CHARS} characters")
    policy_json = kw.get("policy_json")
    if policy_json and len(policy_json) > 10_000:
        return ValidationError("policy_json too large")
    return None


def _validate_check_output(**kw) -> ValidationError | None:
    response = kw.get("response", "")
    if not response or not response.strip():
        return ValidationError("response must be non-empty")
    if len(response) > MAX_OUTPUT_CHARS:
        return ValidationError(f"response exceeds {MAX_OUTPUT_CHARS} characters")
    for key in ("policy_json", "topic_policy_json", "compliance_json"):
        val = kw.get(key)
        if val and len(val) > 10_000:
            return ValidationError(f"{key} too large")
    return None


def _validate_chat(**kw) -> ValidationError | None:
    prompt = kw.get("prompt", "")
    if not prompt or not prompt.strip():
        return ValidationError("prompt must be non-empty")
    if len(prompt) > MAX_PROMPT_CHARS:
        return ValidationError(f"prompt exceeds {MAX_PROMPT_CHARS} characters")
    temperature = kw.get("temperature", 0.7)
    if not (0.0 <= temperature <= 2.0):
        return ValidationError("temperature must be between 0.0 and 2.0")
    max_tokens = kw.get("max_tokens", 1024)
    if not (1 <= max_tokens <= 8192):
        return ValidationError("max_tokens must be between 1 and 8192")
    policy_json = kw.get("policy_json")
    if policy_json and len(policy_json) > 10_000:
        return ValidationError("policy_json too large")
    return None


def _validate_redact_pii(**kw) -> ValidationError | None:
    text = kw.get("text", "")
    if not text or not text.strip():
        return ValidationError("text must be non-empty")
    if len(text) > MAX_CONTENT_CHARS:
        return ValidationError(f"text exceeds {MAX_CONTENT_CHARS} characters")
    return None


def _validate_scan_repo(**kw) -> ValidationError | None:
    files_json = kw.get("files_json", "")
    if not files_json or not files_json.strip():
        return ValidationError("files_json must be non-empty")
    try:
        files = json.loads(files_json)
    except json.JSONDecodeError:
        return ValidationError("files_json must be valid JSON")
    if not isinstance(files, list):
        return ValidationError("files_json must be a JSON array of {filename, content} objects")
    if not files:
        return ValidationError("files_json must contain at least one file")
    if len(files) > MAX_SCAN_FILES:
        return ValidationError(f"too many files: {len(files)} exceeds {MAX_SCAN_FILES}")
    for entry in files:
        if not isinstance(entry, dict):
            return ValidationError("each file entry must be an object with filename and content")
        filename = entry.get("filename")
        content = entry.get("content")
        if not isinstance(filename, str) or not filename.strip():
            return ValidationError("each file entry must have a non-empty filename")
        if len(filename) > MAX_FILENAME_CHARS:
            return ValidationError(f"filename exceeds {MAX_FILENAME_CHARS} characters")
        if not isinstance(content, str) or not content.strip():
            return ValidationError("each file entry must have non-empty content")
        if len(content) > MAX_CONTENT_CHARS:
            return ValidationError("content exceeds " + str(MAX_CONTENT_CHARS) + " characters")
    return None


def _validate_explain_policy(**kw) -> ValidationError | None:
    policy_json = kw.get("policy_json", "")
    if not policy_json or not policy_json.strip():
        return ValidationError("policy_json must be non-empty")
    if len(policy_json) > 10_000:
        return ValidationError("policy_json too large")
    try:
        policy = json.loads(policy_json)
    except json.JSONDecodeError:
        return ValidationError("policy_json must be valid JSON")
    if not isinstance(policy, dict):
        return ValidationError("policy_json must be a JSON object")
    return None


_VALIDATORS: dict[str, Callable[..., ValidationError | None]] = {
    "scan_skill": _validate_scan_skill,
    "scan_repo": _validate_scan_repo,
    "check_input": _validate_check_input,
    "check_output": _validate_check_output,
    "chat": _validate_chat,
    "redact_pii": _validate_redact_pii,
    "explain_policy": _validate_explain_policy,
}


def _validate_tool_call(name: str, args: dict[str, Any]) -> ValidationError | None:
    validator = _VALIDATORS.get(name)
    if validator:
        return validator(**args)
    return None


# ─── Rate limiter (in-memory fallback, Redis-backed when available) ──────────

@dataclass
class RateLimitState:
    rpm_remaining: int = RATE_LIMIT_RPM_DEFAULT
    rpd_remaining: int = RATE_LIMIT_RPD_DEFAULT
    rpm_reset: float = 0.0
    rpd_reset: float = 0.0


_rate_limits: dict[str, RateLimitState] = {}
_rpm_window = 60.0
_rpd_window = 86400.0


def _check_rate_limit_local(key_id: str, rpm: int, rpd: int) -> RateLimitState:
    now = time.time()
    state = _rate_limits.get(key_id)
    if state is None:
        state = RateLimitState(rpm_remaining=rpm, rpd_remaining=rpd)
        _rate_limits[key_id] = state

    if now >= state.rpm_reset:
        state.rpm_remaining = rpm
        state.rpm_reset = now + _rpm_window
    if now >= state.rpd_reset:
        state.rpd_remaining = rpd
        state.rpd_reset = now + _rpd_window

    state.rpm_remaining -= 1
    state.rpd_remaining -= 1

    return state


# ─── Auth context ─────────────────────────────────────────────────────────────

@dataclass
class MCPAuthContext:
    key_id: str
    owner_id: str
    org_id: str | None
    scopes: list[str] = field(default_factory=lambda: ["chat"])
    rpm: int = RATE_LIMIT_RPM_DEFAULT
    rpd: int = RATE_LIMIT_RPD_DEFAULT
    is_authenticated: bool = False


_UNAUTHENTICATED = MCPAuthContext(
    key_id="", owner_id="", org_id=None, is_authenticated=False
)

# ─── Tools ────────────────────────────────────────────────────────────────────

def _finding_dict(f) -> dict[str, Any]:
    return {
        "category": f.category,
        "severity": f.severity,
        "check": f.check,
        "reason": f.reason,
        "reason_code": f.reason_code,
        "line_number": f.line_number,
        "snippet": f.snippet,
        "risk_score": f.risk_score,
    }


@tool(
    name="scan_skill",
    description=(
        "Scan agent skill / instruction content for secrets (API keys, tokens, "
        "database URLs), PII (emails, SSNs, credit cards), and destructive commands "
        "(rm -rf, DROP TABLE, disk wipe, pipe-to-shell, etc.). Returns findings with "
        "severity, line numbers, and risk scores. Use before publishing any Cursor "
        "skill, MCP rule, system prompt, or agent instruction file."
    ),
)
def scan_skill(content: str, filename: str | None = None) -> str:
    result = SkillGuardrail().scan(content)
    return json.dumps({
        "safe": result.safe,
        "risk_score": result.risk_score,
        "findings": [_finding_dict(f) for f in result.findings],
        "line_count": result.line_count,
        "char_count": result.char_count,
        "filename": filename,
    })


@tool(
    name="scan_repo",
    description=(
        "Scan a batch of agent skill / instruction files (e.g. a repo checkout) "
        "for secrets (API keys, tokens, database URLs), PII (emails, SSNs, credit "
        "cards), and destructive commands (rm -rf, DROP TABLE, disk wipe, "
        "pipe-to-shell, etc.). Accepts a JSON array of {\"filename\", \"content\"} "
        "objects, so it works both for local callers who already read files off "
        "disk and for remote MCP clients without filesystem access to the server. "
        "Returns per-file results plus an aggregate summary (files scanned, files "
        "with findings, findings by severity, overall risk score)."
    ),
)
def scan_repo(files_json: str) -> str:
    files = json.loads(files_json)
    results = []
    files_with_findings = 0
    overall_risk_score = 0.0
    by_severity = {"critical": 0, "high": 0, "medium": 0}
    for entry in files:
        result = SkillGuardrail().scan(entry["content"])
        results.append({
            "filename": entry["filename"],
            "safe": result.safe,
            "risk_score": result.risk_score,
            "findings": [_finding_dict(f) for f in result.findings],
            "line_count": result.line_count,
            "char_count": result.char_count,
        })
        if not result.safe:
            files_with_findings += 1
        overall_risk_score = max(overall_risk_score, result.risk_score)
        for f in result.findings:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
    return json.dumps({
        "results": results,
        "summary": {
            "files_scanned": len(files),
            "files_with_findings": files_with_findings,
            "findings_by_severity": by_severity,
            "overall_risk_score": overall_risk_score,
        },
    })


@tool(
    name="check_input",
    description=(
        "Check a prompt or user input against input guardrails. Detects secrets "
        "(API keys, tokens), PII (emails, SSNs, credit cards), prompt injection "
        "attempts ('ignore previous instructions', 'reveal system prompt'), and "
        "jailbreak patterns ('DAN mode', 'pretend you have no restrictions'). "
        "Use before sending a prompt to any LLM."
    ),
)
def check_input(prompt: str, policy_json: str | None = None) -> str:
    policy = dict(INPUT_RULES)
    if policy_json:
        try:
            policy.update(json.loads(policy_json))
        except json.JSONDecodeError:
            pass
    guard = InputGuardrail(policy)
    result = guard.check(prompt)
    return json.dumps({
        "allowed": result.allowed,
        "check": result.check,
        "reason": result.reason,
        "reason_code": result.reason_code,
        "risk_score": result.risk_score,
        "warned": result.warned,
    })


@tool(
    name="check_output",
    description=(
        "Check an LLM response against output guardrails. Detects credential "
        "leakage, toxic content, blocked topics, and schema violations. Use "
        "before returning an LLM response to the user."
    ),
)
def check_output(
    response: str,
    policy_json: str | None = None,
    topic_policy_json: str | None = None,
    compliance_json: str | None = None,
) -> str:
    output_rules = dict(OUTPUT_RULES)
    if policy_json:
        try:
            output_rules.update(json.loads(policy_json))
        except json.JSONDecodeError:
            pass
    topic_policy = dict(TOPIC_POLICY)
    if topic_policy_json:
        try:
            topic_policy.update(json.loads(topic_policy_json))
        except json.JSONDecodeError:
            pass
    compliance = dict(COMPLIANCE)
    if compliance_json:
        try:
            compliance.update(json.loads(compliance_json))
        except json.JSONDecodeError:
            pass
    guard = OutputGuardrail(output_rules, compliance, topic_policy)
    result = guard.check(response)
    return json.dumps({
        "allowed": result.allowed,
        "check": result.check,
        "reason": result.reason,
        "reason_code": result.reason_code,
        "risk_score": result.risk_score,
        "warned": result.warned,
    })


@tool(
    name="chat",
    description=(
        "Send a prompt through the full guardrail gateway to an LLM backend. "
        "The prompt is checked against input guardrails (secrets, PII, injection, "
        "jailbreak), sent to the configured LLM provider, then the response is "
        "checked against output guardrails (toxicity, topic policy, credential "
        "leakage). Supports Groq, OpenAI, Anthropic, Gemini, Ollama, and "
        "OpenAI-compatible backends. Requires an API key with the 'chat' scope."
    ),
)
async def chat(
    prompt: str,
    backend: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    policy_json: str | None = None,
) -> str:
    from app.services.llm import call_llm

    policy = dict(INPUT_RULES)
    if policy_json:
        try:
            policy.update(json.loads(policy_json))
        except json.JSONDecodeError:
            pass

    in_guard = InputGuardrail(policy)
    in_result = in_guard.check(prompt)

    if not in_result.allowed:
        return json.dumps({
            "status": "input_blocked",
            "response": None,
            "input_guard": {
                "passed": False, "check": in_result.check,
                "reason": in_result.reason, "reason_code": in_result.reason_code,
                "risk_score": in_result.risk_score,
            },
            "output_guard": None, "model": None, "backend": None,
        })

    try:
        llm_resp = await call_llm(
            prompt=prompt, temperature=temperature, max_tokens=max_tokens,
            request_backend=backend, org_backend=None,
            request_model=model, org_model=None,
        )
    except Exception as e:
        return json.dumps({
            "status": "error", "response": None, "error": str(e),
            "input_guard": {
                "passed": True, "check": in_result.check,
                "reason": in_result.reason or "", "reason_code": in_result.reason_code,
                "risk_score": in_result.risk_score,
            },
            "output_guard": None, "model": None, "backend": None,
        })

    out_guard = OutputGuardrail(OUTPUT_RULES, COMPLIANCE, TOPIC_POLICY)
    out_result = out_guard.check(llm_resp.text)
    status = "delivered" if out_result.allowed else "output_blocked"

    return json.dumps({
        "status": status,
        "response": llm_resp.text if out_result.allowed else None,
        "input_guard": {
            "passed": True, "check": in_result.check,
            "reason": in_result.reason or "", "reason_code": in_result.reason_code,
            "risk_score": in_result.risk_score,
        },
        "output_guard": {
            "passed": out_result.allowed, "check": out_result.check,
            "reason": out_result.reason or "", "reason_code": out_result.reason_code,
            "risk_score": out_result.risk_score,
        },
        "model": llm_resp.model, "backend": llm_resp.backend,
        "input_tokens": llm_resp.input_tokens, "output_tokens": llm_resp.output_tokens,
    })


@tool(
    name="redact_pii",
    description=(
        "Detect and redact PII (emails, SSNs, credit card numbers, phone numbers, "
        "IP addresses) from text, replacing them with reversible placeholders. "
        "Returns both the redacted text and the mapping to restore originals."
    ),
)
def redact_pii(text: str) -> str:
    redactor = PIIRedactor()
    result = redactor.redact(text)
    return json.dumps({
        "redacted_text": result.redacted_text,
        "pii_found": result.pii_found,
        "pii_count": result.pii_count,
        "pii_types": result.pii_types,
        "mapping": result.mapping,
    })


@tool(
    name="get_default_policy",
    description=(
        "Return the default guardrail policy configuration. Shows the default "
        "input rules (secrets, PII, injection, jailbreak), output rules "
        "(toxicity, schema), topic policy, and compliance rules. Use to "
        "understand what the gateway checks before customizing."
    ),
)
def get_default_policy() -> str:
    return json.dumps({
        "input_rules": INPUT_RULES,
        "output_rules": OUTPUT_RULES,
        "topic_policy": TOPIC_POLICY,
        "compliance_rules": COMPLIANCE,
        "available_backends": [
            "groq", "openai", "anthropic", "gemini", "ollama",
            "openai_compatible", "mock",
        ],
    })


@tool(
    name="explain_policy",
    description=(
        "Explain what a JSON guardrail policy actually does in plain English. "
        "Accepts a JSON policy matching the shape get_default_policy returns "
        "(input_rules, output_rules, topic_policy, compliance_rules) and returns "
        "a bullet list of the checks that would run, derived only from the fields "
        "InputGuardrail and OutputGuardrail read. Pure formatting — no LLM call "
        "and no database access. Use to inspect a policy before applying it."
    ),
)
def explain_policy(policy_json: str) -> str:
    policy = json.loads(policy_json)
    input_rules = dict(policy.get("input_rules") or {})
    output_rules = dict(policy.get("output_rules") or {})
    topic_policy = dict(policy.get("topic_policy") or {})
    compliance = dict(policy.get("compliance_rules") or {})

    bullets = []

    # Input checks — same fields InputGuardrail.check reads (guardrails/input.py)
    if input_rules.get("block_secrets", True):
        bullets.append("Input: blocks prompts containing secrets (API keys, tokens, private keys)")
    else:
        bullets.append("Input: secret detection is disabled")

    if input_rules.get("block_pii"):
        patterns = [
            p["name"]
            for p in (input_rules.get("pii_patterns") or [])
            if isinstance(p, dict) and p.get("name")
        ]
        names = ", ".join(patterns) if patterns else "email, SSN, credit card"
        bullets.append(f"Input: blocks prompts containing PII ({names})")
    else:
        bullets.append("Input: PII detection is disabled")

    if input_rules.get("block_prompt_injection"):
        mode = input_rules.get("injection_mode", "block")
        action = "warns instead of blocking" if mode == "warn" else "blocks"
        extra = len([k for k in (input_rules.get("injection_keywords") or []) if k])
        suffix = f" plus {extra} custom keyword(s)" if extra else ""
        bullets.append(f"Input: {action} prompt injection attempts after built-in keywords{suffix}")
    else:
        bullets.append("Input: prompt-injection detection is disabled")

    if input_rules.get("block_jailbreak"):
        mode = input_rules.get("jailbreak_mode", "block")
        action = "warns instead of blocking" if mode == "warn" else "blocks"
        extra = len([p for p in (input_rules.get("jailbreak_patterns") or []) if p])
        suffix = f" plus {extra} custom pattern(s)" if extra else ""
        bullets.append(f"Input: {action} jailbreak attempts after built-in patterns{suffix}")
    else:
        bullets.append("Input: jailbreak detection is disabled")

    semantic_mode = input_rules.get("semantic_mode")
    if semantic_mode in ("block", "warn"):
        blocked = [t for t in (input_rules.get("semantic_blocked_texts") or []) if t]
        threshold = input_rules.get("semantic_threshold", 0.82)
        bullets.append(
            f"Input: semantic similarity {semantic_mode} is enabled for {len(blocked)} "
            f"blocked phrase(s) at threshold {threshold}"
        )
    else:
        bullets.append("Input: semantic similarity blocking is disabled")

    if input_rules.get("custom_rule_rego"):
        bullets.append(
            "Input: runs an org-defined Rego custom rule (custom_rule_rego) in the "
            "OPA sidecar that is the FINAL gate: when configured, the standard checks "
            "below run only to feed their findings to the rule, which then blocks, "
            "warns, or passes. Fails closed (blocks) if OPA is unreachable, the "
            "request times out, or the decision is malformed."
        )
    else:
        bullets.append("Input: no custom Rego rule configured")

    # Output checks — same fields OutputGuardrail.check reads (guardrails/output.py).
    # Secret leakage is unconditional there and always runs, regardless of policy.
    bullets.append("Output: credential leakage in responses always blocks (cannot be disabled)")

    if output_rules.get("enforce_schema"):
        required = [f for f in (output_rules.get("required_fields") or []) if f]
        if required:
            bullets.append(f"Output: responses must be valid JSON with required fields: {', '.join(required)}")
        else:
            bullets.append("Output: responses must be valid JSON (no required fields listed)")
    else:
        bullets.append("Output: JSON schema enforcement is disabled")

    if output_rules.get("block_toxic_content"):
        mode = output_rules.get("toxic_mode", "block")
        action = "warns instead of blocking" if mode == "warn" else "blocks"
        bullets.append(f"Output: {action} toxic content")
    else:
        bullets.append("Output: toxic-content filtering is disabled")

    blocked_topics = [t for t in (topic_policy.get("blocked_topics") or []) if t]
    if blocked_topics:
        bullets.append(f"Output: blocks responses covering topics: {', '.join(blocked_topics)}")

    if compliance.get("block_medical_advice"):
        bullets.append("Output: blocks medical-advice statements (dosage, prescription, diagnosis)")

    return json.dumps({"summary": "\n".join(bullets)})


# ─── MCP Protocol handler (JSON-RPC) ─────────────────────────────────────────

def _list_tools() -> list[dict]:
    return [
        {"name": t["name"], "description": t["description"], "inputSchema": t["input_schema"]}
        for t in TOOL_REGISTRY.values()
    ]


async def _call_tool(name: str, arguments: dict[str, Any]) -> dict:
    tool_def = TOOL_REGISTRY.get(name)
    if not tool_def:
        return _tool_error(f"Tool not found: {name}")

    err = _validate_tool_call(name, arguments)
    if err:
        logger.warning("tool input validation failed: %s args=%s", err.message, name)
        return _tool_error(err.message)

    fn = tool_def["fn"]
    try:
        result = fn(**arguments)
        if asyncio.iscoroutine(result):
            result = await result
        return {"content": [{"type": "text", "text": str(result)}], "isError": False}
    except Exception as e:
        logger.exception("Tool call failed: %s", name)
        return _tool_error(str(e))


def _tool_error(msg: str) -> dict:
    return {"content": [{"type": "text", "text": json.dumps({"error": msg})}], "isError": True}


async def _handle_request(body: dict) -> dict | None:
    method = body.get("method", "")
    params = body.get("params", {}) or {}
    req_id = body.get("id")

    if method == "tools/list":
        resp = {"tools": _list_tools()}
    elif method == "tools/call":
        resp = await _call_tool(params.get("name", ""), params.get("arguments", {}))
    elif method == "initialize":
        resp = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "LLM Guardrails Gateway", "version": "1.0.0"},
        }
    elif method in ("notifications/initialized", "notifications/cancelled"):
        return None
    elif method == "ping":
        resp = {}
    else:
        err = {"code": -32601, "message": f"Method not found: {method}"}
        if req_id is None:
            return None
        return {"jsonrpc": "2.0", "id": req_id, "error": err}

    if req_id is None:
        return None
    return {"jsonrpc": "2.0", "id": req_id, "result": resp}


# ─── Auth for SSE transport ───────────────────────────────────────────────────

async def _resolve_sse_auth(request) -> MCPAuthContext | None:
    raw_key = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        raw_key = auth_header[len("Bearer "):].strip()
    if not raw_key:
        raw_key = request.headers.get("X-Api-Key", "").strip()
    if not raw_key:
        return None

    try:
        from app.deps import resolve_api_key
        from app.database import get_sessionmaker

        if not raw_key.startswith(GATEWAY_KEY_PREFIX):
            return None

        sessionmaker = get_sessionmaker()
        async with sessionmaker() as db:
            key = await resolve_api_key(raw_key, db)
            scopes = list(key.scopes) if key.scopes else ["chat"]
            return MCPAuthContext(
                key_id=key.id,
                owner_id=key.owner_id,
                org_id=key.org_id,
                scopes=scopes,
                is_authenticated=True,
            )
    except Exception:
        logger.warning("SSE auth failed for key prefix %s", raw_key[:12] if len(raw_key) > 12 else raw_key)
        return None


def _scope_allows(auth: MCPAuthContext, required_scope: str) -> bool:
    if not auth.is_authenticated:
        return False
    return required_scope in auth.scopes


async def _audit_log(auth: MCPAuthContext, tool_name: str, args: dict, status: str) -> None:
    if not auth.is_authenticated:
        return
    try:
        from app.database import get_sessionmaker
        from app.models import RequestLog
        import hashlib

        prompt_str = ""
        if isinstance(args.get("prompt"), str):
            prompt_str = args["prompt"]
        elif isinstance(args.get("content"), str):
            prompt_str = args["content"]
        elif isinstance(args.get("text"), str):
            prompt_str = args["text"]
        elif tool_name == "scan_repo" and isinstance(args.get("files_json"), str):
            prompt_str = args["files_json"]
        elif tool_name == "explain_policy" and isinstance(args.get("policy_json"), str):
            prompt_str = args["policy_json"]

        sessionmaker = get_sessionmaker()
        async with sessionmaker() as db:
            log = RequestLog(
                api_key_id=auth.key_id,
                org_id=auth.org_id,
                prompt_hash=hashlib.sha256(prompt_str.encode()).hexdigest(),
                prompt_preview=prompt_str[:120],
                model="mcp:" + tool_name,
                backend="mcp",
                input_passed=status in ("ok", "delivered"),
                input_block_reason=None,
                output_passed=True if status == "delivered" else (None if status in ("input_blocked", "error") else False),
                output_block_reason=None if status in ("ok", "delivered") else status,
                fired_rule=status if status not in ("ok", "delivered") else None,
                status=status,
                latency_ms=0,
                input_tokens=0,
                output_tokens=0,
            )
            db.add(log)
            await db.commit()
    except Exception:
        logger.exception("audit log failed")


# ─── SSE transport (mounted into FastAPI at /mcp) ────────────────────────────

async def _sse_listener(request, session_id: str, queue: asyncio.Queue):
    try:
        while True:
            await asyncio.sleep(30)
            if await request.is_disconnected():
                break
    except asyncio.CancelledError:
        pass


def get_mcp_app():
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse, Response, StreamingResponse
    from starlette.routing import Route

    async def sse_ep(request):
        auth = await _resolve_sse_auth(request)
        if not auth:
            return JSONResponse(
                {"error": "Authentication required. Provide X-Api-Key or Authorization: Bearer <grg_key>"},
                status_code=401,
            )

        session_id = str(uuid.uuid4())

        async def event_generator():
            try:
                yield f"event: endpoint\ndata: /mcp/message?session_id={session_id}\n\n"
                while True:
                    msg = await asyncio.wait_for(queue.get(), timeout=SSE_SESSION_TIMEOUT)
                    yield f"data: {json.dumps(msg)}\n\n"
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                pass

        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_sse_listener(request, session_id, queue))
            return StreamingResponse(event_generator(), media_type="text/event-stream")

    async def msg_ep(request):
        auth = await _resolve_sse_auth(request)
        if not auth:
            return JSONResponse(
                {"error": "Authentication required. Provide X-Api-Key or Authorization: Bearer <grg_key>"},
                status_code=401,
            )

        try:
            raw = await request.body()
            if len(raw) > 512_000:
                return JSONResponse({"error": "Request too large"}, status_code=413)
            body = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        method = body.get("method", "")
        is_call = method == "tools/call"

        if is_call:
            tool_name = body.get("params", {}).get("name", "")
            if tool_name == "chat" and not _scope_allows(auth, "chat"):
                return JSONResponse(
                    {"error": "API key does not have the 'chat' scope required for this tool"},
                    status_code=403,
                )

            # Rate limit per key
            state = _check_rate_limit_local(auth.key_id, auth.rpm, auth.rpd)
            if state.rpm_remaining < 0:
                return JSONResponse({"error": "Rate limit exceeded (RPM)"}, status_code=429)
            if state.rpd_remaining < 0:
                return JSONResponse({"error": "Rate limit exceeded (RPD)"}, status_code=429)

            args = body.get("params", {}).get("arguments", {})
            status = "ok"
            try:
                result = await _handle_request(body)
            except Exception:
                status = "error"
                raise
            finally:
                asyncio.ensure_future(_audit_log(auth, tool_name, args, status))

            if result is not None:
                return JSONResponse(result)
            return Response(status_code=202)

        result = await _handle_request(body)
        if result is not None:
            return JSONResponse(result)
        return Response(status_code=202)

    return Starlette(routes=[
        Route("/sse", endpoint=sse_ep, methods=["GET"]),
        Route("/message", endpoint=msg_ep, methods=["POST"]),
    ])


# ─── Standalone stdio mode (no auth — local only) ───────────────────────────

async def _stdio_handler():
    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        try:
            body = json.loads(line.strip())
            result = await _handle_request(body)
            if result is not None:
                sys.stdout.write(json.dumps(result) + "\n")
                sys.stdout.flush()
        except (json.JSONDecodeError, Exception) as e:
            logger.error("stdio handler error: %s", e)


def run_stdio():
    asyncio.run(_stdio_handler())


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if mode == "sse":
        import uvicorn
        uvicorn.run(get_mcp_app(), host="0.0.0.0", port=8900, log_level="info")
    else:
        run_stdio()
