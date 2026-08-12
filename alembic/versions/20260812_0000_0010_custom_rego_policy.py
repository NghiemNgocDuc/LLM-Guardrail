"""add custom_rule_rego to org_policies

Revision ID: 0010_custom_rego_policy
Revises: 0009_chat_feedback
Create Date: 2026-08-12 00:00:00 UTC
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0010_custom_rego_policy"
down_revision: Union[str, None] = "0009_chat_feedback"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE org_policies ADD COLUMN custom_rule_rego TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE org_policies DROP COLUMN IF EXISTS custom_rule_rego")
