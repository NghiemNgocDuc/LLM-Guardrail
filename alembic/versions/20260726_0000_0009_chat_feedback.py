"""add chat_feedback table

Revision ID: 0009_chat_feedback
Revises: 0008_api_key_scopes
Create Date: 2026-07-26 00:00:00 UTC
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0009_chat_feedback"
down_revision: Union[str, None] = "0008_api_key_scopes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS chat_feedback (
            request_log_id UUID PRIMARY KEY REFERENCES request_logs(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            rating INTEGER NOT NULL CHECK (rating IN (-1, 0, 1)),
            comment TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_chat_feedback_user_id ON chat_feedback(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_chat_feedback_rating ON chat_feedback(rating)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chat_feedback")
