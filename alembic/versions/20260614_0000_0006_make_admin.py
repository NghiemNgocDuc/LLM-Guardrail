"""make dnghiem admin

Revision ID: 0006_make_admin
Revises: 0005_full_prompt
Create Date: 2026-06-14 00:00:00 UTC
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_make_admin"
down_revision: Union[str, None] = "0005_full_prompt"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_ORG_ID     = "00000000-0000-0000-0000-000000000001"
_DEFAULT_POLICY_ID  = "00000000-0000-0000-0000-000000000002"


def upgrade() -> None:
    op.execute("UPDATE users SET is_admin = true WHERE email = 'dnghiem@umass.edu'")

    # Create a default org only if no orgs exist yet
    op.execute(sa.text("""
        INSERT INTO organizations (id, name, slug, created_at)
        SELECT :org_id, 'Default Organization', 'default-organization', CURRENT_TIMESTAMP
        WHERE NOT EXISTS (SELECT 1 FROM organizations)
    """).bindparams(org_id=_DEFAULT_ORG_ID))

    # Create a default policy for that org only if none exist yet
    op.execute(sa.text("""
        INSERT INTO org_policies
            (id, org_id, input_rules, output_rules, topic_policy, compliance_rules, updated_at)
        SELECT :policy_id, :org_id, '{}', '{}', '{}', '{}', CURRENT_TIMESTAMP
        WHERE NOT EXISTS (SELECT 1 FROM org_policies)
          AND EXISTS (SELECT 1 FROM organizations WHERE id = :org_id)
    """).bindparams(policy_id=_DEFAULT_POLICY_ID, org_id=_DEFAULT_ORG_ID))

    # Assign user to the first org if they have none
    op.execute("""
        UPDATE users
        SET org_id = (SELECT id FROM organizations LIMIT 1)
        WHERE email = 'dnghiem@umass.edu' AND org_id IS NULL
    """)


def downgrade() -> None:
    pass
