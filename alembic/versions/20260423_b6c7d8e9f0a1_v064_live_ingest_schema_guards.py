"""v064 — live webhook ingest schema guards.

Forward-port small schema pieces that existed in legacy/admin migrations
but were missing from the Alembic-only Railway production path. Without
these, ``POST /api/v1/webhooks/ingest`` can return an accepted response
while the transaction is later aborted by best-effort fan-out work.

Revision ID: b6c7d8e9f0a1
Revises: 85cebda8e7f7
Create Date: 2026-04-23
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, Sequence[str], None] = "85cebda8e7f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS fsma")

    # v054 forward-port: FDA 21 CFR 1.1455 entry timestamp for legacy CTE rows.
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('fsma.cte_events') IS NOT NULL THEN
                ALTER TABLE fsma.cte_events
                ADD COLUMN IF NOT EXISTS event_entry_timestamp TIMESTAMPTZ;

                COMMENT ON COLUMN fsma.cte_events.event_entry_timestamp
                IS 'FDA 21 CFR 1.1455 - when the record was entered into the system (distinct from event_timestamp)';

                UPDATE fsma.cte_events
                SET event_entry_timestamp = ingested_at
                WHERE event_entry_timestamp IS NULL
                  AND ingested_at IS NOT NULL;
            END IF;
        END $$;
        """
    )

    # Canonical writer uses ON CONFLICT (tenant_id, idempotency_key).
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('fsma.traceability_events') IS NOT NULL THEN
                CREATE UNIQUE INDEX IF NOT EXISTS ux_traceability_events_tenant_idempotency_key
                ON fsma.traceability_events (tenant_id, idempotency_key);
            END IF;
        END $$;
        """
    )

    # Admin Flyway V36 forward-port for Alembic-only environments.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS funnel_events (
            id BIGSERIAL PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            event_name TEXT NOT NULL CHECK (
                event_name IN (
                    'signup_completed',
                    'first_ingest',
                    'first_scan',
                    'first_nlp_query',
                    'checkout_started',
                    'payment_completed'
                )
            ),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, event_name)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_funnel_events_event_name
        ON funnel_events (event_name)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_funnel_events_created_at
        ON funnel_events (created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_funnel_events_tenant_created
        ON funnel_events (tenant_id, created_at DESC)
        """
    )


def downgrade() -> None:
    # Non-destructive forward-port: leave table/column data intact.
    op.execute("DROP INDEX IF EXISTS fsma.ux_traceability_events_tenant_idempotency_key")
