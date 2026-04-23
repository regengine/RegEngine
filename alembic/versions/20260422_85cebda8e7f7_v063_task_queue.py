"""v063 — forward-port fsma.task_queue (v050 creation + v059 hardening).

Restores the ``fsma.task_queue`` table that was dropped from the prod DB
during the 2026-04-20 alembic consolidation incident. Without it,
``server/workers/task_processor.py`` errors on every poll and any webhook
ingest that enqueues background work returns 500. See #1871.

Forward-ports:

* ``alembic/versions/20260329_task_queue_v050.py`` — table creation,
  indexes, and RLS policy.
* ``docs/abandoned_migrations_20260420_incident/20260417_task_queue_hardening_v059.py``
  — idempotency_key column + partial unique index (#1164), scheduled_at
  column + updated pending index (#1181), visibility_timeout_seconds
  column (#1210), and drops the orphaned pg_notify trigger (#1185).

Idempotent: every DDL uses ``IF NOT EXISTS`` / ``DROP IF EXISTS`` so the
migration is safe on envs where v050 or the v059 hardening may have run
before (older CI fixtures, local dev with older checkouts).

Revision ID: 85cebda8e7f7
Revises: 8374fa2eb35b
Create Date: 2026-04-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "85cebda8e7f7"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "8374fa2eb35b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS fsma")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.task_queue (
            id              BIGSERIAL PRIMARY KEY,
            task_type       TEXT NOT NULL,
            payload         JSONB NOT NULL DEFAULT '{}',
            status          TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'dead')),
            priority        INT NOT NULL DEFAULT 0,
            tenant_id       TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at      TIMESTAMPTZ,
            completed_at    TIMESTAMPTZ,
            attempts        INT NOT NULL DEFAULT 0,
            max_attempts    INT NOT NULL DEFAULT 3,
            last_error      TEXT,
            locked_by       TEXT,
            locked_until    TIMESTAMPTZ
        )
        """
    )

    # v059-hardening additive columns — safe on a brand-new table too.
    op.execute(
        """
        ALTER TABLE fsma.task_queue
        ADD COLUMN IF NOT EXISTS idempotency_key TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE fsma.task_queue
        ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        """
    )
    op.execute(
        """
        ALTER TABLE fsma.task_queue
        ADD COLUMN IF NOT EXISTS visibility_timeout_seconds INT
        """
    )

    # Pending-work index — must consider scheduled_at so retries with
    # backoff are not picked up before their retry time (#1181).
    # Drop any pre-existing narrower variant and recreate with the right
    # column order.
    op.execute("DROP INDEX IF EXISTS fsma.idx_task_queue_pending")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_task_queue_pending
        ON fsma.task_queue (scheduled_at ASC, priority DESC, created_at ASC)
        WHERE status = 'pending'
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_task_queue_tenant
        ON fsma.task_queue (tenant_id, status)
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_task_queue_locked
        ON fsma.task_queue (locked_until)
        WHERE status = 'processing'
        """
    )

    # Partial unique index for enqueue idempotency (#1164) — only enforced
    # when a caller supplies an idempotency_key.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_task_queue_idempotency
        ON fsma.task_queue (tenant_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )

    # #1185 — the v050 pg_notify trigger is intentionally NOT recreated.
    # The worker never LISTENed on the channel, so every INSERT fired a
    # NOTIFY to nobody. Worker is polling-only (500ms default). Drop any
    # stale trigger/function that may exist from a pre-consolidation DB.
    op.execute("DROP TRIGGER IF EXISTS task_queue_notify ON fsma.task_queue")
    op.execute("DROP FUNCTION IF EXISTS fsma.notify_new_task() CASCADE")

    # RLS — enabled regardless; policy references app.tenant_id GUC set
    # by the task-queue session context. Idempotent via IF-not-exists
    # pattern (Postgres lacks CREATE POLICY IF NOT EXISTS, so drop-then-
    # create).
    op.execute("ALTER TABLE fsma.task_queue ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_tasks ON fsma.task_queue")
    op.execute(
        """
        CREATE POLICY tenant_isolation_tasks ON fsma.task_queue
        USING (tenant_id::text = current_setting('app.tenant_id', true)
               OR current_setting('app.tenant_id', true) = '')
        """
    )


def downgrade() -> None:
    # Non-destructive: do not drop the table — if v050 already ran
    # somewhere, the rollback of this forward-port should leave the
    # schema intact. Callers who actually want to remove the table
    # should do so in a dedicated migration.
    op.execute("DROP POLICY IF EXISTS tenant_isolation_tasks ON fsma.task_queue")
    op.execute("DROP INDEX IF EXISTS fsma.idx_task_queue_idempotency")
    op.execute(
        "ALTER TABLE fsma.task_queue DROP COLUMN IF EXISTS visibility_timeout_seconds"
    )
    op.execute("ALTER TABLE fsma.task_queue DROP COLUMN IF EXISTS scheduled_at")
    op.execute("ALTER TABLE fsma.task_queue DROP COLUMN IF EXISTS idempotency_key")
