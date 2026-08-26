"""Integration test for the request_logs immutability trigger (PostgreSQL only).

Mirrors alembic/versions/..._0012_immutable_request_log.py: creates the
request_logs table (model column set), the BEFORE UPDATE OR DELETE guard
function and trigger, then asserts that INSERT still works while UPDATE and
DELETE raise inside PostgreSQL.

Skipped unless TEST_DATABASE_URL is set (default CI and local runs have no
PostgreSQL) — run against a scratch database:

    $env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:password@localhost:5432/guardrails_test"
"""
import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set — requires a PostgreSQL instance",
)

# Model column set for app/models/__init__.py RequestLog (request_logs).
_DDL = [
    """
    CREATE TABLE request_logs (
        id                   TEXT PRIMARY KEY,
        api_key_id           TEXT,
        org_id               TEXT,
        prompt_hash          TEXT NOT NULL,
        prompt_preview       TEXT NOT NULL,
        full_prompt          TEXT,
        model                TEXT NOT NULL,
        backend              TEXT NOT NULL,
        input_passed         BOOLEAN NOT NULL,
        input_block_reason   TEXT,
        output_passed        BOOLEAN,
        output_block_reason  TEXT,
        fired_rule           TEXT,
        status               TEXT NOT NULL,
        latency_ms           INTEGER NOT NULL,
        input_tokens         INTEGER NOT NULL DEFAULT 0,
        output_tokens        INTEGER NOT NULL DEFAULT 0,
        created_at           TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE OR REPLACE FUNCTION request_logs_assert_immutable() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'request_logs is an immutable audit trail (INSERT only) — UPDATE/DELETE blocked'
              USING ERRCODE = '55000';
    END;
    $$;
    """,
    ("CREATE TRIGGER trg_request_logs_immutable "
     "BEFORE UPDATE OR DELETE ON request_logs "
     "FOR EACH ROW EXECUTE FUNCTION request_logs_assert_immutable()"),
]

_DROP = [
    "DROP TRIGGER IF EXISTS trg_request_logs_immutable ON request_logs",
    "DROP FUNCTION IF EXISTS request_logs_assert_immutable()",
    "DROP TABLE IF EXISTS request_logs CASCADE",
]

_INSERT = (
    "INSERT INTO request_logs (id, api_key_id, org_id, prompt_hash, prompt_preview, "
    "model, backend, input_passed, status, latency_ms, created_at) VALUES "
    "('r1', 'k1', 'org-a', 'hash1', 'hello', 'llama', 'groq', TRUE, 'delivered', 12, "
    "'2026-08-01 10:00:00+00')"
)


def _run(test_fn):
    """Create a scratch schema, run one async test body, tear the schema down."""

    async def runner():
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        try:
            async with engine.begin() as conn:
                for stmt in _DROP:
                    await conn.execute(text(stmt))
                for stmt in _DDL:
                    await conn.execute(text(stmt))
                await conn.execute(text(_INSERT))
            await test_fn(engine)
        finally:
            async with engine.begin() as conn:
                for stmt in _DROP:
                    await conn.execute(text(stmt))
            await engine.dispose()

    asyncio.run(runner())


def test_insert_still_works():
    async def body(engine):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO request_logs (id, api_key_id, org_id, prompt_hash, prompt_preview, "
                    "model, backend, input_passed, status, latency_ms, created_at) VALUES "
                    "('r2', 'k1', 'org-a', 'hash2', 'again', 'llama', 'groq', TRUE, 'delivered', 5, "
                    "'2026-08-01 11:00:00+00')"
                )
            )
        async with engine.connect() as conn:
            count = (await conn.execute(text("SELECT COUNT(*) FROM request_logs"))).scalar()
        assert count == 2

    _run(body)


def test_update_blocked():
    async def body(engine):
        with pytest.raises(Exception, match="immutable audit trail"):
            async with engine.begin() as conn:
                await conn.execute(
                    text("UPDATE request_logs SET status = 'error' WHERE id = 'r1'")
                )

    _run(body)


def test_delete_blocked():
    async def body(engine):
        with pytest.raises(Exception, match="immutable audit trail"):
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM request_logs WHERE id = 'r1'"))

    _run(body)


def test_rows_survive_attempted_mutation():
    async def body(engine):
        for stmt in (
            "UPDATE request_logs SET status = 'error' WHERE id = 'r1'",
            "DELETE FROM request_logs WHERE id = 'r1'",
        ):
            with pytest.raises(Exception, match="immutable audit trail"):
                async with engine.begin() as conn:
                    await conn.execute(text(stmt))
        async with engine.connect() as conn:
            row = (await conn.execute(
                text("SELECT status FROM request_logs WHERE id = 'r1'")
            )).first()
        assert row is not None
        assert row.status == "delivered"

    _run(body)