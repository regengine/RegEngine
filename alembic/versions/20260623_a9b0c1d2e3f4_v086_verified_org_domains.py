"""v086 -- verified organization domains.

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-06-23

Adds explicit domain verification state so SSO-only policy routing cannot be
activated by merely claiming an email domain.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9b0c1d2e3f4"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "f8a9b0c1d2e3"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("domain_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("organizations", "domain_verified")
