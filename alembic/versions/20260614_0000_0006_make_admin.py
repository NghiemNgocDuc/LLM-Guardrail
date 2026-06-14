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


def upgrade() -> None:
    # Update dnghiem@umass.edu to be an admin
    op.execute("UPDATE users SET is_admin = true WHERE email = 'dnghiem@umass.edu'")
    
    # If the user doesn't have an organization, assign them to the first available organization
    # or create a default one if none exists.
    
    # First ensure at least one organization exists (only creates if table is empty)
    op.execute("""
        INSERT INTO organizations (id, name, slug, created_at)
        SELECT 'org_default', 'Default Organization', 'default-organization', CURRENT_TIMESTAMP
        WHERE NOT EXISTS (SELECT 1 FROM organizations)
    """)
    
    # Ensure a policy exists for the default org
    op.execute("""
        INSERT INTO org_policies (id, org_id, input_rules, output_rules, topic_policy, compliance_rules, created_at, updated_at)
        SELECT 'pol_default', 'org_default', '{}', '{}', '{}', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        WHERE NOT EXISTS (SELECT 1 FROM org_policies) AND EXISTS (SELECT 1 FROM organizations WHERE id = 'org_default')
    """)
    
    # Assign the user to the first organization
    op.execute("""
        UPDATE users 
        SET org_id = (SELECT id FROM organizations LIMIT 1) 
        WHERE email = 'dnghiem@umass.edu' AND org_id IS NULL
    """)


def downgrade() -> None:
    # No downgrade necessary or safe to do
    pass
