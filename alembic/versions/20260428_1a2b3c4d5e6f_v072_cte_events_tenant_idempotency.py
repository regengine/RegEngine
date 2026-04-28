"""v072 — add tenant-scoped idempotency guard for legacy CTE events.

``CTEPersistence`` writes to ``fsma.cte_events`` with
``ON CONFLICT (tenant_id, idempotency_key) DO NOTHING``. Fresh Alembic
databases had only the legacy single-column idempotency constraint/index,
so live webhook ingest could reach the database and then fail with
``no unique or exclusion constraint matching the ON CONFLICT specification``.

Revision ID: 1a2b3c4d5e6f
Revises: 9d60e8724725
Create Date: 2026-04-28
"""
from typing import Sequence, Union

from alembic import op


revision: str = "1a2b3c4d5e6f"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "9d60e8724725"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS fsma")
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('fsma.cte_events') IS NULL THEN
                RAISE NOTICE 'v072: fsma.cte_events absent; skipping tenant idempotency guard';
                RETURN;
            END IF;

            ALTER TABLE fsma.cte_events
                DROP CONSTRAINT IF EXISTS cte_events_idempotency_key_key;

            CREATE UNIQUE INDEX IF NOT EXISTS ux_cte_events_tenant_idempotency_key
            ON fsma.cte_events (tenant_id, idempotency_key);
        END$$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS fsma.ux_cte_events_tenant_idempotency_key")
