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


def get_engine():
    global engine
    if engine is None:
        if not settings.DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not configured")
        engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            pool_size=10,
            max_overflow=20,
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
