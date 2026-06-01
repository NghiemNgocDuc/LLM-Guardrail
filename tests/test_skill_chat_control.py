from guardrails.skill_agent_packet import format_chat_control_prompt


def test_chat_control_prompt_lists_four_options():
    text = format_chat_control_prompt(
        [{"severity": "high", "reason_code": "database_url", "line_number": 5, "snippet": "postgres://..."}],
        source="SKILL.md",
    )
    assert "Run once" in text
    assert "Always allow" in text
    assert "Reject" in text
    assert "this chat" in text.lower()
    assert "database_url" in text
