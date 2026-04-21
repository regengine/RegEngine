"""v060: add replay_attempts and replayed_at to dlq.webhook_failures (#1192).

Revision ID: eaba6af7ae2c
Revises: f5a6b7c8d9e0
Create Date: 2026-04-20

Forward-port of the quarantined migration
``docs/abandoned_migrations_20260420_incident/20260420_v073_dlq_replay_columns_1192.py``
which was orphaned by the 2026-04-20 revision-graph incident.

Why
---
The DLQ (``dlq.webhook_failures``) had no replay tracking -- once a
webhook was marked "dead" it became a permanent graveyard with no
audit trail.

This migration adds two columns so the admin replay endpoint can:

  * Count how many times an operator has manually replayed a record
    (``replay_attempts``)
  * Record when the most recent successful replay was issued
    (``replayed_at``)

Both default to NULL / 0 on existing rows so the migration is fully
backwards-compatible. Every DDL statement is guarded with
``IF NOT EXISTS`` so the migration is idempotent against any existing
state (dev DBs that already have the ORM-created table, fresh DBs
that don't, and partially-applied states).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "eaba6af7ae2c"
down_revision: Union[str, Sequence[str], None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure the dlq schema exists (it may not yet exist on fresh DBs that
    # have not run the webhook_dlq bootstrap).
    op.execute("CREATE SCHEMA IF NOT EXISTS dlq")

    # Create the table if it was never migrated (services/shared/webhook_dlq.py
    # created it via the ORM but there was no Alembic migration for the base
    # table).
    op.execute("""
        CREATE TABLE IF NOT EXISTS dlq.webhook_failures (
            id              UUID PRIMARY KEY,
            payload         JSONB NOT NULL,
            error_message   TEXT NOT NULL,
            retry_count     INTEGER NOT NULL DEFAULT 0,
            max_retries     INTEGER NOT NULL DEFAULT 5,
            next_retry_at   TIMESTAMPTZ,
            status          VARCHAR(20) NOT NULL DEFAULT 'pending',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            tenant_id       VARCHAR(36),
            source          VARCHAR(50)
        )
    """)

    # Add replay tracking columns (idempotent -- IF NOT EXISTS requires PG 9.6+).
    op.execute("""
        ALTER TABLE dlq.webhook_failures
            ADD COLUMN IF NOT EXISTS replay_attempts INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS replayed_at TIMESTAMPTZ
    """)

    # Partial index so operators can quickly find replayed vs never-replayed
    # records without scanning the whole table.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_dlq_webhook_failures_replayed_at
        ON dlq.webhook_failures (replayed_at)
        WHERE replayed_at IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS dlq.idx_dlq_webhook_failures_replayed_at")
    op.execute("""
        ALTER TABLE dlq.webhook_failures
            DROP COLUMN IF EXISTS replayed_at,
            DROP COLUMN IF EXISTS replay_attempts
    """)
