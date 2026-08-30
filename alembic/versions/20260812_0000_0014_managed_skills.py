"""managed skills: versioned SKILL.md per org

Revision ID: 0014_managed_skills
Revises: 0013_notify_request_log_events
Create Date: 2026-08-13 00:00 UTC
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014_managed_skills"
down_revision: Union[str, None] = "0013_notify_request_log_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "managed_skills",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("update_mode", sa.String(length=16), nullable=False, server_default="overwrite"),
        sa.Column("live_url_token", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "slug", name="uq_managed_skill_org_slug"),
    )
    op.create_index("ix_managed_skills_slug", "managed_skills", ["slug"])
    op.create_table(
        "managed_skill_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("skill_id", sa.String(length=36), sa.ForeignKey("managed_skills.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("update_mode", sa.String(length=16), nullable=False, server_default="overwrite"),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_managed_skill_versions_org_slug", "managed_skill_versions", ["org_id", "slug"])


def downgrade() -> None:
    op.drop_index("ix_managed_skill_versions_org_slug", table_name="managed_skill_versions")
    op.drop_table("managed_skill_versions")
    op.drop_index("ix_managed_skills_slug", table_name="managed_skills")
    op.drop_table("managed_skills")
