import time
from collections import defaultdict, deque

from fastapi import HTTPException, status
from redis.asyncio import Redis

from app.config import get_settings
from app.i18n import _t

settings = get_settings()

_minute_windows: dict[str, deque] = defaultdict(deque)
_day_windows: dict[str, deque] = defaultdict(deque)
_redis: Redis | None = None
_rate_limit_sha: str | None = None

_MINUTE = 60.0
_DAY = 86_400.0

# Lua script for atomic rate limiting: cleanup → check → record in one round-trip.
# Returns {minute_count_before_add, day_count_before_add} — caller checks limits after.
_RATE_LIMIT_LUA = """
local minute_key = KEYS[1]
local day_key    = KEYS[2]
local now        = tonumber(ARGV[1])
local member     = ARGV[2]

redis.call('ZREMRANGEBYSCORE', minute_key, 0, now - 60)
redis.call('ZREMRANGEBYSCORE', day_key, 0, now - 86400)

local minute_count = redis.call('ZCARD', minute_key)
local day_count    = redis.call('ZCARD', day_key)

redis.call('ZADD', minute_key, now, member)
redis.call('EXPIRE', minute_key, 65)
redis.call('ZADD', day_key, now, member)
redis.call('EXPIRE', day_key, 86460)

return {minute_count, day_count}
"""


async def _get_redis() -> Redis | None:
    global _redis
    if _redis is None and settings.RATE_LIMIT_REDIS_URL:
        _redis = await Redis.from_url(
            settings.RATE_LIMIT_REDIS_URL,
            decode_responses=True,
        )
    return _redis


async def close_rate_limit_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def check_rate_limit(api_key_id: str, rpm: int, rpd: int) -> dict:
    """
    Raises HTTP 429 if either limit is exceeded.
    Redis is used when configured so multiple API workers share limits.
    """
    redis = await _get_redis()
    if redis:
        return await _check_redis_rate_limit(redis, api_key_id, rpm, rpd)
    return _check_memory_rate_limit(api_key_id, rpm, rpd)


def _check_memory_rate_limit(api_key_id: str, rpm: int, rpd: int) -> dict:
    now = time.monotonic()

    minute_q = _minute_windows[api_key_id]
    day_q = _day_windows[api_key_id]

    while minute_q and now - minute_q[0] > _MINUTE:
        minute_q.popleft()
    while day_q and now - day_q[0] > _DAY:
        day_q.popleft()

    minute_count = len(minute_q)
    day_count = len(day_q)

    _raise_if_limited(minute_count, day_count, rpm, rpd)

    minute_q.append(now)
    day_q.append(now)

    return {
        "rpm_remaining": rpm - minute_count - 1,
        "rpd_remaining": rpd - day_count - 1,
    }


async def _check_redis_rate_limit(redis: Redis, api_key_id: str, rpm: int, rpd: int) -> dict:
    global _rate_limit_sha
    now = time.time()
    member = str(now)
    minute_key = f"rate:{api_key_id}:minute"
    day_key = f"rate:{api_key_id}:day"

    if _rate_limit_sha is None:
        _rate_limit_sha = await redis.script_load(_RATE_LIMIT_LUA)

    minute_count, day_count = await redis.evalsha(
        _rate_limit_sha, 2, minute_key, day_key, str(now), member
    )
    minute_count = int(minute_count)
    day_count = int(day_count)
    _raise_if_limited(minute_count, day_count, rpm, rpd)

    return {
        "rpm_remaining": rpm - minute_count - 1,
        "rpd_remaining": rpd - day_count - 1,
    }


def _raise_if_limited(minute_count: int, day_count: int, rpm: int, rpd: int) -> None:
    if minute_count >= rpm:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_t("rate_limit.exceeded_per_minute"),
            headers={"Retry-After": "60"},
        )
    if day_count >= rpd:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_t("rate_limit.exceeded_per_day"),
            headers={"Retry-After": "86400"},
        )
