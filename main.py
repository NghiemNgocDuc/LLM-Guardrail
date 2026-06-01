"""
LLM Guardrails Gateway — production entrypoint.
Run: uvicorn main:app --reload
"""
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import create_all_tables
from app.middleware.request_logging import RequestLoggingMiddleware
from app.routers import admin, auth, api_keys, billing, chat, analytics, policy, skills

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(message)s",
)
allowed_origins = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # In dev, auto-create tables. In production, use: alembic upgrade head
    if settings.APP_ENV == "development":
        await create_all_tables()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="Safety middleware for LLM traffic and agent skills — gateway, policy, and leak scanning.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(auth.router)
app.include_router(api_keys.router)
app.include_router(admin.router)
app.include_router(chat.router)
app.include_router(analytics.router)
app.include_router(policy.router)
app.include_router(skills.router)
app.include_router(billing.router)


@app.get("/health", tags=["Meta"])
async def health():
    return {
        "status":  "ok",
        "env":     settings.APP_ENV,
        "backend": settings.DEFAULT_LLM_BACKEND,
    }


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
