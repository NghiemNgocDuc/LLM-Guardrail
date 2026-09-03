"""add api key budget columns

Revision ID: 0016_api_key_budgets
Revises: 0015_org_membership
Create Date: 2026-09-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016_api_key_budgets"
down_revision: Union[str, None] = "0015_org_membership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: the public demo seed (scripts/create_public_demo.sql) also
    # creates these columns via top-level ALTER TABLE ... IF NOT EXISTS for
    # users who paste the seed directly in Supabase SQL Editor before running
    # migrations. If the seed ran first, op.add_column would raise
    # DuplicateColumnError and crash the Render deploy (startup preflight).
    # Use IF NOT EXISTS so the migration is safe to re-run in either order.
    op.execute(sa.text("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS budget_tokens BIGINT"))
    op.execute(sa.text("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS budget_used BIGINT NOT NULL DEFAULT 0"))
    op.execute(sa.text("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS budget_reset_at TIMESTAMPTZ"))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE api_keys DROP COLUMN IF EXISTS budget_reset_at"))
    op.execute(sa.text("ALTER TABLE api_keys DROP COLUMN IF EXISTS budget_used"))
    op.execute(sa.text("ALTER TABLE api_keys DROP COLUMN IF EXISTS budget_tokens"))
