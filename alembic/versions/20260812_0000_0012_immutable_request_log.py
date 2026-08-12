"""enforce request_logs immutability at the database level

request_logs is the full audit trail (see app/models/__init__.py — RequestLog
"immutable audit trail — never update, only insert"). The model-level
convention was previously the only enforcement; this migration adds a
database-level guarantee that survives any code path, migration, or ad-hoc
SQL: UPDATE and DELETE on request_logs now raise inside PostgreSQL.

Deliberate properties:

- The app only ever INSERTs request_logs. Key revocation is a soft delete
  (api_keys.is_active = False) — no code path mutates audit rows, and the
  APIKey FK (ondelete="SET NULL") therefore never fires in application code.
- As a consequence, hard-deleting an api_keys row that still has request
  logs is also blocked (the FK's SET NULL cascade is itself an UPDATE on
  request_logs and hits this trigger). Audit history can never be detached,
  silently altered, or purged — a feature, not a bug.
- Retention/cleanup of request_logs must be designed as a deliberate,
  explicit operation (e.g. a dedicated maintenance role or dropping the
  trigger in a named maintenance transaction) — nothing in the app does this
  today.

Revision ID: 0012_immutable_request_log
Revises: 0011_analytics_views
Create Date: 2026-08-12 00:00:00 UTC
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0012_immutable_request_log"
down_revision: Union[str, None] = "0011_analytics_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FUNCTION = "request_logs_assert_immutable"
_TRIGGER = "trg_request_logs_immutable"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FUNCTION}() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'request_logs is an immutable audit trail (INSERT only) — UPDATE/DELETE blocked'
                  USING ERRCODE = '55000';  -- object_not_in_prerequisite_state
        END;
        $$;
        """
    )
    op.execute(
        f"CREATE TRIGGER {_TRIGGER} "
        f"BEFORE UPDATE OR DELETE ON request_logs "
        f"FOR EACH ROW EXECUTE FUNCTION {_FUNCTION}()"
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON request_logs")
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION}()")
