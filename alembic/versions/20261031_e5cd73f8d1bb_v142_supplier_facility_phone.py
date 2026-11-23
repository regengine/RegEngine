"""v142 -- supplier_facilities.phone for 21 CFR 1.1310 (A-2190).

Revision ID: e5cd73f8d1bb
Revises: 08c7cf36ddbe  (v141 traceability_events_append_only)
Create Date: 2026-10-31

Adds an optional business phone on supplier_facilities so a Facility location
description can carry name + phone + address (or a GLN stand-in). Nullable so
existing rows stay valid; UI and API accept phone on create.

Additive. Synthetic fixtures only until SEL-590 clears.

Note: #3717's fsma.traceability_events append-only trigger landed on main as
v141 (08c7cf36ddbe); this migration chains after it and does not vendor it.
Earlier, shipping it as a side-effect of the phone
column caused Live DB suite CheckViolation failures on intentional tamper
UPDATEs (append-only policy), which phone ADD COLUMN never touches.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5cd73f8d1bb"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "08c7cf36ddbe"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "supplier_facilities",
        sa.Column("phone", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    # Destructive: deletes every stored facility phone. Back up
    # supplier_facilities.phone first if those values must be kept.
    op.drop_column("supplier_facilities", "phone")
