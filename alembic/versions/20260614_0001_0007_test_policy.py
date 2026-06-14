"""test policy for dnghiem@umass.edu

Creates a dedicated 'Test' org with all guardrails disabled so the account
can send any prompt without being blocked during development.

Revision ID: 0007_test_policy
Revises: 0006_make_admin
Create Date: 2026-06-14 00:01:00 UTC
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_test_policy"
down_revision: Union[str, None] = "0006_make_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TEST_ORG_ID    = "org_test_dnghiem"
_TEST_POLICY_ID = "pol_test_dnghiem"
_TEST_EMAIL     = "dnghiem@umass.edu"

_INPUT_RULES = json.dumps({
    "block_secrets": False,
    "block_pii": False,
    "pii_redaction_mode": "off",
    "pii_patterns": [],
    "block_prompt_injection": False,
    "injection_keywords": [],
    "block_jailbreak": False,
    "jailbreak_patterns": [],
})

_OUTPUT_RULES = json.dumps({
    "enforce_schema": False,
    "block_toxic_content": False,
    "required_fields": [],
})

_TOPIC_POLICY = json.dumps({
    "blocked_topics": [],
})

_COMPLIANCE = json.dumps({
    "block_medical_advice": False,
    "never_discuss_competitors": False,
    "full_prompt_logging": True,
})


def upgrade() -> None:
    # 1. Dedicated test org (idempotent)
    op.execute(sa.text("""
        INSERT INTO organizations (id, name, slug, created_at)
        VALUES (:org_id, 'Test Org (dnghiem)', 'test-org-dnghiem', CURRENT_TIMESTAMP)
        ON CONFLICT (id) DO NOTHING
    """).bindparams(org_id=_TEST_ORG_ID))

    # 2. Lenient policy for that org (upsert so re-running is safe)
    op.execute(sa.text(f"""
        INSERT INTO org_policies
            (id, org_id, input_rules, output_rules, topic_policy, compliance_rules, updated_at)
        VALUES (
            '{_TEST_POLICY_ID}',
            '{_TEST_ORG_ID}',
            '{_INPUT_RULES}'::jsonb,
            '{_OUTPUT_RULES}'::jsonb,
            '{_TOPIC_POLICY}'::jsonb,
            '{_COMPLIANCE}'::jsonb,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT (org_id) DO UPDATE SET
            input_rules      = EXCLUDED.input_rules,
            output_rules     = EXCLUDED.output_rules,
            topic_policy     = EXCLUDED.topic_policy,
            compliance_rules = EXCLUDED.compliance_rules,
            updated_at       = CURRENT_TIMESTAMP
    """))

    # 3. Move user into the test org and ensure admin flag
    op.execute(sa.text("""
        UPDATE users
        SET org_id   = :org_id,
            is_admin = true
        WHERE email = :email
    """).bindparams(org_id=_TEST_ORG_ID, email=_TEST_EMAIL))

    # 4. Point any existing API keys owned by this user at the test org,
    #    so /chat picks up the lenient policy immediately.
    op.execute(sa.text("""
        UPDATE api_keys
        SET org_id = :org_id
        WHERE owner_id = (SELECT id FROM users WHERE email = :email)
    """).bindparams(org_id=_TEST_ORG_ID, email=_TEST_EMAIL))


def downgrade() -> None:
    # Detach user and keys from the test org, then remove it.
    op.execute(sa.text("""
        UPDATE api_keys SET org_id = NULL
        WHERE owner_id = (SELECT id FROM users WHERE email = :email)
    """).bindparams(email=_TEST_EMAIL))

    op.execute(sa.text("""
        UPDATE users SET org_id = NULL WHERE email = :email
    """).bindparams(email=_TEST_EMAIL))

    op.execute(sa.text("""
        DELETE FROM org_policies WHERE id = :policy_id
    """).bindparams(policy_id=_TEST_POLICY_ID))

    op.execute(sa.text("""
        DELETE FROM organizations WHERE id = :org_id
    """).bindparams(org_id=_TEST_ORG_ID))
