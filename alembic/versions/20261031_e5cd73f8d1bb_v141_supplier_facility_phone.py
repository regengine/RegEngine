"""v141 -- supplier_facilities.phone for 21 CFR 1.1310 (A-2190).

Revision ID: e5cd73f8d1bb
Revises: b8c1e4f2a901
Create Date: 2026-10-31

Adds an optional business phone on supplier_facilities so a Facility location
description can carry name + phone + address (or a GLN stand-in). Nullable so
existing rows stay valid; UI and API accept phone on create.

Additive. Synthetic fixtures only until SEL-590 clears.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5cd73f8d1bb"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "b8c1e4f2a901"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "supplier_facilities",
        sa.Column("phone", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("supplier_facilities", "phone")
