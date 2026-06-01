"""
Agent skill scanner — find secrets, PII, and internal details before they ship in agent context.
"""
import json
from pathlib import Path

from fastapi import APIRouter

from app.deps import CurrentUser
from app.schemas import (
    SkillAgentDecisionIn,
    SkillAgentPacketOut,
    SkillFindingOut,
    SkillScanRequest,
    SkillScanResponse,
)
from guardrails.skill import SkillFinding, SkillGuardrail
from guardrails.skill_agent_packet import build_agent_packet, format_packet_for_chat
from guardrails.skill_messages import explain_finding
from guardrails.skill_overrides import SkillOverrides, apply_overrides, finding_key

router = APIRouter(prefix="/skills", tags=["Agent Skills"])

DEFAULT_OVERRIDES_PATH = Path(".cursor/skill-guard-overrides.json")


def _finding_out(f: SkillFinding, *, allowed: bool = False) -> SkillFindingOut:
    return SkillFindingOut(
        finding_key=finding_key(f),
        category=f.category,
        severity=f.severity,
        check=f.check,
        reason=f.reason or "",
        reason_code=f.reason_code,
        explanation=explain_finding(f.reason_code, f.check),
        line_number=f.line_number,
        snippet=f.snippet,
        risk_score=f.risk_score,
        allowed_by_override=allowed,
    )


def _load_overrides(body: SkillScanRequest) -> SkillOverrides:
    base = SkillOverrides.from_dict(body.overrides.model_dump() if body.overrides else None)
    if DEFAULT_OVERRIDES_PATH.is_file():
        try:
            on_disk = json.loads(DEFAULT_OVERRIDES_PATH.read_text(encoding="utf-8"))
            disk = SkillOverrides.from_dict(on_disk)
            base.always_allow_keys |= disk.always_allow_keys
            base.always_allow_reason_codes |= disk.always_allow_reason_codes
        except (json.JSONDecodeError, OSError):
            pass
    return base


@router.post("/scan", response_model=SkillScanResponse)
async def scan_skill(body: SkillScanRequest, _user: CurrentUser):
    result = SkillGuardrail().scan(body.content)
    overrides = _load_overrides(body)
    decision = apply_overrides(result, overrides)

    all_out = [_finding_out(f, allowed=overrides.is_allowed(f)) for f in result.findings]
    blocking_out = [_finding_out(f) for f in decision.blocking]
    overridden_out = [_finding_out(f, allowed=True) for f in decision.allowed]

    return SkillScanResponse(
        safe=result.safe,
        risk_score=result.risk_score,
        findings=all_out,
        line_count=result.line_count,
        char_count=result.char_count,
        filename=body.filename,
        blocked=decision.blocked,
        agent_may_continue=decision.safe,
        agent_status="paused" if decision.blocked else "ok",
        rejection_summary=decision.rejection_summary,
        blocking_findings=blocking_out,
        overridden_findings=overridden_out,
    )


def _findings_for_packet(body: SkillAgentDecisionIn) -> list[dict]:
    out: list[dict] = []
    codes = body.reason_codes or []
    for i, key in enumerate(body.finding_keys):
        code = codes[i] if i < len(codes) else (key.split(":")[0] if ":" in key else key)
        line = 0
        if ":" in key:
            tail = key.rsplit(":", 1)[-1]
            if tail.isdigit():
                line = int(tail)
        out.append({"finding_key": key, "reason_code": code, "line_number": line})
    if not out and codes:
        for code in codes:
            out.append({"finding_key": f"{code}:0", "reason_code": code, "line_number": 0})
    return out


@router.post("/agent-packet", response_model=SkillAgentPacketOut)
async def format_agent_packet(body: SkillAgentDecisionIn, _user: CurrentUser):
    findings = _findings_for_packet(body)
    packet = build_agent_packet(
        body.action,
        findings=findings,
        scope=body.scope,
        user_message=body.user_message,
        filename=body.filename,
    )
    return SkillAgentPacketOut(packet=packet, chat_markdown=format_packet_for_chat(packet))
