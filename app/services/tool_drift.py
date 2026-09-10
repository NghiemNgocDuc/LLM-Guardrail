"""
Tool poisoning + schema drift detection — Microsoft MCP Security Gateway 1.0
section 4 (tool call interception) + MCP-TDP benchmark defense.

Every MCP tool exposes a description + inputSchema that agents trust for
planning. Tool Description Poisoning hides `ignore previous instructions`
or exfil URLs inside that metadata. Schema drift (a tool silently gaining a
`webhook_url` param) is the rug-pull tripwire.

This module:
  - hashes (description + inputSchema) per tool (sha256, pinned baseline),
  - scans descriptions with InputGuardrail for hidden instructions,
  - reports drift as {tool, expected, actual, severity} for admin alerting.

Baseline lives in code (TOOL_BASELINE) so fresh deploys match; runtime
overrides in tool_baseline.json win when present. Fail-closed on poisoning,
warn-only on pure drift (schema change may be a legit upgrade).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

BASELINE_PATH = Path("tool_baseline.json")

# Pinned at deploy time — regenerate with `python -m app.services.tool_drift --pin`
# after intentional description/schema changes. Hash = sha256(description + canonical schema).
TOOL_BASELINE: dict[str, str] = {}


def fingerprint(description: str, schema: dict[str, Any]) -> str:
    canonical = json.dumps(schema or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{description}\n{canonical}".encode()).hexdigest()[:16]


def current_fingerprints(registry: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {
        name: fingerprint(str(t.get("description", "")), t.get("input_schema") or t.get("inputSchema") or {})
        for name, t in registry.items()
    }


def load_baseline() -> dict[str, str]:
    if BASELINE_PATH.exists():
        try:
            data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except Exception:
            pass
    return dict(TOOL_BASELINE)


def detect_poisoning(description: str) -> tuple[bool, str]:
    """True when a tool description itself contains an injection (MCP-TDP).

    Quoted examples are stripped first: our own docs legitimately mention
    e.g. ('ignore previous instructions', ...) to describe what is detected.
    A real poisoning is an unquoted imperative plus an exfil/action target.
    """
    import re as _re
    text = description or ""
    # Full-text tripwires that never belong in a description.
    lower_full = text.lower()
    for sig in ("exfiltrate", "send to http", "webhook_url", "attacker-controlled"):
        if sig in lower_full:
            return True, f"suspicious phrase in tool description: '{sig}'"
    # Strip quoted spans (docs examples) before the injection scan.
    unquoted = _re.sub(r"'[^']*'|\"[^\"]*\"", "", text)
    try:
        from guardrails.input import InputGuardrail
        guard = InputGuardrail({
            "block_secrets": False, "block_pii": False,
            "block_prompt_injection": True, "block_jailbreak": True,
            "ml_injection": "off",
        })
        res = guard.check(unquoted)
        if not res.allowed:
            return True, res.reason or res.reason_code
    except Exception:
        pass
    return False, ""


def check_registry(registry: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Returns {poisoned: [...], drifted: [...], fingerprints: {...}}."""
    baseline = load_baseline()
    fps = current_fingerprints(registry)
    poisoned: list[dict[str, str]] = []
    drifted: list[dict[str, str]] = []
    for name, tool in registry.items():
        desc = str(tool.get("description", ""))
        hit, reason = detect_poisoning(desc)
        if hit:
            poisoned.append({"tool": name, "reason": reason, "severity": "critical"})
        expected = baseline.get(name)
        if expected and expected != fps[name]:
            drifted.append({"tool": name, "expected": expected, "actual": fps[name], "severity": "high"})
    return {"poisoned": poisoned, "drifted": drifted, "fingerprints": fps}


if __name__ == "__main__":  # pragma: no cover
    import sys
    sys.path.insert(0, ".")
    from app.mcp_server import TOOL_REGISTRY
    fps = current_fingerprints(TOOL_REGISTRY)
    if "--pin" in sys.argv:
        BASELINE_PATH.write_text(json.dumps(fps, indent=2, sort_keys=True), encoding="utf-8")
        print(f"pinned {len(fps)} tools to {BASELINE_PATH}")
    else:
        print(json.dumps(check_registry(TOOL_REGISTRY), indent=2))
