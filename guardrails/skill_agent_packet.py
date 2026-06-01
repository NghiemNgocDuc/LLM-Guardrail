"""
Structured Skill Guard pause / resume messages for Cursor agent chat.
"""
from __future__ import annotations

from typing import Any

ACTION_LABELS = {
    "run_once": "Run once (this session only)",
    "always_allow": "Always allow (persist override)",
    "reject": "Reject (do not use flagged content)",
}


def build_agent_packet(
    action: str,
    *,
    findings: list[dict[str, Any]],
    scope: str = "all",
    user_message: str = "",
    filename: str | None = None,
) -> dict[str, Any]:
    """Build JSON the user pastes into agent chat (or writes to skill-guard-decision.json)."""
    if action not in ACTION_LABELS:
        raise ValueError(f"unknown action: {action}")

    keys = [f.get("finding_key") or f"{f.get('reason_code')}:{f.get('line_number') or 0}" for f in findings]
    codes = sorted({f.get("reason_code", "") for f in findings if f.get("reason_code")})

    may_continue = action != "reject"
    status = "continuing" if may_continue else "rejected"

    instruction = _instruction_for_agent(action, codes, keys, user_message)

    return {
        "type": "skill_guard_decision",
        "version": 1,
        "agent_status": "paused_resolved" if may_continue else "paused_rejected",
        "status": status,
        "action": action,
        "may_continue": may_continue,
        "scope": scope,
        "finding_keys": keys,
        "reason_codes": codes,
        "filename": filename,
        "user_message": (user_message or "").strip(),
        "instruction_for_agent": instruction,
    }


def _instruction_for_agent(action: str, codes: list[str], keys: list[str], user_message: str) -> str:
    codes_s = ", ".join(codes) if codes else "(none)"
    keys_s = ", ".join(keys) if keys else "(none)"
    note = f'\nUser note: "{user_message.strip()}"' if user_message and user_message.strip() else ""

    if action == "always_allow":
        return (
            "Skill Guard: user chose ALWAYS ALLOW. Chat may continue. "
            f"Persist overrides for reason_codes [{codes_s}] (keys: {keys_s}). "
            "You may use the skill content for this task; update .cursor/skill-guard-overrides.json if needed."
            f"{note}"
        )
    if action == "run_once":
        return (
            "Skill Guard: user chose RUN ONCE. Chat may continue for this session only. "
            f"Allow finding_keys [{keys_s}] this time — do not treat as permanent override."
            f"{note}"
        )
    return (
        "Skill Guard: user chose REJECT. Do NOT use the flagged skill content or secrets/commands. "
        f"Blocked reason_codes [{codes_s}]. Help the user fix the skill or remove the sensitive lines."
        f"{note}"
    )


def format_chat_control_prompt(
    findings: list[dict[str, Any]],
    *,
    source: str = "",
) -> str:
    """
    Text the agent must post in Cursor chat when Skill Guard pauses (the control layer).
    User replies in chat — not via the web dashboard.
    """
    lines = [
        "## Skill Guard — paused (control layer in **this chat**)",
        "",
        "Do **not** send the user to the web dashboard. Wait for their reply here.",
        "",
        "**Reply with one of:**",
        "1. **Run once** — allow flagged content for this task only",
        "2. **Always allow** — save override; never block these rules again",
        "3. **Reject** — do not use flagged content; help fix the skill",
        "4. **Your own message** — custom instruction (same as option 4 / send to agent)",
        "",
    ]
    if source:
        lines.append(f"Source: `{source}`")
        lines.append("")
    lines.append("### Flagged items")
    for f in findings:
        sev = f.get("severity", "?")
        code = f.get("reason_code", "?")
        line = f.get("line_number")
        snip = f.get("snippet", "")
        loc = f"line {line}" if line else "file"
        lines.append(f"- **[{sev}]** `{code}` ({loc}): `{snip}`")
    lines.extend([
        "",
        "After they reply, run `python scripts/skill_guard_decision.py <action> ...` and continue.",
    ])
    return "\n".join(lines)


def finding_to_dict(f) -> dict[str, Any]:
    """SkillFinding or dict → pause file entry."""
    if isinstance(f, dict):
        return f
    return {
        "finding_key": f"{f.reason_code}:{f.line_number or 0}",
        "reason_code": f.reason_code,
        "severity": f.severity,
        "check": f.check,
        "line_number": f.line_number,
        "snippet": f.snippet,
    }


def format_packet_for_chat(packet: dict[str, Any]) -> str:
    """Markdown block to paste into Cursor agent chat."""
    import json

    body = json.dumps(packet, indent=2)
    return (
        "## Skill Guard — user decision (agent: read and continue)\n\n"
        f"{packet.get('instruction_for_agent', '')}\n\n"
        f"```json\n{body}\n```"
    )
