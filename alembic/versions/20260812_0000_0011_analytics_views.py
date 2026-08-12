"""analytics materialized views

Per-org, per-day rollups backing GET /analytics/top-blocked-reasons and
GET /analytics/false-positive-candidates. Raw SQL on purpose: materialized
views are DDL, and the refresh pipeline (scripts/refresh_analytics_views.py)
uses REFRESH MATERIALIZED VIEW CONCURRENTLY, which REQUIRES the unique
indexes created here.

Both views are read-only snapshots: they are as fresh as the last refresh.
The scheduled refresh interval is documented in scripts/refresh_analytics_views.py.

Revision ID: 0011_analytics_views
Revises: 0010_custom_rego_policy
Create Date: 2026-08-12 00:00:00 UTC
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0011_analytics_views"
down_revision: Union[str, None] = "0010_custom_rego_policy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Blocked-reason counts per org per day ────────────────────────────
    # Backs /analytics/top-blocked-reasons: per-day COUNT + MAX(created_at)
    # per (org, fired_rule); the endpoint sums the days back into one row.
    op.execute(
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
        """
    )
    # Unique index — REQUIRED for REFRESH MATERIALIZED VIEW CONCURRENTLY.
    # Its leading columns (org_id, day) also serve the endpoint's filter.
    op.execute(
        "CREATE UNIQUE INDEX uq_mv_blocked_reasons_daily "
        "ON mv_blocked_reasons_daily (org_id, day, fired_rule)"
    )
    op.execute(
        "CREATE INDEX idx_mv_blocked_reasons_daily_org_day "
        "ON mv_blocked_reasons_daily (org_id, day)"
    )

    # ── 2. False-positive candidates per org per day ────────────────────────
    # Blocked requests that users later disputed — thumbs-up feedback on the
    # request, OR the fired rule listed in the owner's always-allow overrides.
    # Each row is one disputed request; the endpoint groups by fired rule.
    op.execute(
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
        """
    )
    # Unique index — REQUIRED for REFRESH MATERIALIZED VIEW CONCURRENTLY.
    op.execute(
        "CREATE UNIQUE INDEX uq_mv_false_positive_candidates_daily "
        "ON mv_false_positive_candidates_daily (request_log_id)"
    )
    op.execute(
        "CREATE INDEX idx_mv_false_positive_candidates_daily_org_day "
        "ON mv_false_positive_candidates_daily (org_id, day)"
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_false_positive_candidates_daily")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_blocked_reasons_daily")
