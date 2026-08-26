"""Integration test for the request_log pg_notify feed trigger (PostgreSQL only).

Mirrors alembic/..._0013_notify_request_log_events.py: creates a minimal
request_logs table plus the notify function/trigger, LISTENs on
request_log_events, inserts rows, and asserts the broadcast payload has
exactly the five feed fields â€” and never full_prompt.

Skipped unless TEST_DATABASE_URL is set (postgresql+asyncpg:// URL).
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace

import asyncpg
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set â€” requires a PostgreSQL instance",
)

_DDL = [
    "CREATE TABLE request_logs (id TEXT PRIMARY KEY, org_id TEXT, status TEXT, fired_rule TEXT, created_at TIMESTAMPTZ)",
    """
    CREATE OR REPLACE FUNCTION request_logs_notify() RETURNS trigger
    LANGUAGE plpgsql AS $$
    DECLARE payload text;
    BEGIN
        payload := json_build_object(
            'id', NEW.id::text, 'org_id', NEW.org_id, 'status', NEW.status,
            'fired_rule', NEW.fired_rule, 'created_at', NEW.created_at
        )::text;
        PERFORM pg_notify('request_log_events', payload);
        RETURN NEW;
    END;
    $$;
    """,
    "CREATE TRIGGER trg_request_logs_notify AFTER INSERT ON request_logs FOR EACH ROW EXECUTE FUNCTION request_logs_notify()",
]

_DROP = ["DROP TABLE IF EXISTS request_logs CASCADE"]


def _dsn() -> str:
    return os.environ["TEST_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")


async def _setup(conn: asyncpg.Connection) -> None:
    for stmt in _DROP + _DDL:
        await conn.execute(stmt)


async def _listen(conn: asyncpg.Connection) -> asyncio.Queue:
    """Register a request_log_events listener; returns a queue of (channel, payload)."""
    queue: asyncio.Queue = asyncio.Queue()

    def _on_notification(_conn, _pid, channel, payload):
        queue.put_nowait((channel, payload))

    await conn.add_listener("request_log_events", _on_notification)
    return queue


async def _wait_notification(queue: asyncio.Queue, timeout: float = 5.0):
    """Wait for the next notification, polling so the socket reader stays alive."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        if not queue.empty():
            channel, payload = await queue.get()
            return SimpleNamespace(channel=channel, payload=payload)
        if asyncio.get_event_loop().time() >= deadline:
            raise TimeoutError("no notification received within %.1fs" % timeout)
        await asyncio.sleep(0.05)


def test_notify_payload_carries_feed_fields_only():
    async def run():
        listener = await asyncpg.connect(_dsn())
        writer = await asyncpg.connect(_dsn())
        try:
            await _setup(writer)
            queue = await _listen(listener)

            await writer.execute(
                "INSERT INTO request_logs (id, org_id, status, fired_rule, created_at) "
                "VALUES ($1, $2, $3, $4, $5)",
                "feed-test-1", "org-a", "delivered", None,
                datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc),
            )
            msg = await _wait_notification(queue)
            assert msg.channel == "request_log_events"
            payload = json.loads(msg.payload)

            assert payload == {
                "id": "feed-test-1",
                "org_id": "org-a",
                "status": "delivered",
                "fired_rule": None,
                "created_at": "2026-08-13T10:00:00+00:00",
            }
            assert "full_prompt" not in payload
            assert "prompt_preview" not in payload
            assert len(msg.payload.encode()) < 8000
        finally:
            await listener.close()
            await writer.close()

    asyncio.run(run())


def test_notify_fires_per_row_with_rule():
    async def run():
        listener = await asyncpg.connect(_dsn())
        writer = await asyncpg.connect(_dsn())
        try:
            await _setup(writer)
            queue = await _listen(listener)

            await writer.execute(
                "INSERT INTO request_logs (id, org_id, status, fired_rule, created_at) "
                "VALUES ($1, $2, $3, $4, $5), ($1 || '-2', $2, $3, $4, $5)",
                "feed-test-2", "org-b", "input_blocked", "pii_detected",
                datetime(2026, 8, 13, 11, 0, tzinfo=timezone.utc),
            )
            first = await _wait_notification(queue)
            second = await _wait_notification(queue)

            assert json.loads(first.payload)["fired_rule"] == "pii_detected"
            assert json.loads(first.payload)["org_id"] == "org-b"
            assert json.loads(second.payload)["id"] == "feed-test-2-2"
        finally:
            await listener.close()
            await writer.close()

    asyncio.run(run())


def test_notify_payload_never_includes_full_prompt():
    async def run():
        listener = await asyncpg.connect(_dsn())
        writer = await asyncpg.connect(_dsn())
        try:
            await _setup(writer)
            queue = await _listen(listener)

            await writer.execute(
                "INSERT INTO request_logs (id, org_id, status, fired_rule, created_at) "
                "VALUES ($1, $2, $3, $4, $5)",
                "feed-test-3", "org-a", "error", None, datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc),
            )
            msg = await _wait_notification(queue)
            payload = json.loads(msg.payload)
            assert set(payload.keys()) == {"id", "org_id", "status", "fired_rule", "created_at"}
        finally:
            await listener.close()
            await writer.close()

    asyncio.run(run())
