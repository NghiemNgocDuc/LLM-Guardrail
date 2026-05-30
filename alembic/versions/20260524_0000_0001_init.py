"""init

Revision ID: 0001_init
Revises:
Create Date: 2026-05-24 00:00:00 UTC

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "0001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── organizations ──────────────────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id",         postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name",       sa.String(120), nullable=False, unique=True),
        sa.Column("slug",       sa.String(60),  nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── org_policies ──────────────────────────────────────────────────────
    op.create_table(
        "org_policies",
        sa.Column("id",               postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("org_id",           postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("input_rules",      postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("output_rules",     postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("topic_policy",     postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("compliance_rules", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("llm_backend",      sa.String(32),  nullable=True),
        sa.Column("llm_model",        sa.String(80),  nullable=True),
        sa.Column("rate_limit_rpm",   sa.Integer(),   nullable=True),
        sa.Column("rate_limit_rpd",   sa.Integer(),   nullable=True),
        sa.Column("updated_at",       sa.DateTime(timezone=True), nullable=False),
    )

    # ── users ─────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id",              postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("email",           sa.String(254), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(256), nullable=False),
        sa.Column("full_name",       sa.String(120), nullable=False),
        sa.Column("is_active",       sa.Boolean(),   nullable=False, server_default="true"),
        sa.Column("is_admin",        sa.Boolean(),   nullable=False, server_default="false"),
        sa.Column("org_id",          postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("organizations.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("created_at",      sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login",      sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # ── api_keys ──────────────────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id",              postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name",            sa.String(80),  nullable=False),
        sa.Column("key_prefix",      sa.String(12),  nullable=False),
        sa.Column("key_hash",        sa.String(256), nullable=False, unique=True),
        sa.Column("is_active",       sa.Boolean(),   nullable=False, server_default="true"),
        sa.Column("owner_id",        postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("org_id",          postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("organizations.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("total_requests",  sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_blocked",   sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_tokens",    sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at",      sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at",    sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at",      sa.DateTime(timezone=True), nullable=True),
    )

    # ── request_logs ──────────────────────────────────────────────────────
    op.create_table(
        "request_logs",
        sa.Column("id",                  postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("api_key_id",          postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("api_keys.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("org_id",              postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("organizations.id"),
                  nullable=True),
        sa.Column("prompt_hash",         sa.String(64),  nullable=False),
        sa.Column("prompt_preview",      sa.String(120), nullable=False),
        sa.Column("model",               sa.String(80),  nullable=False),
        sa.Column("backend",             sa.String(32),  nullable=False),
        sa.Column("input_passed",        sa.Boolean(),   nullable=False),
        sa.Column("input_block_reason",  sa.Text(),      nullable=True),
        sa.Column("output_passed",       sa.Boolean(),   nullable=True),
        sa.Column("output_block_reason", sa.Text(),      nullable=True),
        sa.Column("fired_rule",          sa.String(80),  nullable=True),
        sa.Column("status",              sa.String(20),  nullable=False),
        sa.Column("latency_ms",          sa.Integer(),   nullable=False),
        sa.Column("input_tokens",        sa.Integer(),   nullable=False, server_default="0"),
        sa.Column("output_tokens",       sa.Integer(),   nullable=False, server_default="0"),
        sa.Column("created_at",          sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_request_logs_api_key_id", "request_logs", ["api_key_id"])
    op.create_index("ix_request_logs_org_id",     "request_logs", ["org_id"])
    op.create_index("ix_request_logs_created_at", "request_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("request_logs")
    op.drop_table("api_keys")
    op.drop_table("users")
    op.drop_table("org_policies")
    op.drop_table("organizations")
