"""Per-IP rate limit middleware — global abuse protection for all endpoints.

Acts as a coarse flood gate before per-key/per-user limits in endpoint code.
Uses the same Redis backend when available; falls back to in-memory.
"""

import time
import uuid
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from redis.asyncio import Redis

from app.config import get_settings

settings = get_settings()

_redis: Redis | None = None
_ip_windows: dict[str, deque] = defaultdict(deque)
_WINDOW = 60.0
_DEFAULT_RPM = 200
_SENSITIVE_MUTATION_RPM = 30
_SENSITIVE_PREFIXES = ("/auth/clerk-webhook", "/admin", "/billing", "/api-keys")
_global_rate_sha: str | None = None

_GLOBAL_RATE_LUA = """
local key   = KEYS[1]
local now   = tonumber(ARGV[1])
local member = ARGV[2]
local limit = tonumber(ARGV[3])

redis.call('ZREMRANGEBYSCORE', key, 0, now - 60)
local count = redis.call('ZCARD', key)
if count < limit then
    redis.call('ZADD', key, now, member)
end
redis.call('EXPIRE', key, 65)
return count
"""


def _ip_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _get_redis() -> Redis | None:
    global _redis
    if _redis is None and settings.RATE_LIMIT_REDIS_URL:
        _redis = await Redis.from_url(
            settings.RATE_LIMIT_REDIS_URL,
            decode_responses=True,
        )
    return _redis


async def close_global_rate_limiter() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def _check_memory(ip: str, rpm: int) -> None:
    now = time.monotonic()
    q = _ip_windows[ip]
    while q and now - q[0] > _WINDOW:
        q.popleft()
    if len(q) >= rpm:
        raise ValueError("rate_exceeded")
    q.append(now)


async def _check_redis(redis: Redis, ip: str, rpm: int) -> None:
    global _global_rate_sha
    now = time.time()
    key = f"global_rate:{ip}"

    if _global_rate_sha is None:
        _global_rate_sha = await redis.script_load(_GLOBAL_RATE_LUA)

    member = f"{now}:{uuid.uuid4().hex}"
    count = await redis.evalsha(_global_rate_sha, 1, key, str(now), member, str(rpm))
    if int(count) >= rpm:
        raise ValueError("rate_exceeded")


def _sensitive_mutation_group(path: str, method: str) -> str | None:
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    return next((prefix for prefix in _SENSITIVE_PREFIXES if path == prefix or path.startswith(prefix + "/")), None)


class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path in ("/health", "/robots.txt", "/.well-known/security.txt"):
            return await call_next(request)

        ip = _ip_key(request)

        sensitive_group = _sensitive_mutation_group(path, request.method)
        redis = await _get_redis()
        try:
            if redis:
                await _check_redis(redis, ip, _DEFAULT_RPM)
            else:
                _check_memory(ip, _DEFAULT_RPM)
            if sensitive_group:
                bucket = f"mutation:{sensitive_group}:{ip}"
                if redis:
                    await _check_redis(redis, bucket, _SENSITIVE_MUTATION_RPM)
                else:
                    _check_memory(bucket, _SENSITIVE_MUTATION_RPM)
        except ValueError:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests — slow down."},
                headers={"Retry-After": "60"},
            )

        response = await call_next(request)
        return response
