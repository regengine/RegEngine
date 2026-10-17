"""Add campaign attribution to verified tool leads (v131).

Revision ID: 0a329588b824
Revises: 93eb33f262a1
Create Date: 2026-10-16

Chained after the INC-2 v128 head (93eb33f262a1) so the chain keeps a
single head.
"""

from alembic import op

revision = "0a329588b824"  # pragma: allowlist secret
down_revision = "93eb33f262a1"  # pragma: allowlist secret
branch_labels = None
depends_on = None

_COLUMNS = ("utm_source", "utm_medium", "utm_campaign")


def upgrade() -> None:
    for column in _COLUMNS:
        op.execute(f"ALTER TABLE public.tool_leads ADD COLUMN IF NOT EXISTS {column} VARCHAR(100)")


def downgrade() -> None:
    for column in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE public.tool_leads DROP COLUMN IF EXISTS {column}")
