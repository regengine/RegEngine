"""Add campaign attribution to verified tool leads (v131).

Revision ID: 0a329588b824
Revises: a5e7c9b2d341
Create Date: 2026-10-16

origin/main currently has two Alembic heads: a5e7c9b2d341 and the held v129
c4f0a7b6f8ee (INC-2). This migration extends a5e7c9b2d341 and adds no new
head. Before merging this PR after fix/inc2-alembic-heads merges, set
down_revision to 93eb33f262a1; that fix chains it onto a5e7c9b2d341 and
moves v129 to alembic/held.
"""

from alembic import op

revision = "0a329588b824"  # pragma: allowlist secret
down_revision = "a5e7c9b2d341"  # pragma: allowlist secret
branch_labels = None
depends_on = None

_COLUMNS = ("utm_source", "utm_medium", "utm_campaign")


def upgrade() -> None:
    for column in _COLUMNS:
        op.execute(f"ALTER TABLE public.tool_leads ADD COLUMN IF NOT EXISTS {column} VARCHAR(100)")


def downgrade() -> None:
    for column in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE public.tool_leads DROP COLUMN IF EXISTS {column}")
