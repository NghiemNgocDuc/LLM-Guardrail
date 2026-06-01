from guardrails.skill_agent_packet import build_agent_packet, format_packet_for_chat


def test_build_always_allow_packet():
    packet = build_agent_packet(
        "always_allow",
        findings=[{"finding_key": "database_url:12", "reason_code": "database_url", "line_number": 12}],
        user_message="demo only",
        filename="SKILL.md",
    )
    assert packet["may_continue"] is True
    assert packet["action"] == "always_allow"
    assert "database_url" in packet["reason_codes"]
    assert "demo only" in packet["instruction_for_agent"]
    md = format_packet_for_chat(packet)
    assert "skill_guard_decision" in md
    assert "ALWAYS ALLOW" in md


def test_build_reject_packet():
    packet = build_agent_packet(
        "reject",
        findings=[{"finding_key": "drop_sql:3", "reason_code": "drop_sql", "line_number": 3}],
    )
    assert packet["may_continue"] is False
    assert packet["status"] == "rejected"
