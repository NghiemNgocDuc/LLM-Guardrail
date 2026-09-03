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
    op.add_column("api_keys", sa.Column("budget_tokens", sa.BigInteger(), nullable=True))
    op.add_column("api_keys", sa.Column("budget_used", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("api_keys", sa.Column("budget_reset_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("api_keys", "budget_reset_at")
    op.drop_column("api_keys", "budget_used")
    op.drop_column("api_keys", "budget_tokens")
