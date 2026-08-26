"""Integration test for the analytics materialized views (PostgreSQL only).

Seeds request_logs / chat_feedback / user_skill_guard_overrides, refreshes
the views with REFRESH MATERIALIZED VIEW CONCURRENTLY (the exact mechanism
scripts/refresh_analytics_views.py runs), and asserts the rolled-up rows
match the endpoint semantics.

Skipped unless TEST_DATABASE_URL is set (default CI and local runs have no
PostgreSQL). The base tables are created here with only the columns the
views read — run against a scratch database:

    $env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:password@localhost:5432/guardrails_test"
"""
import asyncio
import os
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.routers.analytics import top_blocked_reasons

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set — requires a PostgreSQL instance",
)

# Mirrors alembic/versions/..._0011_analytics_views.py — minimal base tables
# plus the two materialized views and their unique/query indexes.
_DDL = [
    "CREATE TABLE users (id TEXT PRIMARY KEY)",
    "CREATE TABLE api_keys (id TEXT PRIMARY KEY, owner_id TEXT)",
    "CREATE TABLE user_skill_guard_overrides (user_id TEXT PRIMARY KEY, overrides JSONB)",
    ("CREATE TABLE request_logs (id TEXT PRIMARY KEY, org_id TEXT, api_key_id TEXT, "
     "status TEXT, fired_rule TEXT, prompt_preview TEXT, created_at TIMESTAMPTZ)"),
    "CREATE TABLE chat_feedback (request_log_id TEXT PRIMARY KEY, user_id TEXT, rating INT)",
    """
    CREATE MATERIALIZED VIEW mv_blocked_reasons_daily AS
    SELECT org_id,
           CAST(created_at AS DATE) AS day,
           fired_rule,
           COUNT(*) AS cnt,
           MAX(created_at) AS last_occurred_at
    FROM request_logs
    WHERE status IN ('input_blocked', 'output_blocked')
      AND fired_rule IS NOT NULL
    GROUP BY org_id, CAST(created_at AS DATE), fired_rule
    """,
    ("CREATE UNIQUE INDEX uq_mv_blocked_reasons_daily "
     "ON mv_blocked_reasons_daily (org_id, day, fired_rule)"),
    "CREATE INDEX idx_mv_blocked_reasons_daily_org_day ON mv_blocked_reasons_daily (org_id, day)",
    """
    CREATE MATERIALIZED VIEW mv_false_positive_candidates_daily AS
    SELECT rl.org_id,
           CAST(rl.created_at AS DATE) AS day,
           rl.fired_rule,
           rl.id AS request_log_id,
           rl.status,
           rl.prompt_preview,
           rl.created_at,
           (fb.rating = 1) AS positive_feedback,
           EXISTS (
               SELECT 1
               FROM jsonb_array_elements_text(
                   COALESCE(ov.overrides->'always_allow_reason_codes', '[]')::jsonb
               ) AS el
               WHERE el = rl.fired_rule
           ) AS override_hit
    FROM request_logs rl
    LEFT JOIN chat_feedback fb ON fb.request_log_id = rl.id
    LEFT JOIN api_keys ak ON ak.id = rl.api_key_id
    LEFT JOIN user_skill_guard_overrides ov ON ov.user_id = ak.owner_id
    WHERE rl.status IN ('input_blocked', 'output_blocked')
      AND rl.fired_rule IS NOT NULL
      AND (
          fb.rating = 1
          OR EXISTS (
              SELECT 1
              FROM jsonb_array_elements_text(
                  COALESCE(ov.overrides->'always_allow_reason_codes', '[]')::jsonb
              ) AS el
              WHERE el = rl.fired_rule
          )
      )
    """,
    ("CREATE UNIQUE INDEX uq_mv_false_positive_candidates_daily "
     "ON mv_false_positive_candidates_daily (request_log_id)"),
    ("CREATE INDEX idx_mv_false_positive_candidates_daily_org_day "
     "ON mv_false_positive_candidates_daily (org_id, day)"),
]

_DROP = [
    "DROP MATERIALIZED VIEW IF EXISTS mv_false_positive_candidates_daily",
    "DROP MATERIALIZED VIEW IF EXISTS mv_blocked_reasons_daily",
    "DROP TABLE IF EXISTS chat_feedback, request_logs, user_skill_guard_overrides, api_keys, users CASCADE",
]


async def _seed(conn) -> None:
    await conn.execute(text("INSERT INTO users (id) VALUES ('u1')"))
    await conn.execute(
        text("INSERT INTO api_keys (id, owner_id) VALUES ('k1', 'u1'), ('k2', 'u1')")
    )
    await conn.execute(
        text(
            "INSERT INTO request_logs (id, org_id, api_key_id, status, fired_rule, "
            "prompt_preview, created_at) VALUES "
            "('r1', 'org-a', 'k1', 'input_blocked', 'pii_detected', 'email in prompt', '2026-08-01 10:00:00+00'), "
            "('r2', 'org-a', 'k1', 'input_blocked', 'pii_detected', 'another email', '2026-08-02 10:00:00+00'), "
            "('r3', 'org-a', 'k2', 'input_blocked', 'toxic_content', 'bad word', '2026-08-02 11:00:00+00'), "
            "('r4', 'org-a', 'k1', 'delivered', NULL, 'fine', '2026-08-02 12:00:00+00'), "
            "('r5', 'org-b', 'k1', 'output_blocked', 'pii_detected', 'org b', '2026-08-02 13:00:00+00')"
        )
    )
    await conn.execute(
        text("INSERT INTO chat_feedback (request_log_id, user_id, rating) VALUES ('r1', 'u1', 1)")
    )
    await conn.execute(
        text(
            "INSERT INTO user_skill_guard_overrides (user_id, overrides) VALUES "
            "('u1', '{\"always_allow_reason_codes\": [\"toxic_content\"]}')"
        )
    )
    await conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_blocked_reasons_daily"))
    await conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_false_positive_candidates_daily"))


def _run(test_fn):
    """Create the scratch schema (views + seed), run one async test body, drop it."""

    async def runner():
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        try:
            async with engine.begin() as conn:
                for stmt in _DROP:
                    await conn.execute(text(stmt))
                for stmt in _DDL:
                    await conn.execute(text(stmt))
                await _seed(conn)
            await test_fn(engine)
        finally:
            async with engine.begin() as conn:
                for stmt in _DROP:
                    await conn.execute(text(stmt))
            await engine.dispose()

    asyncio.run(runner())


def test_blocked_reasons_view_rolls_up_per_org_per_day():
    async def body(engine):
        async with engine.connect() as conn:
            rows = (await conn.execute(
                text("SELECT org_id, day, fired_rule, cnt FROM mv_blocked_reasons_daily "
                     "ORDER BY org_id, day, fired_rule")
            )).fetchall()

        assert rows == [
            ("org-a", datetime(2026, 8, 1).date(), "pii_detected", 1),
            ("org-a", datetime(2026, 8, 2).date(), "pii_detected", 1),
            ("org-a", datetime(2026, 8, 2).date(), "toxic_content", 1),
            ("org-b", datetime(2026, 8, 2).date(), "pii_detected", 1),
        ]

    _run(body)


def test_blocked_reasons_endpoint_reads_view():
    async def body(engine):
        async with AsyncSession(engine) as session:
            result = await top_blocked_reasons(
                SimpleNamespace(org_id="org-a"),
                days=90,
                limit=10,
                db=session,
            )

        assert [(r.fired_rule, r.count) for r in result] == [("pii_detected", 2), ("toxic_content", 1)]
        assert result[0].last_occurred_at is not None

    _run(body)


def test_false_positive_view_joins_feedback_and_overrides():
    async def body(engine):
        async with engine.connect() as conn:
            rows = (await conn.execute(
                text("SELECT fired_rule, positive_feedback, override_hit, org_id "
                     "FROM mv_false_positive_candidates_daily ORDER BY request_log_id")
            )).fetchall()

        # r1: thumbs-up → positive. r3: override hit (no feedback → NULL). r5: org-b, no signal → out.
        assert rows == [
            ("pii_detected", True, False, "org-a"),
            ("toxic_content", None, True, "org-a"),
        ]

    _run(body)


def test_refresh_concurrently_allows_incremental_update():
    async def body(engine):
        # Add a fresh disputed row AFTER the initial refresh, then refresh again —
        # exercising the exact incremental path the scheduled job uses.
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO request_logs (id, org_id, api_key_id, status, fired_rule, "
                    "prompt_preview, created_at) VALUES "
                    "('r6', 'org-a', 'k1', 'input_blocked', 'jailbreak_attempt', 'dan', '2026-08-03 09:00:00+00')"
                )
            )
            await conn.execute(
                text("INSERT INTO chat_feedback (request_log_id, user_id, rating) VALUES ('r6', 'u1', 1)")
            )
            await conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_false_positive_candidates_daily"))

        async with engine.connect() as conn:
            count = (await conn.execute(
                text("SELECT COUNT(*) FROM mv_false_positive_candidates_daily WHERE org_id = 'org-a'")
            )).scalar()
        assert count == 3

    _run(body)