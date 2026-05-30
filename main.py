"""
LLM Guardrails Gateway — production entrypoint.
Run: uvicorn main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import create_all_tables
from app.routers import auth, api_keys, chat, analytics, policy

settings = get_settings()
allowed_origins = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # In dev, auto-create tables. In production, use: alembic upgrade head
    if settings.APP_ENV == "development":
        await create_all_tables()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="Safety & compliance middleware for any LLM backend.",
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

app.include_router(auth.router)
app.include_router(api_keys.router)
app.include_router(chat.router)
app.include_router(analytics.router)
app.include_router(policy.router)


@app.get("/health", tags=["Meta"])
async def health():
    return {
        "status":  "ok",
        "env":     settings.APP_ENV,
        "backend": settings.DEFAULT_LLM_BACKEND,
    }
