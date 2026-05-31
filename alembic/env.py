"""Alembic async migration environment."""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.config import get_settings
from app.database import ASYNCPG_CONNECT_ARGS, Base
from app.models import *  # noqa: F401, F403 — ensure all models are registered

config  = context.config
settings = get_settings()

if config.config_file_name:
    fileConfig(config.config_file_name)

# Inject the DB URL from settings so alembic.ini doesn't need secrets
# Alembic stores this in configparser, where '%' starts interpolation syntax.
# URL-encoded passwords can contain values like '%40', so escape '%' here.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=settings.DATABASE_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    connectable = create_async_engine(
        settings.DATABASE_URL,
        poolclass=pool.NullPool,
        connect_args=dict(ASYNCPG_CONNECT_ARGS),
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
