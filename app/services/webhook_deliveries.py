"""
Guardrail webhook delivery tracking — ring buffer of recent deliveries per org.

Backed by Redis (shared across workers) when RATE_LIMIT_REDIS_URL is set;
falls back to an in-process deque otherwise. Used by GET /admin/webhook-deliveries.
"""
from __future__ import annotations

import json
import time
from collections import deque

from redis.asyncio import Redis

from app.config import get_settings

settings = get_settings()

_MAX_RECORDS = 500
_DELIVERY_TTL_S = 7 * 86400

_redis: Redis | None = None
# earliest-kept entry is dropped once the deque exceeds _MAX_RECORDS
_memory: deque[dict] = deque(maxlen=_MAX_RECORDS)


async def _get_redis() -> Redis | None:
    global _redis
    if _redis is None and settings.RATE_LIMIT_REDIS_URL:
        _redis = await Redis.from_url(settings.RATE_LIMIT_REDIS_URL, decode_responses=True)
    return _redis


def _key(org_id: str) -> str:
    return f"webhook:deliveries:{org_id or 'none'}"


async def record_delivery(
    org_id: str | None,
    event: str,
    ok: bool,
    http_status: int | None,
    attempts: int,
    error: str | None = None,
) -> None:
    record = {
        "event": event,
        "ok": ok,
        "http_status": http_status,
        "attempts": attempts,
        "error": error or ("" if ok else "network error"),
        "created_at": time.time(),
    }
    redis = await _get_redis()
    if redis:
        try:
            await redis.lpush(_key(org_id), json.dumps(record))
            await redis.ltrim(_key(org_id), 0, _MAX_RECORDS - 1)
            await redis.expire(_key(org_id), _DELIVERY_TTL_S)
            return
        except Exception:
            pass  # fall through to memory if Redis is momentarily down
    _memory.appendleft(record)


async def recent_deliveries(org_id: str | None, limit: int = 50) -> list[dict]:
    redis = await _get_redis()
    if redis:
        try:
            raw = await redis.lrange(_key(org_id), 0, limit - 1)
            items = []
            for entry in raw:
                try:
                    items.append(json.loads(entry))
                except json.JSONDecodeError:
                    continue
            return items
        except Exception:
            pass
    return list(_memory)[:limit]


async def close_webhook_deliveries() -> None:
    global _redis
    _memory.clear()
    if _redis is not None:
        await _redis.aclose()
        _redis = None