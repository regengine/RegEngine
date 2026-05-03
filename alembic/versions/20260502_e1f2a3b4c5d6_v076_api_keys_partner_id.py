"""v076 — add partner_id column to api_keys for partner gateway scoping.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-05-02

Adds a real ``partner_id`` column to ``api_keys`` so the partner gateway
can scope queries to a specific partner without consulting partner-
writable metadata. Previously the gateway pulled ``partner_id`` out of
``extra_data``, but ``update_key(metadata=...)`` lets a key holder
overwrite that field, which would let a compromised partner reassign
themselves to another partner's tenants. Promoting the field to a real
column closes that gap.

Includes a partial index on ``partner_id WHERE partner_id IS NOT NULL``
because the vast majority of keys are non-partner (internal admin keys,
direct customer keys) and a full index would be mostly empty.

Reversible.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c5d6"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent — safe to run twice if a partial deploy needs replay.
    op.execute(
        """
        ALTER TABLE api_keys
            ADD COLUMN IF NOT EXISTS partner_id VARCHAR(64)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_api_keys_partner_id
            ON api_keys (partner_id)
            WHERE partner_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_api_keys_partner_id")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS partner_id")
