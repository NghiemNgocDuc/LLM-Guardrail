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


revision: str = "0007_test_policy"
down_revision: Union[str, None] = "0006_make_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TEST_ORG_ID    = "00000000-0000-0000-0000-000000000010"
_TEST_POLICY_ID = "00000000-0000-0000-0000-000000000011"
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
    # 1. Dedicated test org — embed UUID as literal with ::uuid cast (asyncpg requires this)
    op.execute(f"""
        INSERT INTO organizations (id, name, slug, created_at)
        VALUES ('{_TEST_ORG_ID}'::uuid, 'Test Org (dnghiem)', 'test-org-dnghiem', CURRENT_TIMESTAMP)
        ON CONFLICT (id) DO NOTHING
    """)

    # 2. Lenient policy — upsert so re-running is safe
    op.execute(f"""
        INSERT INTO org_policies
            (id, org_id, input_rules, output_rules, topic_policy, compliance_rules, updated_at)
        VALUES (
            '{_TEST_POLICY_ID}'::uuid,
            '{_TEST_ORG_ID}'::uuid,
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
    """)

    # 3. Move user into the test org and ensure admin flag
    op.execute(f"""
        UPDATE users
        SET org_id   = '{_TEST_ORG_ID}'::uuid,
            is_admin = true
        WHERE email = '{_TEST_EMAIL}'
    """)

    # 4. Point existing API keys at the test org so /chat picks up the lenient policy
    op.execute(f"""
        UPDATE api_keys
        SET org_id = '{_TEST_ORG_ID}'::uuid
        WHERE owner_id = (SELECT id FROM users WHERE email = '{_TEST_EMAIL}')
    """)


def downgrade() -> None:
    op.execute(f"UPDATE api_keys SET org_id = NULL WHERE owner_id = (SELECT id FROM users WHERE email = '{_TEST_EMAIL}')")
    op.execute(f"UPDATE users SET org_id = NULL WHERE email = '{_TEST_EMAIL}'")
    op.execute(f"DELETE FROM org_policies WHERE id = '{_TEST_POLICY_ID}'::uuid")
    op.execute(f"DELETE FROM organizations WHERE id = '{_TEST_ORG_ID}'::uuid")
