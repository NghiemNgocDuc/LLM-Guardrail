"""Tests for the abuse-protection layer — Redis path and in-memory fallback."""
import asyncio

import pytest
from starlette.requests import Request

from app.middleware import abuse_protection as ap


class _FakeRedis:
    """Minimal in-memory stand-in for redis.asyncio used by the middleware."""

    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    async def decr(self, key):
        self.store[key] = int(self.store.get(key, 0)) - 1
        return self.store[key]

    async def expire(self, key, ttl):
        pass

    async def delete(self, key):
        self.store.pop(key, None)

    async def aclose(self):
        pass


def _install_redis(monkeypatch, fake):
    async def _get_redis():
        return fake

    monkeypatch.setattr(ap, "_get_redis", _get_redis)


def _install_memory(monkeypatch):
    async def _get_redis():
        return None

    monkeypatch.setattr(ap, "_get_redis", _get_redis)
    ap._in_flight.clear()
    ap._last_request.clear()
    ap._violations.clear()


# ── Redis path ───────────────────────────────────────────────────────────

def test_redis_check_gap(monkeypatch):
    fake = _FakeRedis()
    _install_redis(monkeypatch, fake)

    assert asyncio.run(ap._check_gap("1.2.3.4")) is False
    assert asyncio.run(ap._check_gap("1.2.3.4")) is True
    # a different IP is unaffected
    assert asyncio.run(ap._check_gap("5.6.7.8")) is False


def test_redis_inflight_limits_parallel_requests(monkeypatch):
    fake = _FakeRedis()
    _install_redis(monkeypatch, fake)

    assert asyncio.run(ap._begin_inflight("1.2.3.4")) is True
    assert asyncio.run(ap._begin_inflight("1.2.3.4")) is False
    asyncio.run(ap._end_inflight("1.2.3.4"))
    assert asyncio.run(ap._begin_inflight("1.2.3.4")) is True
    assert ap._KEYS["inflight"]("1.2.3.4") in fake.store


def test_redis_tarpit_doubles_then_caps(monkeypatch):
    fake = _FakeRedis()
    _install_redis(monkeypatch, fake)

    assert asyncio.run(ap._tarpit_delay("1.2.3.4")) == 0.0
    for _ in range(3):
        asyncio.run(ap._record_violation("1.2.3.4"))
    assert asyncio.run(ap._tarpit_delay("1.2.3.4")) == 4.0
    for _ in range(10):  # 13 violations → 2**12 = 4096, capped at 60
        asyncio.run(ap._record_violation("1.2.3.4"))
    assert asyncio.run(ap._tarpit_delay("1.2.3.4")) == 60.0


# ── In-memory fallback ───────────────────────────────────────────────────

def test_memory_check_gap(monkeypatch):
    _install_memory(monkeypatch)
    assert asyncio.run(ap._check_gap("1.2.3.4")) is False
    assert asyncio.run(ap._check_gap("1.2.3.4")) is True


def test_memory_inflight(monkeypatch):
    _install_memory(monkeypatch)
    assert asyncio.run(ap._begin_inflight("1.2.3.4")) is True
    assert asyncio.run(ap._begin_inflight("1.2.3.4")) is False
    asyncio.run(ap._end_inflight("1.2.3.4"))
    assert asyncio.run(ap._begin_inflight("1.2.3.4")) is True


def test_memory_tarpit_doubles(monkeypatch):
    _install_memory(monkeypatch)
    assert asyncio.run(ap._tarpit_delay("1.2.3.4")) == 0.0
    asyncio.run(ap._record_violation("1.2.3.4"))
    asyncio.run(ap._record_violation("1.2.3.4"))
    assert asyncio.run(ap._tarpit_delay("1.2.3.4")) == 2.0


# ── Middleware dispatch ──────────────────────────────────────────────────

def _request(path, user_agent=""):
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [(b"user-agent", user_agent.encode())] if user_agent else [],
        "client": ("1.2.3.4", 54321),
        "query_string": b"",
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_middleware_blocks_known_bots(monkeypatch):
    _install_memory(monkeypatch)
    mw = ap.AbuseProtectionMiddleware(app=None)

    async def call_next(request):
        return "response"

    resp = await mw.dispatch(_request("/chat", "Mozilla/5.0 gptbot"), call_next)
    assert resp.status_code == 403

    resp = await mw.dispatch(_request("/chat", "curl/8.0"), call_next)
    assert resp == "response"


@pytest.mark.asyncio
async def test_middleware_bypasses_non_chat_paths(monkeypatch):
    _install_memory(monkeypatch)
    mw = ap.AbuseProtectionMiddleware(app=None)

    async def call_next(request):
        return "response"

    assert await mw.dispatch(_request("/health"), call_next) == "response"


@pytest.mark.asyncio
async def test_middleware_returns_429_inside_min_gap(monkeypatch):
    _install_memory(monkeypatch)
    mw = ap.AbuseProtectionMiddleware(app=None)

    async def call_next(request):
        return "response"

    resp = await mw.dispatch(_request("/chat"), call_next)
    assert resp == "response"
    resp = await mw.dispatch(_request("/chat"), call_next)
    assert resp.status_code == 429