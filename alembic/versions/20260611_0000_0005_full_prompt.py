"""add full_prompt to request_logs

Revision ID: 0005_full_prompt
Revises: 0004_skill_rejections
Create Date: 2026-06-11 00:00:00 UTC
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_full_prompt"
down_revision: Union[str, None] = "0004_skill_rejections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("request_logs", sa.Column("full_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("request_logs", "full_prompt")
