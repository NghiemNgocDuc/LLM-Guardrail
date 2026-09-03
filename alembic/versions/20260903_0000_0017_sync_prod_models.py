"""sync prod DB with models — missing clerk_id, tier, memories, evals, tool approvals

Revision ID: 0017_sync_prod_models
Revises: 0016_api_key_budgets
Create Date: 2026-09-03

Prod Supabase was on 0016 but crash-landed on startup with:

  UndefinedColumnError: column users.clerk_id does not exist
  SELECT ... FROM users WHERE users.email = $1

because the Clerk integration added User.clerk_id (app/models/__init__.py:116)
without a migration, and OrgPolicy tier/opa_fail_mode/version, memories,
guardrail_evaluations, tool_approvals, org_policy_versions, and
request_logs.correlation_id were also never migrated (the local dev path
used Base.metadata.create_all on APP_ENV=development and never noticed).

This migration is fully idempotent (IF NOT EXISTS / IF NOT EXISTS indexes)
so it is safe whether it runs on a fresh DB, a dev DB that already has
these tables via create_all, or a prod DB that ran the seed before
migrations.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_sync_prod_models"
down_revision: Union[str, None] = "0016_api_key_budgets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users.clerk_id (Clerk integration) ─────────────────────────────────
    op.execute(sa.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS clerk_id VARCHAR(64)"))
    # unique + indexed as in the model — IF NOT EXISTS so re-runs are safe
    op.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_clerk_id ON users (clerk_id) WHERE clerk_id IS NOT NULL"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_users_clerk_id_plain ON users (clerk_id)"))

    # ── org_policies — tier / opa_fail_mode / version ───────────────────────
    op.execute(sa.text("ALTER TABLE org_policies ADD COLUMN IF NOT EXISTS tier INTEGER NOT NULL DEFAULT 2"))
    op.execute(sa.text("ALTER TABLE org_policies ADD COLUMN IF NOT EXISTS opa_fail_mode VARCHAR(16) NOT NULL DEFAULT 'closed'"))
    op.execute(sa.text("ALTER TABLE org_policies ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1"))
    # custom_rule_rego was added in 0010 but make idempotent here too
    op.execute(sa.text("ALTER TABLE org_policies ADD COLUMN IF NOT EXISTS custom_rule_rego TEXT"))

    # ── request_logs.correlation_id ─────────────────────────────────────────
    op.execute(sa.text("ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS correlation_id VARCHAR(36)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_request_logs_correlation_id ON request_logs (correlation_id)"))

    # ── org_policy_versions (versioned policy history) ──────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS org_policy_versions (
            id UUID PRIMARY KEY,
            org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            policy_id UUID NOT NULL REFERENCES org_policies(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            input_rules JSON NOT NULL DEFAULT '{}'::json,
            output_rules JSON NOT NULL DEFAULT '{}'::json,
            topic_policy JSON NOT NULL DEFAULT '{}'::json,
            compliance_rules JSON NOT NULL DEFAULT '{}'::json,
            llm_backend VARCHAR(32),
            llm_model VARCHAR(80),
            tier INTEGER NOT NULL DEFAULT 2,
            created_by VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_org_policy_versions_org_id ON org_policy_versions (org_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_org_policy_versions_policy_id ON org_policy_versions (policy_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_org_policy_versions_created_at ON org_policy_versions (created_at)"))

    # ── memories (Mem0-style long-term memory) ──────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS memories (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            org_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
            title VARCHAR(160) NOT NULL,
            content TEXT NOT NULL,
            category VARCHAR(24) NOT NULL DEFAULT 'fact',
            kind VARCHAR(16) NOT NULL DEFAULT 'user',
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0.82,
            importance INTEGER NOT NULL DEFAULT 3,
            pinned BOOLEAN NOT NULL DEFAULT FALSE,
            archived BOOLEAN NOT NULL DEFAULT FALSE,
            source_type VARCHAR(16),
            source_id VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_accessed TIMESTAMPTZ
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_memories_user_id ON memories (user_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_memories_org_id ON memories (org_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_memories_category ON memories (category)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_memories_kind ON memories (kind)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_memories_pinned ON memories (pinned)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_memories_archived ON memories (archived)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_memories_created_at ON memories (created_at)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_memories_updated_at ON memories (updated_at)"))

    # ── guardrail_evaluations (Databricks inference-table per-guardrail trace) ─
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS guardrail_evaluations (
            id UUID PRIMARY KEY,
            correlation_id VARCHAR(36) NOT NULL,
            request_log_id UUID REFERENCES request_logs(id) ON DELETE SET NULL,
            org_id VARCHAR(36),
            guardrail VARCHAR(64) NOT NULL,
            stage VARCHAR(16) NOT NULL,
            action VARCHAR(16) NOT NULL,
            verdict VARCHAR(16) NOT NULL,
            reason_code VARCHAR(80),
            latency_ms DOUBLE PRECISION,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_guardrail_evaluations_correlation_id ON guardrail_evaluations (correlation_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_guardrail_evaluations_request_log_id ON guardrail_evaluations (request_log_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_guardrail_evaluations_org_id ON guardrail_evaluations (org_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_guardrail_evaluations_guardrail ON guardrail_evaluations (guardrail)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_guardrail_evaluations_created_at ON guardrail_evaluations (created_at)"))

    # ── tool_approvals (InfrastructureSentinel human gate) ───────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS tool_approvals (
            id UUID PRIMARY KEY,
            org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            tool_name VARCHAR(80) NOT NULL,
            tool_input JSON NOT NULL DEFAULT '{}'::json,
            risk_level VARCHAR(16) NOT NULL DEFAULT 'high',
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            correlation_id VARCHAR(36),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            decided_at TIMESTAMPTZ
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_tool_approvals_org_id ON tool_approvals (org_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_tool_approvals_user_id ON tool_approvals (user_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_tool_approvals_tool_name ON tool_approvals (tool_name)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_tool_approvals_status ON tool_approvals (status)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_tool_approvals_correlation_id ON tool_approvals (correlation_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_tool_approvals_created_at ON tool_approvals (created_at)"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS tool_approvals"))
    op.execute(sa.text("DROP TABLE IF EXISTS guardrail_evaluations"))
    op.execute(sa.text("DROP TABLE IF EXISTS memories"))
    op.execute(sa.text("DROP TABLE IF EXISTS org_policy_versions"))
    op.execute(sa.text("ALTER TABLE request_logs DROP COLUMN IF EXISTS correlation_id"))
    op.execute(sa.text("ALTER TABLE org_policies DROP COLUMN IF EXISTS version"))
    op.execute(sa.text("ALTER TABLE org_policies DROP COLUMN IF EXISTS opa_fail_mode"))
    op.execute(sa.text("ALTER TABLE org_policies DROP COLUMN IF EXISTS tier"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_users_clerk_id_plain"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_users_clerk_id"))
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS clerk_id"))
