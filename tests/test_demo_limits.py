import pytest
from fastapi import HTTPException

from app import demo_limits


def test_demo_payload_limits_are_disabled_by_default(monkeypatch):
    monkeypatch.setattr(demo_limits.settings, "DEMO_MODE", False)

    demo_limits.enforce_demo_payload_limits("x" * 10_000, 8192)


def test_demo_payload_limits_reject_long_prompt(monkeypatch):
    monkeypatch.setattr(demo_limits.settings, "DEMO_MODE", True)
    monkeypatch.setattr(demo_limits.settings, "DEMO_MAX_PROMPT_CHARS", 5)

    with pytest.raises(HTTPException) as exc:
        demo_limits.enforce_demo_payload_limits("too long", 10)

    assert exc.value.status_code == 400
    assert "prompt must be 5 characters or fewer" in exc.value.detail


def test_demo_payload_limits_reject_high_max_tokens(monkeypatch):
    monkeypatch.setattr(demo_limits.settings, "DEMO_MODE", True)
    monkeypatch.setattr(demo_limits.settings, "DEMO_MAX_PROMPT_CHARS", 100)
    monkeypatch.setattr(demo_limits.settings, "DEMO_MAX_OUTPUT_TOKENS", 16)

    with pytest.raises(HTTPException) as exc:
        demo_limits.enforce_demo_payload_limits("ok", 32)

    assert exc.value.status_code == 400
    assert "max_tokens must be 16 or fewer" in exc.value.detail
