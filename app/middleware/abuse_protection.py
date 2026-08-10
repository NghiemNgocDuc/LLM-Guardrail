"""Anti-scraping & anti-abuse layer.

- Limits concurrent in-flight requests per IP on /chat (prevents parallel token burning).
- Enforces a minimum inter-request gap per IP on /chat (prevents rapid-fire scraping).
- Blocks a short list of known aggressive scraper bots.
- Tarpit: progressive delay for IPs that exceed rate limits (doubles each violation).

State is keyed per IP. When ``RATE_LIMIT_REDIS_URL`` is configured the state lives
in Redis (shared across API workers); otherwise it falls back to in-memory dicts
(single-worker deployments).
"""

import asyncio
import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from redis.asyncio import Redis

from app.config import get_settings

settings = get_settings()

# Known aggressive scraper / AI-training crawlers (lowercase substring match)
_BLOCKED_BOTS = frozenset({
    "ahrefsbot", "dotbot", "mj12bot", "blexbot", "semrushbot",
    "panscient", "woobot", "zoominfobot", "exabot",
    "claudebot", "anthropic-ai", "gptbot", "chatgpt-user",
})

# ── Per-IP tracking ──────────────────────────────────────────────────────
_in_flight: dict[str, int] = defaultdict(int)
_in_flight_lock: asyncio.Lock = asyncio.Lock()
_last_request: dict[str, float] = {}
_MIN_GAP_S = 2.0

# ── Tarpit ───────────────────────────────────────────────────────────────
# Tracks how many times an IP has been rate-limited in the last hour.
_violations: dict[str, int] = defaultdict(int)
_LAST_VIOLATION_RESET = 0.0
_TARPIT_BASE_S = 1.0   # initial extra delay
_TARPIT_MAX_S = 60.0   # cap

# ── Redis keys (only used when RATE_LIMIT_REDIS_URL is set) ──────────────
_LAST_TTL_S = 3600
_INFLIGHT_TTL_S = 30
_VIOLATIONS_TTL_S = 3600

_redis: Redis | None = None

_KEYS = {
    "last":      lambda ip: f"abuse:last:{ip}",
    "inflight":  lambda ip: f"abuse:inflight:{ip}",
    "violations": lambda ip: f"abuse:violations:{ip}",
}


async def _get_redis() -> Redis | None:
    global _redis
    if _redis is None and settings.RATE_LIMIT_REDIS_URL:
        _redis = await Redis.from_url(
            settings.RATE_LIMIT_REDIS_URL,
            decode_responses=True,
        )
    return _redis


async def close_abuse_protection() -> None:
    """Clear in-memory state and close the shared Redis pool if open."""
    global _redis
    _in_flight.clear()
    _last_request.clear()
    _violations.clear()
    if _redis is not None:
        await _redis.aclose()
        _redis = None


# ── Gap check ────────────────────────────────────────────────────────────

async def _check_gap(ip: str) -> bool:
    """True when the IP is below the minimum inter-request gap."""
    now = time.monotonic()
    redis = await _get_redis()
    if redis:
        last = await redis.get(_KEYS["last"](ip))
        if last is not None and (now - float(last)) < _MIN_GAP_S:
            return True
        await redis.set(_KEYS["last"](ip), str(now), ex=_LAST_TTL_S)
        return False
    last = _last_request.get(ip, 0.0)
    violated = last != 0.0 and now - last < _MIN_GAP_S
    if not violated:
        _last_request[ip] = now
    return violated


# ── In-flight counter ────────────────────────────────────────────────────

async def _begin_inflight(ip: str) -> bool:
    """True when the request may proceed; False when the IP already has one in flight."""
    redis = await _get_redis()
    if redis:
        n = await redis.incr(_KEYS["inflight"](ip))
        if n > 1:
            await redis.decr(_KEYS["inflight"](ip))
            return False
        await redis.expire(_KEYS["inflight"](ip), _INFLIGHT_TTL_S)
        return True
    async with _in_flight_lock:
        _in_flight[ip] += 1
        if _in_flight[ip] > 1:
            _in_flight[ip] -= 1
            return False
        return True


async def _end_inflight(ip: str) -> None:
    redis = await _get_redis()
    if redis:
        n = await redis.decr(_KEYS["inflight"](ip))
        if n <= 0:
            await redis.delete(_KEYS["inflight"](ip))
        return
    async with _in_flight_lock:
        _in_flight[ip] -= 1
        if _in_flight[ip] <= 0:
            _in_flight.pop(ip, None)


# ── Violations / tarpit ──────────────────────────────────────────────────

async def _record_violation(ip: str) -> None:
    redis = await _get_redis()
    if redis:
        await redis.incr(_KEYS["violations"](ip))
        await redis.expire(_KEYS["violations"](ip), _VIOLATIONS_TTL_S)
        return
    _violations[ip] += 1


async def _tarpit_delay(ip: str) -> float:
    redis = await _get_redis()
    if redis:
        raw = await redis.get(_KEYS["violations"](ip))
        n = int(raw) if raw else 0
        if n == 0:
            return 0.0
        return min(_TARPIT_BASE_S * (2 ** (n - 1)), _TARPIT_MAX_S)

    global _LAST_VIOLATION_RESET
    now = time.monotonic()
    # Crude hourly reset
    if now - _LAST_VIOLATION_RESET > 3600:
        _violations.clear()
        _LAST_VIOLATION_RESET = now
    n = _violations.get(ip, 0)
    if n == 0:
        return 0.0
    return min(_TARPIT_BASE_S * (2 ** (n - 1)), _TARPIT_MAX_S)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class AbuseProtectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Bypass for non-chat endpoints
        if not path.startswith("/chat"):
            return await call_next(request)

        ip = _client_ip(request)

        # ── 1. Known scraper bots ─────────────────────────────────────────
        ua = (request.headers.get("user-agent") or "").lower()
        if ua:
            for bot in _BLOCKED_BOTS:
                if bot in ua:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Forbidden"},
                    )

        # ── 2. Tarpit — delay repeat offenders before counting them ───────
        delay = await _tarpit_delay(ip)
        if delay > 0:
            await asyncio.sleep(delay)

        # ── 3. Minimum inter-request gap ──────────────────────────────────
        if await _check_gap(ip):
            await _record_violation(ip)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests — slow down."},
                headers={"Retry-After": str(int(_MIN_GAP_S))},
            )

        # ── 4. Concurrent in-flight limit (1 per IP) ──────────────────────
        if not await _begin_inflight(ip):
            await _record_violation(ip)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests — slow down."},
            )

        try:
            return await call_next(request)
        finally:
            await _end_inflight(ip)