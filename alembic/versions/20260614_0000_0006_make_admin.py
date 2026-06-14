"""make dnghiem admin

Revision ID: 0006_make_admin
Revises: 0005_full_prompt
Create Date: 2026-06-14 00:00:00 UTC
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0006_make_admin"
down_revision: Union[str, None] = "0005_full_prompt"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_ORG_ID    = "00000000-0000-0000-0000-000000000001"
_DEFAULT_POLICY_ID = "00000000-0000-0000-0000-000000000002"


def upgrade() -> None:
    op.execute("UPDATE users SET is_admin = true WHERE email = 'dnghiem@umass.edu'")

    # Create a default org only if no orgs exist yet
    op.execute(f"""
        INSERT INTO organizations (id, name, slug, created_at)
        SELECT '{_DEFAULT_ORG_ID}'::uuid, 'Default Organization', 'default-organization', CURRENT_TIMESTAMP
        WHERE NOT EXISTS (SELECT 1 FROM organizations)
    """)

    # Create a default policy for that org only if none exist yet
    op.execute(f"""
        INSERT INTO org_policies
            (id, org_id, input_rules, output_rules, topic_policy, compliance_rules, updated_at)
        SELECT '{_DEFAULT_POLICY_ID}'::uuid, '{_DEFAULT_ORG_ID}'::uuid,
               '{{}}'::jsonb, '{{}}'::jsonb, '{{}}'::jsonb, '{{}}'::jsonb, CURRENT_TIMESTAMP
        WHERE NOT EXISTS (SELECT 1 FROM org_policies)
          AND EXISTS (SELECT 1 FROM organizations WHERE id = '{_DEFAULT_ORG_ID}'::uuid)
    """)

    # Assign user to the first org if they have none
    op.execute("UPDATE users SET org_id = (SELECT id FROM organizations LIMIT 1) WHERE email = 'dnghiem@umass.edu' AND org_id IS NULL")


def downgrade() -> None:
    pass
