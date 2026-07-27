"""
LLM Guardrails Gateway — production entrypoint.
Run: uvicorn main:app --reload
"""
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path
import uuid

import posthog
import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import create_all_tables, get_engine
from app.http_client import close_http_client
from app.middleware.body_size import BodySizeMiddleware
from app.middleware.rate_limit import close_rate_limit_redis
from app.middleware.rate_limit_middleware import GlobalRateLimitMiddleware, close_global_rate_limiter
from app.middleware.content_type import ContentTypeMiddleware
from app.middleware.i18n import I18nMiddleware
from app.middleware.abuse_protection import AbuseProtectionMiddleware, close_abuse_protection
from app.middleware.request_logging import RequestLoggingMiddleware
from app.routers import admin, auth, api_keys, billing, chat, analytics, health, org, policy, skills, vector
from app.mcp_server import get_mcp_app
from sqlalchemy import text

from app.services.vectorstore import init as init_vectorstore, shutdown as shutdown_vectorstore

settings = get_settings()

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
    )

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }, separators=(",", ":"))

_handler = logging.StreamHandler()
_handler.setFormatter(JSONFormatter())
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    handlers=[_handler],
    force=True,
)
allowed_origins = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.POSTHOG_API_KEY:
        posthog.project_api_key = settings.POSTHOG_API_KEY
        posthog.host = settings.POSTHOG_HOST
    init_vectorstore()
    if settings.APP_ENV == "development":
        await create_all_tables()
    yield
    shutdown_vectorstore()
    await close_abuse_protection()
    await close_rate_limit_redis()
    await close_global_rate_limiter()
    await close_http_client()
    if settings.POSTHOG_API_KEY:
        posthog.shutdown()


app = FastAPI(
    title=settings.APP_NAME,
    description="Safety middleware for LLM traffic and agent skills — gateway, policy, and leak scanning.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.APP_ENV == "production" else "/docs",
    redoc_url=None if settings.APP_ENV == "production" else "/redoc",
    openapi_url=None if settings.APP_ENV == "production" else "/openapi.json",
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.getLogger("app.error").exception("Unhandled exception")
    if settings.APP_ENV == "production":
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )
    raise


@app.middleware("http")
async def add_security_headers(request, call_next):
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "0"
    if settings.APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), interest-cohort=()"
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(I18nMiddleware)
app.add_middleware(GlobalRateLimitMiddleware)
app.add_middleware(AbuseProtectionMiddleware)
app.add_middleware(BodySizeMiddleware)
app.add_middleware(ContentTypeMiddleware)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(auth.router)
app.include_router(api_keys.router)
app.include_router(admin.router)
app.include_router(chat.router)
app.include_router(analytics.router)
app.include_router(policy.router)
app.include_router(skills.router)
app.include_router(billing.router)
app.include_router(org.router)
app.include_router(health.router)
app.include_router(vector.router)

# Mount MCP server on /mcp for SSE transport (connectable by MCP clients)
mcp_app = get_mcp_app()
app.mount("/mcp", mcp_app, name="mcp")


@app.get("/health", tags=["Meta"])
async def health():
    checks = {"status": "ok", "env": settings.APP_ENV, "backend": settings.DEFAULT_LLM_BACKEND}
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
        checks["status"] = "degraded"
    return checks


@app.get("/.well-known/security.txt", include_in_schema=False)
async def security_txt():
    return Response(
        content=(
            "Contact: mailto:security@llm-guardrails.dev\n"
            "Expires: 2027-01-01T00:00:00.000Z\n"
            "Preferred-Languages: en\n"
            "Canonical: https://llm-guardrails.dev/.well-known/security.txt\n"
        ),
        media_type="text/plain",
        headers={"Content-Disposition": "inline"},
    )


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    return Response(
        content="User-agent: *\nDisallow: /\n",
        media_type="text/plain",
    )


static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def serve_frontend(path: str):
        requested = static_dir / path
        if path and requested.is_file():
            return FileResponse(requested)
        return FileResponse(static_dir / "index.html")
