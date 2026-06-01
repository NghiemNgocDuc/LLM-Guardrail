"""
Apply user overrides when skill scans flag findings (run once, always allow, reject).
"""
from __future__ import annotations

from dataclasses import dataclass

from guardrails.skill import SkillFinding, SkillScanResult


def finding_key(finding: SkillFinding) -> str:
    return f"{finding.reason_code}:{finding.line_number or 0}"


@dataclass
class SkillOverrides:
    """Persisted + session allow lists."""

    session_allow_keys: set[str]
    always_allow_keys: set[str]
    always_allow_reason_codes: set[str]

    @classmethod
    def from_dict(cls, data: dict | None) -> "SkillOverrides":
        if not data:
            return cls(set(), set(), set())
        return cls(
            session_allow_keys=set(data.get("session_allow_keys") or []),
            always_allow_keys=set(data.get("always_allow_keys") or []),
            always_allow_reason_codes=set(data.get("always_allow_reason_codes") or []),
        )

    def to_dict(self) -> dict:
        return {
            "session_allow_keys": sorted(self.session_allow_keys),
            "always_allow_keys": sorted(self.always_allow_keys),
            "always_allow_reason_codes": sorted(self.always_allow_reason_codes),
        }

    def is_allowed(self, finding: SkillFinding) -> bool:
        key = finding_key(finding)
        if key in self.session_allow_keys or key in self.always_allow_keys:
            return True
        return finding.reason_code in self.always_allow_reason_codes

    def allow_once(self, finding: SkillFinding) -> None:
        self.session_allow_keys.add(finding_key(finding))

    def allow_always(self, finding: SkillFinding) -> None:
        self.always_allow_keys.add(finding_key(finding))
        self.always_allow_reason_codes.add(finding.reason_code)


@dataclass
class SkillScanDecision:
    """Result after applying overrides."""

    raw: SkillScanResult
    blocking: list[SkillFinding]
    allowed: list[SkillFinding]
    safe: bool
    blocked: bool

    @property
    def rejection_summary(self) -> str | None:
        if not self.blocking:
            return None
        n = len(self.blocking)
        kinds = sorted({f.category for f in self.blocking})
        return (
            f"Agent skill blocked: {n} issue(s) — "
            f"{', '.join(kinds)}. "
            "Choose Run once, Always allow, or Reject for each item below."
        )


def apply_overrides(result: SkillScanResult, overrides: SkillOverrides) -> SkillScanDecision:
    blocking: list[SkillFinding] = []
    allowed: list[SkillFinding] = []
    for f in result.findings:
        if overrides.is_allowed(f):
            allowed.append(f)
        else:
            blocking.append(f)
    safe = len(blocking) == 0
    return SkillScanDecision(
        raw=result,
        blocking=blocking,
        allowed=allowed,
        safe=safe,
        blocked=not safe,
    )
