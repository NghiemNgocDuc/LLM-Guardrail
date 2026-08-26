"""emit a live pg_notify event for every INSERT into request_logs

Supports the Elixir/Phoenix live request feed (elixir/live_feed): an
AFTER INSERT trigger publishes a compact JSON payload on the
'request_log_events' channel, which the feed service consumes via
Postgrex LISTEN and fans out over per-org websocket topics.

This is strictly additive to 0012_immutable_request_log:

- 0012 blocks UPDATE/DELETE (trg_request_logs_immutable).
- This migration only fires AFTER INSERT — it never runs UPDATE/DELETE,
  so the immutability trigger cannot interfere with it, and vice versa.

Payload is deliberately tiny (Postgres caps NOTIFY payloads at 8000
bytes; this is ~200): only id, org_id, status, fired_rule, created_at.
full_prompt is never included — the feed is for live UI updates, and
the audit trail itself is never mutated.

Revision ID: 0013_notify_request_log_events
Revises: 0012_immutable_request_log
Create Date: 2026-08-13 00:00:00 UTC
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0013_notify_request_log_events"
down_revision: Union[str, None] = "0012_immutable_request_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FUNCTION = "request_logs_notify"
_TRIGGER = "trg_request_logs_notify"
_CHANNEL = "request_log_events"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FUNCTION}() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            payload text;
        BEGIN
            payload := json_build_object(
                'id',         NEW.id::text,
                'org_id',     NEW.org_id,
                'status',     NEW.status,
                'fired_rule', NEW.fired_rule,
                'created_at', NEW.created_at
            )::text;
            PERFORM pg_notify('{_CHANNEL}', payload);
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        f"CREATE TRIGGER {_TRIGGER} "
        f"AFTER INSERT ON request_logs "
        f"FOR EACH ROW EXECUTE FUNCTION {_FUNCTION}()"
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON request_logs")
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION}()")