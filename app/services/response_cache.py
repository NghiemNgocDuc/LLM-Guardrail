"""
Exact-match response cache (opt-in per policy).

Policy opt-in: output_rules: {"response_cache": true}

Caches the final delivered LLM text keyed by SHA-256 of
"{model}|{temperature}|{prompt}" for 6 hours. Backed by Redis when
RATE_LIMIT_REDIS_URL is set, in-memory dict otherwise (LRU-capped).
"""
from __future__ import annotations

import hashlib
import time
from collections import OrderedDict

from redis.asyncio import Redis

from app.config import get_settings

settings = get_settings()

_TTL_S = 6 * 3600
_MAX_ENTRIES = 10_000

_redis: Redis | None = None
_memory: OrderedDict[str, tuple[float, str]] = OrderedDict()


def cache_key(prompt: str, model: str, temperature: float) -> str:
    return hashlib.sha256(f"{model}|{temperature}|{prompt}".encode()).hexdigest()


async def _get_redis() -> Redis | None:
    global _redis
    if _redis is None and settings.RATE_LIMIT_REDIS_URL:
        _redis = await Redis.from_url(settings.RATE_LIMIT_REDIS_URL, decode_responses=True)
    return _redis


async def get_cached(prompt: str, model: str, temperature: float) -> str | None:
    key = cache_key(prompt, model, temperature)
    redis = await _get_redis()
    if redis:
        try:
            return await redis.get(f"llm:cache:{key}")
        except Exception:
            return None
    entry = _memory.get(key)
    if entry is None:
        return None
    stored_at, text = entry
    if time.monotonic() - stored_at > _TTL_S:
        _memory.pop(key, None)
        return None
    return text


async def set_cached(prompt: str, model: str, temperature: float, text: str) -> None:
    key = cache_key(prompt, model, temperature)
    redis = await _get_redis()
    if redis:
        try:
            await redis.set(f"llm:cache:{key}", text, ex=_TTL_S)
            return
        except Exception:
            pass  # fall back to memory
    _memory[key] = (time.monotonic(), text)
    _memory.move_to_end(key)
    while len(_memory) > _MAX_ENTRIES:
        _memory.popitem(last=False)


async def close_response_cache() -> None:
    global _redis
    _memory.clear()
    if _redis is not None:
        await _redis.aclose()
        _redis = None