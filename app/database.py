"""
Async SQLAlchemy 2.0 database setup.
All models inherit from Base; session is injected via FastAPI dependency.
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = None
AsyncSessionLocal = None

# Supabase transaction pooler (PgBouncer) cannot reuse prepared statements across
# pooled backend connections. Disable both asyncpg and SQLAlchemy statement caches.
# See: https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#asyncpg-prepared-statement-cache
ASYNCPG_CONNECT_ARGS = {
    "statement_cache_size": 0,
    "prepared_statement_cache_size": 0,
    "server_settings": {"statement_timeout": "30000"},
}


def get_engine():
    global engine
    if engine is None:
        if not settings.DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not configured")
        
        # Only pass asyncpg-specific arguments if using a PostgreSQL dialect
        connect_args = {}
        if "postgresql" in settings.DATABASE_URL or settings.DATABASE_URL.startswith("postgres"):
            connect_args = dict(ASYNCPG_CONNECT_ARGS)

        engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
            connect_args=connect_args,
        )
    return engine


def get_sessionmaker():
    global AsyncSessionLocal
    if AsyncSessionLocal is None:
        AsyncSessionLocal = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return AsyncSessionLocal


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency: yields a DB session and closes it after the request."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_all_tables():
    """Called once at startup in dev. Use Alembic in production."""
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
