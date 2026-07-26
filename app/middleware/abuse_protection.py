"""Anti-scraping & anti-abuse layer.

- Limits concurrent in-flight requests per IP on /chat (prevents parallel token burning).
- Enforces a minimum inter-request gap per IP on /chat (prevents rapid-fire scraping).
- Blocks a short list of known aggressive scraper bots.
- Tarpit: progressive delay for IPs that exceed rate limits (doubles each violation).
"""

import asyncio
import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

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


def _tarpit_delay(ip: str) -> float:
    global _LAST_VIOLATION_RESET
    now = time.monotonic()
    # Crude hourly reset
    if now - _LAST_VIOLATION_RESET > 3600:
        _violations.clear()
        _LAST_VIOLATION_RESET = now
    n = _violations.get(ip, 0)
    if n == 0:
        return 0.0
    delay = min(_TARPIT_BASE_S * (2 ** (n - 1)), _TARPIT_MAX_S)
    return delay


def _record_violation(ip: str) -> None:
    _violations[ip] += 1


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
        delay = _tarpit_delay(ip)
        if delay > 0:
            await asyncio.sleep(delay)

        # ── 3. Minimum inter-request gap ──────────────────────────────────
        now = time.monotonic()
        last = _last_request.get(ip, 0.0)
        if last != 0.0 and now - last < _MIN_GAP_S:
            _record_violation(ip)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests — slow down."},
                headers={"Retry-After": str(int(_MIN_GAP_S))},
            )
        _last_request[ip] = now

        # ── 4. Concurrent in-flight limit (1 per IP) ──────────────────────
        async with _in_flight_lock:
            _in_flight[ip] += 1
            if _in_flight[ip] > 1:
                _in_flight[ip] -= 1
                _record_violation(ip)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests — slow down."},
                )

        try:
            return await call_next(request)
        finally:
            async with _in_flight_lock:
                _in_flight[ip] -= 1
                if _in_flight[ip] <= 0:
                    _in_flight.pop(ip, None)


async def close_abuse_protection() -> None:
    _in_flight.clear()
    _last_request.clear()
    _violations.clear()