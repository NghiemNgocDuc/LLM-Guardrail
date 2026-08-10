"""Tests for generic backend failover in call_llm / stream_llm."""
import httpx
import pytest

import app.services.llm as llm
from app.services.llm.base import LLMResponse, LLMStreamChunk
from app.services.llm.mock import MockAdapter


class _FailingAdapter(MockAdapter):
    """Fails every call with a breaker-worthy 5xx until tell=False."""

    fail = True

    async def complete(self, prompt, model, temperature, max_tokens):
        if self.fail:
            response = httpx.Response(503, request=httpx.Request("POST", "https://example.com"))
            raise httpx.HTTPStatusError("5xx", request=response.request, response=response)
        return LLMResponse(text="ok", input_tokens=1, output_tokens=1, model=model, backend="mock")

    async def stream(self, prompt, model, temperature, max_tokens):
        if self.fail:
            response = httpx.Response(503, request=httpx.Request("POST", "https://example.com"))
            raise httpx.HTTPStatusError("5xx", request=response.request, response=response)
        yield LLMStreamChunk(token="ok")


@pytest.fixture(autouse=True)
def _fresh_breakers():
    """Other tests trip the shared module-level 'mock' breaker; reset per test."""
    for name in ("mock", "primary", "alt"):
        llm.reset_breaker(name)
    yield


@pytest.mark.asyncio
async def test_call_llm_falls_back_to_next_backend(monkeypatch):
    failing = _FailingAdapter()
    monkeypatch.setitem(llm._ADAPTERS, "primary", failing)
    monkeypatch.setattr(llm.settings, "DEFAULT_LLM_BACKEND", "primary")

    resp = await llm.call_llm("hello", 0.1, 8, fallbacks=["mock"])

    assert "Mock response" in resp.text
    assert resp.backend == "mock"


@pytest.mark.asyncio
async def test_org_fallback_reaches_alternate_adapter(monkeypatch):
    calls = []

    class _Tracking(MockAdapter):
        async def complete(self, prompt, model, temperature, max_tokens, **kw):
            calls.append((model, self.__class__.__name__))
            return LLMResponse(text="a", input_tokens=0, output_tokens=0, model=model, backend="b")

    primary = _FailingAdapter()
    alt = _Tracking()
    monkeypatch.setitem(llm._ADAPTERS, "primary", primary)
    monkeypatch.setitem(llm._ADAPTERS, "alt", alt)
    monkeypatch.setattr(llm.settings, "DEFAULT_LLM_BACKEND", "primary")

    resp = await llm.call_llm("hi", 0.1, 4, fallbacks=["alt/alt-model"])

    assert resp.text == "a"
    assert resp.model == "alt-model"
    assert calls == [("alt-model", "_Tracking")]


@pytest.mark.asyncio
async def test_all_failures_surface_final_error(monkeypatch):
    failing = _FailingAdapter()
    monkeypatch.setitem(llm._ADAPTERS, "mock", failing)
    monkeypatch.setattr(llm.settings, "DEFAULT_LLM_BACKEND", "mock")

    with pytest.raises(httpx.HTTPStatusError):
        await llm.call_llm("hello", 0.1, 8)


@pytest.mark.asyncio
async def test_settings_failover_backends_are_used(monkeypatch):
    calls = []

    class _Alternate(MockAdapter):
        async def complete(self, prompt, model, temperature, max_tokens, **kw):
            calls.append(model)
            return LLMResponse(text="ok", input_tokens=0, output_tokens=0, model=model, backend="alt")

    primary = _FailingAdapter()
    monkeypatch.setitem(llm._ADAPTERS, "primary", primary)
    monkeypatch.setitem(llm._ADAPTERS, "alt", _Alternate())
    monkeypatch.setattr(llm.settings, "DEFAULT_LLM_BACKEND", "primary")
    monkeypatch.setattr(llm.settings, "LLM_FAILOVER_BACKENDS", "alt")

    resp = await llm.call_llm("hi", 0.1, 4)

    assert resp.backend == "alt"
    assert calls == [llm.settings.DEFAULT_MODEL]


@pytest.mark.asyncio
async def test_stream_fails_over_before_first_token(monkeypatch):
    primary = _FailingAdapter()
    monkeypatch.setitem(llm._ADAPTERS, "primary", primary)
    monkeypatch.setattr(llm.settings, "DEFAULT_LLM_BACKEND", "primary")

    chunks = [c async for c in llm.stream_llm("hello", 0.1, 8, fallbacks=["mock"])]
    text = "".join(c.token for c in chunks)
    assert "Mock response" in text