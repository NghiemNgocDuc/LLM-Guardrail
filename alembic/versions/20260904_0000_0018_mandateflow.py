"""MandateFlow provenance-aware gateway — mandates, capabilities, references, runs, receipts

Revision ID: 0018_mandateflow
Revises: 0017_sync_prod_models
Create Date: 2026-09-04

Ports the MandateFlow P0 (provenance-aware authorization) onto the existing
LLM-Guardrail stack without replacing it:

  LLM-Guardrail today:  input/output guardrails + ToolApproval (human gate)
  MandateFlow adds:     provenance gate — same tool, same scope, DENY when
                        the reference was Payment-derived vs Support-derived

Built on what already exists:
  - ToolApproval pattern (risk_level, status, correlation_id) → Receipt
  - GuardrailEvaluation inference table → provenance ancestry walk
  - CorrelationMiddleware (X-Request-ID) → Run/Capability binding
  - OPA custom_rule_rego → pinned NO_PAYMENT_REIDENTIFICATION rule
  - RequestLog trigger pg_notify → receipt pg_notify

Idempotent (IF NOT EXISTS) so safe on dev (create_all) and prod (alembic).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018_mandateflow"
down_revision: Union[str, None] = "0017_sync_prod_models"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── mandates — top-level delegation grant (the “mandate”) ───────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS mandates (
            id UUID PRIMARY KEY,
            org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status VARCHAR(16) NOT NULL DEFAULT 'active',
            policy_context JSON NOT NULL DEFAULT '{}'::json,
            expires_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_mandates_org_id ON mandates (org_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_mandates_owner_id ON mandates (owner_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_mandates_status ON mandates (status)"))

    # ── capabilities — short-lived, attenuated bearer for one Run ────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS capabilities (
            id UUID PRIMARY KEY,
            mandate_id UUID NOT NULL REFERENCES mandates(id) ON DELETE CASCADE,
            run_id UUID,
            capability_hash VARCHAR(128) NOT NULL,
            scopes JSON NOT NULL DEFAULT '[]'::json,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_capabilities_mandate_id ON capabilities (mandate_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_capabilities_hash ON capabilities (capability_hash)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_capabilities_run_id ON capabilities (run_id)"))

    # ── references — server-minted handles with provenance ancestry ──────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS provenance_references (
            id UUID PRIMARY KEY,
            org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind VARCHAR(64) NOT NULL,
            provenance VARCHAR(64) NOT NULL,
            parent_id UUID REFERENCES provenance_references(id) ON DELETE SET NULL,
            handle VARCHAR(128) NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_provenance_refs_org_id ON provenance_references (org_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_provenance_refs_handle ON provenance_references (handle)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_provenance_refs_provenance ON provenance_references (provenance)"))

    # ── runs — one disposable Runtime per execution attempt ──────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS mandate_runs (
            id UUID PRIMARY KEY,
            mandate_id UUID NOT NULL REFERENCES mandates(id) ON DELETE CASCADE,
            org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            capability_id UUID REFERENCES capabilities(id) ON DELETE SET NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            runtime_id VARCHAR(128),
            correlation_id VARCHAR(36),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_mandate_runs_mandate_id ON mandate_runs (mandate_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_mandate_runs_org_id ON mandate_runs (org_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_mandate_runs_status ON mandate_runs (status)"))

    # ── receipts — per-tool decision (the “receipt” in MandateFlow evidence) ─
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS mandate_receipts (
            id UUID PRIMARY KEY,
            run_id UUID NOT NULL REFERENCES mandate_runs(id) ON DELETE CASCADE,
            mandate_id UUID NOT NULL REFERENCES mandates(id) ON DELETE CASCADE,
            org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            tool VARCHAR(128) NOT NULL,
            decision VARCHAR(16) NOT NULL,
            rule_id VARCHAR(64),
            reason TEXT,
            provenance_at_call VARCHAR(64),
            latency_ms INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_receipts_run_id ON mandate_receipts (run_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_receipts_mandate_id ON mandate_receipts (mandate_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_receipts_tool ON mandate_receipts (tool)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_receipts_decision ON mandate_receipts (decision)"))

    # ── fixture counters — provable deny (crmCounter invariant) ──────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS fixture_counters (
            org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            fixture VARCHAR(64) NOT NULL,
            counter INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (org_id, fixture)
        )
    """))

    # ── protected fixtures registry (for audit, mirrors Go fixtures) ─────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS protected_fixtures (
            name VARCHAR(64) PRIMARY KEY,
            description TEXT NOT NULL DEFAULT '',
            risk_level VARCHAR(16) NOT NULL DEFAULT 'high'
        )
    """))
    op.execute(sa.text("""
        INSERT INTO protected_fixtures (name, description, risk_level)
        VALUES
            ('support.list_tickets', 'List support tickets', 'medium'),
            ('payments.list_failures', 'List payment failures', 'high'),
            ('cases.lookup_subject', 'Lookup case subject by reference', 'medium'),
            ('crm.resolve_customer', 'Resolve customer in CRM — provenance-gated', 'critical'),
            ('payments.aggregate_failures', 'Aggregate payment failures (aggregate-only provenance)', 'medium')
        ON CONFLICT (name) DO NOTHING
    """))

    # ── pg_notify trigger for receipts (mirrors 0013 request_log_events) ─────
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION mandate_receipt_notify() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE payload text;
        BEGIN
            payload := json_build_object(
                'id', NEW.id::text,
                'run_id', NEW.run_id::text,
                'mandate_id', NEW.mandate_id::text,
                'tool', NEW.tool,
                'decision', NEW.decision,
                'rule_id', NEW.rule_id,
                'created_at', NEW.created_at
            )::text;
            PERFORM pg_notify('mandate_receipt_events', payload);
            RETURN NEW;
        END; $$;
    """))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_mandate_receipt_notify ON mandate_receipts"))
    op.execute(sa.text("CREATE TRIGGER trg_mandate_receipt_notify AFTER INSERT ON mandate_receipts FOR EACH ROW EXECUTE FUNCTION mandate_receipt_notify()"))


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_mandate_receipt_notify ON mandate_receipts"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS mandate_receipt_notify()"))
    op.execute(sa.text("DROP TABLE IF EXISTS protected_fixtures"))
    op.execute(sa.text("DROP TABLE IF EXISTS fixture_counters"))
    op.execute(sa.text("DROP TABLE IF EXISTS mandate_receipts"))
    op.execute(sa.text("DROP TABLE IF EXISTS mandate_runs"))
    op.execute(sa.text("DROP TABLE IF EXISTS provenance_references"))
    op.execute(sa.text("DROP TABLE IF EXISTS capabilities"))
    op.execute(sa.text("DROP TABLE IF EXISTS mandates"))
