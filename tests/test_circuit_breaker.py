"""Tests for the per-backend LLM circuit breaker."""
import asyncio
from types import SimpleNamespace

import httpx
import pytest

import app.services.llm as llm
from app.services.llm import call_llm, reset_breaker, stream_llm
from app.services.llm.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    _breakers,
    get_breaker,
    is_failure,
)


class _Clock:
    def __init__(self):
        self.t = 10_000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def _breaker(monkeypatch, **kwargs):
    clock = _Clock()
    monkeypatch.setattr("app.services.llm.circuit_breaker.time.monotonic", clock)
    return CircuitBreaker("mock", **kwargs), clock


# ── Class-level state machine ────────────────────────────────────────────

def test_open_after_threshold(monkeypatch):
    cb, _ = _breaker(monkeypatch, failure_threshold=3, cooldown_s=10, window_s=60)
    for _ in range(3):
        cb.on_failure()
    assert cb.state == "open"
    with pytest.raises(CircuitOpenError):
        cb.before_call()


def test_failures_prune_outside_window(monkeypatch):
    cb, clock = _breaker(monkeypatch, failure_threshold=3, cooldown_s=10, window_s=60)
    cb.on_failure()
    cb.on_failure()
    clock.advance(61)
    cb.on_failure()  # the first two fell out of the window — only one counts now
    assert cb.state != "open"
    cb.before_call()  # still accepting traffic
    cb.on_failure()
    cb.on_failure()
    assert cb.state == "open"


def test_half_open_probe_success_recloses(monkeypatch):
    cb, clock = _breaker(monkeypatch, failure_threshold=2, cooldown_s=10, window_s=60)
    cb.on_failure()
    cb.on_failure()
    assert cb.state == "open"

    clock.advance(11)
    cb.before_call()  # probe allowed
    with pytest.raises(CircuitOpenError):
        cb.before_call()  # concurrent second probe rejected
    cb.on_success()
    assert cb.state == "closed"
    cb.before_call()  # normal traffic again


def test_half_open_probe_failure_reopens(monkeypatch):
    cb, clock = _breaker(monkeypatch, failure_threshold=2, cooldown_s=10, window_s=60)
    cb.on_failure()
    cb.on_failure()
    clock.advance(11)
    cb.before_call()
    cb.on_failure()
    assert cb.state == "open"
    with pytest.raises(CircuitOpenError):
        cb.before_call()


def test_reset_forces_closed(monkeypatch):
    cb, _ = _breaker(monkeypatch, failure_threshold=1)
    cb.on_failure()
    assert cb.state == "open"
    cb.reset()
    assert cb.state == "closed"
    cb.before_call()


# ── Failure classification ───────────────────────────────────────────────

def test_is_failure_classification():
    assert is_failure(httpx.TimeoutException("slow"))
    resp_500 = httpx.Response(503, request=httpx.Request("POST", "http://x"))
    assert is_failure(httpx.HTTPStatusError("bad", request=resp_500.request, response=resp_500))
    resp_400 = httpx.Response(400, request=httpx.Request("POST", "http://x"))
    assert not is_failure(httpx.HTTPStatusError("bad", request=resp_400.request, response=resp_400))
    assert not is_failure(ValueError("programmer bug"))


# ── Wiring through call_llm / stream_llm ─────────────────────────────────

def _install_adapter(monkeypatch, complete_impl, stream_impl=None):
    reset_breaker("mock")
    _breakers.pop("mock", None)
    get_breaker("mock")  # fresh state for the test
    adapter = SimpleNamespace(complete=complete_impl, stream=stream_impl)
    monkeypatch.setattr(llm, "_ADAPTERS", {"mock": adapter})


def test_call_llm_trips_circuit_after_repeated_timeouts(monkeypatch):
    async def always_times_out(prompt, model, temperature, max_tokens):
        raise httpx.TimeoutException("provider unreachable")

    _install_adapter(monkeypatch, complete_impl=always_times_out)

    for _ in range(5):
        with pytest.raises(httpx.TimeoutException):
            asyncio.run(call_llm("hello", 0.0, 10, request_backend="mock"))

    with pytest.raises(CircuitOpenError):
        asyncio.run(call_llm("hello", 0.0, 10, request_backend="mock"))


def test_call_llm_recovers_after_success(monkeypatch):
    async def ok(prompt, model, temperature, max_tokens):
        from app.services.llm.base import LLMResponse
        return LLMResponse(text="ok", input_tokens=3, output_tokens=2, model="mock-local", backend="mock")

    async def fails(prompt, model, temperature, max_tokens):
        raise httpx.TimeoutException("boom")

    _install_adapter(monkeypatch, complete_impl=fails)
    for _ in range(5):
        with pytest.raises(httpx.TimeoutException):
            asyncio.run(call_llm("hello", 0.0, 10, request_backend="mock"))

    monkeypatch.setattr(llm, "_ADAPTERS", {"mock": SimpleNamespace(complete=ok, stream=None)})

    # While the breaker is open, even a healthy backend is rejected (fail fast)
    with pytest.raises(CircuitOpenError):
        asyncio.run(call_llm("hello", 0.0, 10, request_backend="mock"))

    # Simulate the cooldown elapsing → half-open probe → success recloses
    get_breaker("mock")._state = "half_open"
    resp = asyncio.run(call_llm("hello", 0.0, 10, request_backend="mock"))
    assert resp.text == "ok"
    assert get_breaker("mock").state == "closed"


def test_non_transient_errors_do_not_trip_breaker(monkeypatch):
    async def raises_value_error(prompt, model, temperature, max_tokens):
        raise ValueError("invalid model name")

    _install_adapter(monkeypatch, complete_impl=raises_value_error)

    for _ in range(10):
        with pytest.raises(ValueError):
            asyncio.run(call_llm("hello", 0.0, 10, request_backend="mock"))

    # still closed — client-side bugs must not take the backend offline
    assert get_breaker("mock").state == "closed"


def test_stream_llm_trips_breaker(monkeypatch):
    async def failing_stream(prompt, model, temperature, max_tokens):
        raise httpx.TimeoutException("mid-stream failure")
        yield  # pragma: no cover

    _install_adapter(monkeypatch, complete_impl=None, stream_impl=failing_stream)

    for _ in range(5):
        with pytest.raises(httpx.TimeoutException):
            async def consume():
                async for _ in stream_llm("hello", 0.0, 10, request_backend="mock"):
                    pass
            asyncio.run(consume())

    with pytest.raises(CircuitOpenError):
        async def consume2():
            async for _ in stream_llm("hello", 0.0, 10, request_backend="mock"):
                pass
        asyncio.run(consume2())