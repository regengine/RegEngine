"""Agreed sending time per supplier facility.

Mirrors supabase/migrations/20261024070000_supplier_agreed_sending_hours.sql
exactly: adds public.supplier_facilities.agreed_sending_hours, integer NULL,
CHECK (agreed_sending_hours > 0). No backfill. The supplier data quality view
counts a CTE record as late when it is received more than this many hours
after its event time.

Additive and idempotent (ADD COLUMN IF NOT EXISTS with an inline CHECK that is
only created together with the column), so the plain SQL file can run ahead of
it. Downgrade drops only what this revision created.

Revision ID: b005ddbf1dba
Revises: 41f96588d87c
Create Date: 2026-10-24
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b005ddbf1dba"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "41f96588d87c"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
alter table public.supplier_facilities
    add column if not exists agreed_sending_hours integer null
        constraint supplier_facilities_agreed_sending_hours_check
            check (agreed_sending_hours > 0);
"""
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE public.supplier_facilities DROP CONSTRAINT IF EXISTS supplier_facilities_agreed_sending_hours_check"
    )
    op.execute("ALTER TABLE public.supplier_facilities DROP COLUMN IF EXISTS agreed_sending_hours")
