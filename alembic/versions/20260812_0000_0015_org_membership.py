"""org membership for multi-team

Revision ID: 0015_org_membership
Revises: 0014_managed_skills
Create Date: 2026-08-30
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0015_org_membership"
down_revision: Union[str, None] = "0014_managed_skills"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "org_memberships",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "org_id", name="uq_org_membership_user_org"),
    )
    op.create_index("ix_org_memberships_user_org", "org_memberships", ["user_id", "org_id"])

def downgrade() -> None:
    op.drop_index("ix_org_memberships_user_org", table_name="org_memberships")
    op.drop_table("org_memberships")
