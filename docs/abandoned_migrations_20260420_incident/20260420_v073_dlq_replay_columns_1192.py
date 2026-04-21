"""Add replay_attempts and replayed_at to dlq.webhook_failures (#1192).

Revision ID: a1b2c3d4e5f6
Revises: f8a9b0c1d2e3
Create Date: 2026-04-20

Why
---
The DLQ (dlq.webhook_failures) had no replay tracking — once a webhook was
marked "dead" it became a permanent graveyard with no audit trail.

This migration adds two columns so the new admin replay endpoint can:
  * Count how many times an operator has manually replayed a record
    (``replay_attempts``)
  * Record when the most recent successful replay was issued
    (``replayed_at``)

These columns default to NULL/0 on existing rows so the migration is
fully backwards-compatible.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure the dlq schema exists (it may not yet exist on fresh DBs that
    # have not run the webhook_dlq bootstrap).
    op.execute("CREATE SCHEMA IF NOT EXISTS dlq")

    # Create the table if it was never migrated (shared/webhook_dlq.py created
    # it via the ORM but there was no Alembic migration for the base table).
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

    # Add replay tracking columns (idempotent — IF NOT EXISTS requires PG 9.6+).
    op.execute("""
        ALTER TABLE dlq.webhook_failures
            ADD COLUMN IF NOT EXISTS replay_attempts INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS replayed_at TIMESTAMPTZ
    """)

    # Index so operators can quickly find replayed vs never-replayed records.
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
