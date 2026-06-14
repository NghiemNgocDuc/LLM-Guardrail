"""
System health endpoints:
  GET /health          — simple liveness (already exists in main app)
  GET /health/detailed — DB + Redis + LLM backend status
"""
import time

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db

settings = get_settings()
router = APIRouter(tags=["Health"])


async def _check_db(db: AsyncSession) -> dict:
    try:
        t0 = time.monotonic()
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def _check_redis() -> dict:
    from app.middleware.rate_limit import _redis
    if not _redis:
        return {"status": "not_configured"}
    try:
        t0 = time.monotonic()
        await _redis.ping()
        return {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def _check_llm(backend: str, url: str) -> dict:
    try:
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=4) as client:
            r = await client.get(url)
        return {"status": "ok" if r.status_code < 400 else "error",
                "latency_ms": round((time.monotonic() - t0) * 1000, 1),
                "http_status": r.status_code}
    except Exception as e:
        return {"status": "error", "detail": str(e)[:120]}


@router.get("/health/detailed")
async def detailed_health(db: AsyncSession = Depends(get_db)):
    db_status  = await _check_db(db)
    redis_status = await _check_redis()

    backends: dict = {}
    default = settings.DEFAULT_LLM_BACKEND
    if default == "ollama":
        ollama_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        backends["ollama"] = await _check_llm("ollama", f"{ollama_url}/api/tags")
    elif default in ("openai", "groq", "anthropic", "gemini"):
        backends[default] = {"status": "configured", "note": "key-authenticated, no ping endpoint"}
    else:
        backends[default] = {"status": "unknown"}

    overall = "ok"
    if db_status["status"] != "ok":
        overall = "degraded"
    if redis_status["status"] == "error":
        overall = "degraded"

    return {
        "overall": overall,
        "database": db_status,
        "redis": redis_status,
        "llm_backends": backends,
        "default_backend": default,
        "app_env": settings.APP_ENV,
        "billing_enabled": settings.BILLING_ENABLED,
    }
