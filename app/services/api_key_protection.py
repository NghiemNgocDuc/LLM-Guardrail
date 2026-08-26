"""
API key exploit protection + temporary auto-ban.

Signals:
  - RPM burst (> EXPLOIT_RPM_THRESHOLD / min)
  - Token burn velocity (sum tokens in 5 min)
  - IP diversity (distinct IPs per key in 10 min)
  - Blocked-ratio (probing guardrails)
  - Repeated dedup hits (same prompt retried)
  - Abuse tarpit violations

On trigger: ban the API key + owning user for N minutes (exponential,
capped). Bans live in Redis when available, otherwise in-memory.
Enforced in deps.py:resolve_api_key before any LLM call.
"""
from __future__ import annotations

import time
import asyncio
from collections import defaultdict, deque
from fastapi import HTTPException, status

from app.config import get_settings

settings = get_settings()

# ── In-memory fallback ───────────────────────────────────────────────────
_lock = asyncio.Lock()

# key_id -> deque[timestamps]
_req_windows: dict[str, deque[float]] = defaultdict(deque)
# key_id -> deque[(ts, tokens)]
_token_windows: dict[str, deque[tuple[float, int]]] = defaultdict(deque)
# key_id -> deque[(ts, ip)]
_ip_windows: dict[str, deque[tuple[float, str]]] = defaultdict(deque)
# key_id -> deque[(ts, blocked_bool)]
_block_windows: dict[str, deque[tuple[float, bool]]] = defaultdict(deque)
# key_id -> {prompt_hash: deque[ts]}
_dedup_windows: dict[str, dict[str, deque[float]]] = defaultdict(lambda: defaultdict(deque))

# bans: id -> expiry monotonic
_banned_keys: dict[str, float] = {}
_banned_users: dict[str, float] = {}
# ban strike count for exponential backoff
_ban_strikes: dict[str, int] = defaultdict(int)

_redis = None  # lazy init


async def _get_redis():
    global _redis
    if _redis is None and settings.RATE_LIMIT_REDIS_URL:
        try:
            from redis.asyncio import Redis
            _redis = await Redis.from_url(settings.RATE_LIMIT_REDIS_URL, decode_responses=True)
        except Exception:
            return None
    return _redis


def _now() -> float:
    return time.monotonic()


# ── Public helpers ───────────────────────────────────────────────────────
async def is_banned(*, api_key_id: str | None = None, user_id: str | None = None) -> tuple[bool, int, str]:
    """Return (banned?, retry_after_seconds, reason)."""
    now = _now()
    # check key ban
    if api_key_id:
        # try Redis first
        redis = await _get_redis()
        if redis:
            try:
                ttl = await redis.ttl(f"ban:key:{api_key_id}")
                if ttl and ttl > 0:
                    reason = await redis.get(f"ban:key:{api_key_id}:reason") or "exploit_detected"
                    return True, int(ttl), reason
            except Exception:
                pass
        exp = _banned_keys.get(api_key_id)
        if exp and exp > now:
            return True, int(exp - now), "exploit_detected"
        elif exp and exp <= now:
            _banned_keys.pop(api_key_id, None)

    if user_id:
        redis = await _get_redis()
        if redis:
            try:
                ttl = await redis.ttl(f"ban:user:{user_id}")
                if ttl and ttl > 0:
                    reason = await redis.get(f"ban:user:{user_id}:reason") or "exploit_detected"
                    return True, int(ttl), reason
            except Exception:
                pass
        exp = _banned_users.get(user_id)
        if exp and exp > now:
            return True, int(exp - now), "exploit_detected"
        elif exp and exp <= now:
            _banned_users.pop(user_id, None)

    return False, 0, ""


async def ban_api_key(api_key_id: str, user_id: str, reason: str, duration_minutes: int | None = None) -> int:
    """Ban key+user for duration, exponential on repeat. Return seconds."""
    if not settings.EXPLOIT_PROTECTION_ENABLED:
        return 0
    base = duration_minutes or settings.EXPLOIT_BAN_DURATION_MINUTES
    strikes = _ban_strikes[api_key_id] + 1
    _ban_strikes[api_key_id] = strikes
    # exponential: 15, 30, 60, 120, ... cap at max
    duration = min(base * (2 ** (strikes - 1)), settings.EXPLOIT_MAX_BAN_DURATION_MINUTES)
    secs = int(duration * 60)
    expiry = _now() + secs

    _banned_keys[api_key_id] = expiry
    if user_id:
        _banned_users[user_id] = expiry

    redis = await _get_redis()
    if redis:
        try:
            await redis.setex(f"ban:key:{api_key_id}", secs, "1")
            await redis.setex(f"ban:key:{api_key_id}:reason", secs, reason)
            if user_id:
                await redis.setex(f"ban:user:{user_id}", secs, "1")
                await redis.setex(f"ban:user:{user_id}:reason", secs, reason)
            # keep strike count in redis as well
            await redis.setex(f"ban:strikes:{api_key_id}", 86400, str(strikes))
        except Exception:
            pass
    return secs


async def list_active_bans() -> list[dict]:
    """Return all active bans (key + user) for admin view."""
    now = _now()
    out = []
    for kid, exp in list(_banned_keys.items()):
        if exp > now:
            out.append({"type": "api_key", "id": kid, "retry_after": int(exp - now), "reason": "exploit_detected"})
    for uid, exp in list(_banned_users.items()):
        if exp > now:
            out.append({"type": "user", "id": uid, "retry_after": int(exp - now), "reason": "exploit_detected"})
    redis = await _get_redis()
    if redis:
        try:
            # Scan redis for ban keys (best-effort)
            async for key in redis.scan_iter(match="ban:key:*"):
                if key.endswith(":reason") or key.endswith(":strikes"):
                    continue
                ttl = await redis.ttl(key)
                if ttl and ttl > 0:
                    kid = key.split(":")[-1]
                    # avoid duplicates already in memory
                    if not any(x["id"] == kid and x["type"] == "api_key" for x in out):
                        reason = await redis.get(f"ban:key:{kid}:reason") or "exploit_detected"
                        out.append({"type": "api_key", "id": kid, "retry_after": int(ttl), "reason": reason})
            async for key in redis.scan_iter(match="ban:user:*"):
                if key.endswith(":reason"):
                    continue
                ttl = await redis.ttl(key)
                if ttl and ttl > 0:
                    uid = key.split(":")[-1]
                    if not any(x["id"] == uid and x["type"] == "user" for x in out):
                        reason = await redis.get(f"ban:user:{uid}:reason") or "exploit_detected"
                        out.append({"type": "user", "id": uid, "retry_after": int(ttl), "reason": reason})
        except Exception:
            pass
    return out


async def unban_api_key(api_key_id: str, user_id: str | None = None) -> None:
    _banned_keys.pop(api_key_id, None)
    _ban_strikes.pop(api_key_id, None)
    if user_id:
        _banned_users.pop(user_id, None)
    redis = await _get_redis()
    if redis:
        try:
            await redis.delete(f"ban:key:{api_key_id}", f"ban:key:{api_key_id}:reason", f"ban:strikes:{api_key_id}")
            if user_id:
                await redis.delete(f"ban:user:{user_id}", f"ban:user:{user_id}:reason")
        except Exception:
            pass
    # also unban by user id if only key provided we try to find owner
    if not user_id and api_key_id:
        # remove user bans that correspond to this key's owner (if cached)
        pass


async def check_ban_or_raise(api_key_id: str, user_id: str) -> None:
    banned, retry_after, reason = await is_banned(api_key_id=api_key_id, user_id=user_id)
    if banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "temporarily_banned",
                "message": f"API key temporarily banned for {reason}. Retry after {retry_after}s.",
                "retry_after": retry_after,
                "reason": reason,
            },
            headers={"Retry-After": str(retry_after)},
        )


def _prune_windows(key_id: str, now: float) -> None:
    # requests last 60s
    q = _req_windows[key_id]
    while q and now - q[0] > 60:
        q.popleft()
    # tokens last 300s
    tq = _token_windows[key_id]
    while tq and now - tq[0][0] > 300:
        tq.popleft()
    # ips last EXPLOIT_IP_WINDOW_S
    iq = _ip_windows[key_id]
    while iq and now - iq[0][0] > settings.EXPLOIT_IP_WINDOW_S:
        iq.popleft()
    # blocked last N entries (not time based, just cap)
    bq = _block_windows[key_id]
    while len(bq) > settings.EXPLOIT_BLOCKED_WINDOW:
        bq.popleft()
    # dedup per hash 300s
    for h, dq in list(_dedup_windows[key_id].items()):
        while dq and now - dq[0] > 300:
            dq.popleft()
        if not dq:
            _dedup_windows[key_id].pop(h, None)


async def record_usage(
    *,
    api_key_id: str,
    user_id: str,
    ip: str,
    tokens: int,
    blocked: bool,
    prompt_hash: str | None = None,
) -> tuple[bool, str]:
    """
    Record one request and return (should_ban, reason). Caller decides to ban.
    We separate detection from action so chat handler can log before banning.
    """
    if not settings.EXPLOIT_PROTECTION_ENABLED:
        return False, ""
    now = _now()
    async with _lock:
        _req_windows[api_key_id].append(now)
        if tokens:
            _token_windows[api_key_id].append((now, tokens))
        _ip_windows[api_key_id].append((now, ip))
        _block_windows[api_key_id].append((now, blocked))
        if prompt_hash:
            _dedup_windows[api_key_id][prompt_hash].append(now)

        _prune_windows(api_key_id, now)

        # ── Signal 1: RPM burst
        rpm = len(_req_windows[api_key_id])
        if rpm > settings.EXPLOIT_RPM_THRESHOLD:
            return True, f"rpm_burst:{rpm}/min"

        # ── Signal 2: token burn velocity (5m)
        burn = sum(t for _, t in _token_windows[api_key_id])
        if burn > settings.EXPLOIT_TOKEN_BURN_5M:
            return True, f"token_burn:{burn}/5m"

        # ── Signal 3: IP diversity (key shared/leaked)
        distinct_ips = len({addr for _, addr in _ip_windows[api_key_id]})
        if distinct_ips >= settings.EXPLOIT_IP_DIVERSITY_THRESHOLD:
            return True, f"ip_diversity:{distinct_ips} ips/{settings.EXPLOIT_IP_WINDOW_S}s"

        # ── Signal 4: high blocked ratio (probing)
        bq = _block_windows[api_key_id]
        if len(bq) >= settings.EXPLOIT_BLOCKED_WINDOW:
            blocked_cnt = sum(1 for _, b in bq if b)
            ratio = blocked_cnt / len(bq)
            if ratio >= settings.EXPLOIT_BLOCKED_RATIO:
                return True, f"blocked_ratio:{blocked_cnt}/{len(bq)}"

        # ── Signal 5: dedup abuse (same prompt hammered)
        if prompt_hash:
            cnt = len(_dedup_windows[api_key_id][prompt_hash])
            if cnt >= settings.EXPLOIT_DEDUP_THRESHOLD:
                return True, f"dedup_abuse:{cnt}x same prompt/5m"

    return False, ""


async def maybe_auto_ban(
    *,
    api_key_id: str,
    user_id: str,
    ip: str,
    tokens: int,
    blocked: bool,
    prompt_hash: str | None = None,
) -> tuple[bool, str, int]:
    """Record + auto-ban if exploit detected. Return (banned, reason, retry_after)."""
    should, reason = await record_usage(
        api_key_id=api_key_id, user_id=user_id, ip=ip, tokens=tokens, blocked=blocked, prompt_hash=prompt_hash
    )
    if should:
        secs = await ban_api_key(api_key_id, user_id, reason)
        return True, reason, secs
    return False, "", 0
