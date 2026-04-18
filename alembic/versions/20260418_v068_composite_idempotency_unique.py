"""Composite UNIQUE (tenant_id, idempotency_key) on event tables — #1248.

Both ``fsma.cte_events`` and ``fsma.traceability_events`` declare
``idempotency_key TEXT UNIQUE`` (a single-column unique constraint)
but several ``ON CONFLICT (tenant_id, idempotency_key) DO NOTHING``
writers target a **composite** arbiter — which fails at runtime with::

    there is no unique or exclusion constraint matching the ON CONFLICT
    specification

Call sites using the composite arbiter today:

  - services/shared/cte_persistence/core.py:354, 397, 738
  - services/shared/canonical_persistence/writer.py:_batch_insert_canonical_events
    (added by #1266)

In production this path has likely never fired because the pre-flight
idempotency SELECT catches the dupe first. But the webhook path for
#1248 depends on ``ON CONFLICT`` surviving cross-request races where
two concurrent batches both pass their local pre-flight dedup.

This migration adds a composite partial unique index
``(tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL`` on
both tables. The existing single-column ``UNIQUE`` is kept as
defense-in-depth against cross-tenant sha256 collisions (astronomically
rare) and so existing rows remain valid during the migration. Callers
that specify ``ON CONFLICT (tenant_id, idempotency_key)`` now have a
matching arbiter; callers that specify ``ON CONFLICT (idempotency_key)``
continue to work against the single-column constraint.

A follow-up migration may drop the single-column UNIQUE once every
caller is audited; that decision belongs with the cte_persistence
retirement work (#1335), not here.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-04-18
"""
from alembic import op

revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- cte_events: composite partial unique index -------------------
    # CREATE INDEX CONCURRENTLY would avoid a brief table lock but can't
    # run inside an Alembic migration transaction. Deployments with
    # large cte_events volumes should use zero-downtime migration
    # tooling; for the standard path, the ACCESS EXCLUSIVE the
    # CREATE UNIQUE INDEX takes is brief.
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'fsma' AND tablename = 'cte_events'
            ) THEN
                RAISE NOTICE 'fsma.cte_events does not exist - skipping';
                RETURN;
            END IF;

            -- Partial index so NULL idempotency_key rows (legacy, pre-
            -- idempotency) don't bloat the index and don't fail
            -- UNIQUE on multiple NULLs.
            CREATE UNIQUE INDEX IF NOT EXISTS
                idx_cte_events_tenant_idempotency_unique
                ON fsma.cte_events (tenant_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL;
        END $$;
        """
    )

    # --- traceability_events: same shape ------------------------------
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'fsma' AND tablename = 'traceability_events'
            ) THEN
                RAISE NOTICE 'fsma.traceability_events does not exist - skipping';
                RETURN;
            END IF;

            CREATE UNIQUE INDEX IF NOT EXISTS
                idx_trace_events_tenant_idempotency_unique
                ON fsma.traceability_events (tenant_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL;
        END $$;
        """
    )


def downgrade() -> None:
    # Safe to drop: the single-column UNIQUE continues to enforce
    # global uniqueness on idempotency_key, so no existing row becomes
    # invalid and no ON CONFLICT writer starts accepting duplicates
    # that were previously rejected. Callers using the composite
    # arbiter will again fail with "no matching unique or exclusion
    # constraint" — operators are encouraged to roll forward, not
    # backward.
    op.execute(
        "DROP INDEX IF EXISTS fsma.idx_cte_events_tenant_idempotency_unique"
    )
    op.execute(
        "DROP INDEX IF EXISTS fsma.idx_trace_events_tenant_idempotency_unique"
    )
