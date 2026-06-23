"""v085 -- enterprise SSO domain policy.

Revision ID: f8a9b0c1d2e3
Revises: da5d93004161
Create Date: 2026-06-23

Adds organization domain routing metadata and constrains auth policy values
for Phase 6 enterprise SSO enforcement.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f8a9b0c1d2e3"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "da5d93004161"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("domain_name", sa.String(), nullable=True))
    op.create_index("ix_organizations_domain_name", "organizations", ["domain_name"], unique=True)

    op.execute(
        """
        UPDATE public.organizations
        SET enforced_auth_policy = 'standard'
        WHERE enforced_auth_policy IS NULL
           OR enforced_auth_policy NOT IN ('standard', 'sso_only')
        """
    )
    op.alter_column(
        "organizations",
        "enforced_auth_policy",
        existing_type=sa.String(),
        nullable=False,
        server_default="standard",
    )
    op.create_check_constraint(
        "organization_auth_policy",
        "organizations",
        "enforced_auth_policy IN ('standard', 'sso_only')",
    )


def downgrade() -> None:
    op.drop_constraint("organization_auth_policy", "organizations", type_="check")
    op.execute(
        """
        UPDATE public.organizations
        SET enforced_auth_policy = 'passwordless_email_code'
        WHERE enforced_auth_policy IN ('standard', 'sso_only')
        """
    )
    op.alter_column(
        "organizations",
        "enforced_auth_policy",
        existing_type=sa.String(),
        nullable=False,
        server_default="passwordless_email_code",
    )

    op.drop_index("ix_organizations_domain_name", table_name="organizations")
    op.drop_column("organizations", "domain_name")
