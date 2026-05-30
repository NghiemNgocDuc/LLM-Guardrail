import time
from collections import defaultdict, deque

from fastapi import HTTPException, status
from redis.asyncio import Redis

from app.config import get_settings

settings = get_settings()

_minute_windows: dict[str, deque] = defaultdict(deque)
_day_windows: dict[str, deque] = defaultdict(deque)
_redis: Redis | None = (
    Redis.from_url(settings.RATE_LIMIT_REDIS_URL, decode_responses=True)
    if settings.RATE_LIMIT_REDIS_URL
    else None
)

_MINUTE = 60.0
_DAY = 86_400.0


async def check_rate_limit(api_key_id: str, rpm: int, rpd: int) -> dict:
    """
    Raises HTTP 429 if either limit is exceeded.
    Redis is used when configured so multiple API workers share limits.
    """
    if _redis:
        return await _check_redis_rate_limit(api_key_id, rpm, rpd)
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


async def _check_redis_rate_limit(api_key_id: str, rpm: int, rpd: int) -> dict:
    assert _redis is not None

    now = time.time()
    member = str(now)
    minute_key = f"rate:{api_key_id}:minute"
    day_key = f"rate:{api_key_id}:day"

    pipe = _redis.pipeline(transaction=True)
    pipe.zremrangebyscore(minute_key, 0, now - _MINUTE)
    pipe.zremrangebyscore(day_key, 0, now - _DAY)
    pipe.zcard(minute_key)
    pipe.zcard(day_key)
    _, _, minute_count, day_count = await pipe.execute()

    minute_count = int(minute_count)
    day_count = int(day_count)
    _raise_if_limited(minute_count, day_count, rpm, rpd)

    pipe = _redis.pipeline(transaction=True)
    pipe.zadd(minute_key, {member: now})
    pipe.expire(minute_key, int(_MINUTE) + 5)
    pipe.zadd(day_key, {member: now})
    pipe.expire(day_key, int(_DAY) + 60)
    await pipe.execute()

    return {
        "rpm_remaining": rpm - minute_count - 1,
        "rpd_remaining": rpd - day_count - 1,
    }


def _raise_if_limited(minute_count: int, day_count: int, rpm: int, rpd: int) -> None:
    if minute_count >= rpm:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {rpm} requests/minute",
            headers={"Retry-After": "60"},
        )
    if day_count >= rpd:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily limit exceeded: {rpd} requests/day",
            headers={"Retry-After": "86400"},
        )
