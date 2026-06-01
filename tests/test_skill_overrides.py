from guardrails.skill import SkillFinding, SkillGuardrail
from guardrails.skill_overrides import SkillOverrides, apply_overrides, finding_key


def test_finding_key_stable():
    f = SkillFinding(
        category="secret",
        severity="critical",
        check="x",
        reason="y",
        reason_code="gateway_api_key",
        line_number=3,
    )
    assert finding_key(f) == "gateway_api_key:3"


def test_apply_overrides_session_allow():
    content = "key grg_" + "a" * 40
    raw = SkillGuardrail().scan(content)
    overrides = SkillOverrides(session_allow_keys={finding_key(raw.findings[0])}, always_allow_keys=set(), always_allow_reason_codes=set())
    decision = apply_overrides(raw, overrides)
    assert decision.safe
    assert len(decision.blocking) == 0


def test_apply_overrides_always_allow_reason_code():
    content = "Connect via postgresql://u:p@10.0.0.5:5432/db"
    raw = SkillGuardrail().scan(content)
    overrides = SkillOverrides(set(), set(), {"database_url"})
    decision = apply_overrides(raw, overrides)
    assert not any(f.reason_code == "database_url" for f in decision.blocking)
