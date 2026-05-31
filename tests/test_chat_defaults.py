from app.routers import chat
from app.schemas import ChatRequest


def test_effective_max_tokens_uses_demo_limit_when_omitted(monkeypatch):
    monkeypatch.setattr(chat.settings, "DEMO_MODE", True)
    monkeypatch.setattr(chat.settings, "DEMO_MAX_OUTPUT_TOKENS", 128)
    body = ChatRequest(prompt="hello")

    assert chat._effective_max_tokens(body) == 128


def test_effective_max_tokens_keeps_explicit_value(monkeypatch):
    monkeypatch.setattr(chat.settings, "DEMO_MODE", True)
    monkeypatch.setattr(chat.settings, "DEMO_MAX_OUTPUT_TOKENS", 128)
    body = ChatRequest(prompt="hello", max_tokens=64)

    assert chat._effective_max_tokens(body) == 64


def test_effective_max_tokens_clamps_high_explicit_value(monkeypatch):
    monkeypatch.setattr(chat.settings, "DEMO_MODE", True)
    monkeypatch.setattr(chat.settings, "DEMO_MAX_OUTPUT_TOKENS", 128)
    body = ChatRequest(prompt="hello", max_tokens=1024)

    assert chat._effective_max_tokens(body) == 128
