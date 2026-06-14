"""add scopes column to api_keys

Revision ID: 0008_api_key_scopes
Revises: 0007_test_policy
Create Date: 2026-06-14 00:02:00 UTC
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0008_api_key_scopes"
down_revision: Union[str, None] = "0007_test_policy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE api_keys
        ADD COLUMN IF NOT EXISTS scopes JSONB NOT NULL DEFAULT '["chat"]'::jsonb
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS scopes")
