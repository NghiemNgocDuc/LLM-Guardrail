"""
System health endpoints:
  GET /health          — simple liveness (already exists in main app)
  GET /health/detailed — DB + Redis + LLM backend status
"""
import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.services import vectorstore

settings = get_settings()
router = APIRouter(tags=["Health"])


async def _check_db(db: AsyncSession) -> dict:
    try:
        t0 = time.monotonic()
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
    except Exception:
        return {"status": "error"}


async def _check_redis() -> dict:
    from app.middleware.rate_limit import _redis
    if not _redis:
        return {"status": "not_configured"}
    try:
        t0 = time.monotonic()
        await _redis.ping()
        return {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
    except Exception:
        return {"status": "error"}


@router.get("/health/detailed")
async def detailed_health(db: AsyncSession = Depends(get_db)):
    db_status  = await _check_db(db)
    redis_status = await _check_redis()

    overall = "ok"
    if db_status["status"] != "ok":
        overall = "degraded"
    if redis_status["status"] == "error":
        overall = "degraded"

    return {
        "overall": overall,
        "database": db_status,
        "redis": redis_status,
        "vectorstore": {
            "status": "ok" if vectorstore._pinecone_initialized else "not_configured",
        },
    }
