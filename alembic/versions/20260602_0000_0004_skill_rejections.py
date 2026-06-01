"""skill access rejections queue

Revision ID: 0004_skill_rejections
Revises: 0003_token_billing
Create Date: 2026-06-02 00:00:00 UTC
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_skill_rejections"
down_revision: Union[str, None] = "0003_token_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "skill_access_rejections",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="api_scan"),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("rejection_summary", sa.Text(), nullable=False),
        sa.Column("content_preview", sa.String(500), nullable=True),
        sa.Column("resolved_action", sa.String(24), nullable=True),
        sa.Column("resolver_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_skill_access_rejections_user_id", "skill_access_rejections", ["user_id"])
    op.create_index("ix_skill_access_rejections_status", "skill_access_rejections", ["status"])
    op.create_index("ix_skill_access_rejections_created_at", "skill_access_rejections", ["created_at"])

    op.create_table(
        "user_skill_guard_overrides",
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("overrides", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_skill_guard_overrides")
    op.drop_index("ix_skill_access_rejections_created_at", table_name="skill_access_rejections")
    op.drop_index("ix_skill_access_rejections_status", table_name="skill_access_rejections")
    op.drop_index("ix_skill_access_rejections_user_id", table_name="skill_access_rejections")
    op.drop_table("skill_access_rejections")
