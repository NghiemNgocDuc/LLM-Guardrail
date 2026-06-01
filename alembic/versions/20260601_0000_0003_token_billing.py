"""token billing wallets and purchases

Revision ID: 0003_token_billing
Revises: 0002_email_auth
Create Date: 2026-06-01 00:00:00 UTC
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_token_billing"
down_revision: Union[str, None] = "0002_email_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "token_wallets",
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("balance_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tokens_used_lifetime", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tokens_purchased_lifetime", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "token_purchases",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_slug", sa.String(32), nullable=False),
        sa.Column("tokens_granted", sa.BigInteger(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="usd"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("stripe_checkout_session_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_token_purchases_user_id", "token_purchases", ["user_id"])
    op.create_index(
        "ix_token_purchases_stripe_session",
        "token_purchases",
        ["stripe_checkout_session_id"],
        unique=True,
    )

    # Backfill existing users with free trial balance
    op.execute(
        """
        INSERT INTO token_wallets (user_id, balance_tokens, tokens_used_lifetime, tokens_purchased_lifetime, updated_at)
        SELECT id, 10000, 0, 0, NOW() AT TIME ZONE 'utc'
        FROM users
        ON CONFLICT (user_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_token_purchases_stripe_session", table_name="token_purchases")
    op.drop_index("ix_token_purchases_user_id", table_name="token_purchases")
    op.drop_table("token_purchases")
    op.drop_table("token_wallets")
