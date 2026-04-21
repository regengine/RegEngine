"""Task queue hardening — idempotency, retry backoff, per-type visibility timeout.

Closes the additive-DDL portions of:

* #1164 — enqueue_task idempotency key (nullable column + partial unique index)
* #1181 — retry backoff (``scheduled_at`` column so failed tasks can be
  deferred instead of immediately re-claimed)
* #1210 — per-task-type visibility timeout (``visibility_timeout_seconds``
  set at enqueue time so the worker's claim knows how long to hold)
* #1185 — drop the ``fsma.notify_new_task`` trigger + function. The
  worker never issued ``LISTEN task_queue``, so every INSERT fired a
  pg_notify whose only effect was wasted work. Worker is now polling-only
  with a 500ms default poll interval.

All column additions are nullable / default-valued so existing rows
remain valid and a rollback is a column drop.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-04-17
"""
from alembic import op

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # #1164 — idempotency key (nullable for backward compat)
    op.execute(
        """
        ALTER TABLE fsma.task_queue
        ADD COLUMN IF NOT EXISTS idempotency_key TEXT
        """
    )

    # Partial unique index: enforce (tenant_id, idempotency_key) uniqueness
    # only when a key is provided. Rows without a key remain unconstrained,
    # preserving the current enqueue behavior.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_task_queue_idempotency
        ON fsma.task_queue (tenant_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )

    # #1181 — scheduled_at so _fail_task can defer retries with backoff
    op.execute(
        """
        ALTER TABLE fsma.task_queue
        ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        """
    )

    # The pending-work index must consider scheduled_at so deferred rows
    # aren't picked up before their retry time.
    op.execute("DROP INDEX IF EXISTS fsma.idx_task_queue_pending")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_task_queue_pending
        ON fsma.task_queue (scheduled_at ASC, priority DESC, created_at ASC)
        WHERE status = 'pending'
        """
    )

    # #1210 — per-task-type visibility timeout set at enqueue time, so the
    # worker's claim SQL can use the row's own timeout without needing a
    # two-phase read/update.
    op.execute(
        """
        ALTER TABLE fsma.task_queue
        ADD COLUMN IF NOT EXISTS visibility_timeout_seconds INT
        """
    )

    # #1185 — drop the orphaned pg_notify trigger. The worker never
    # LISTENed for the channel, so every INSERT fired a NOTIFY to nobody.
    # Worker is polling-only now; dropping the trigger eliminates the
    # per-insert overhead and matches reality.
    op.execute("DROP TRIGGER IF EXISTS task_queue_notify ON fsma.task_queue")
    op.execute("DROP FUNCTION IF EXISTS fsma.notify_new_task() CASCADE")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS fsma.idx_task_queue_idempotency")
    op.execute("ALTER TABLE fsma.task_queue DROP COLUMN IF EXISTS idempotency_key")

    op.execute("DROP INDEX IF EXISTS fsma.idx_task_queue_pending")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_task_queue_pending
        ON fsma.task_queue (priority DESC, created_at ASC)
        WHERE status = 'pending'
        """
    )

    op.execute("ALTER TABLE fsma.task_queue DROP COLUMN IF EXISTS scheduled_at")
    op.execute(
        "ALTER TABLE fsma.task_queue DROP COLUMN IF EXISTS visibility_timeout_seconds"
    )

    # Re-create the pg_notify trigger + function for parity with v050,
    # even though nothing LISTENs to it in this codebase.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.notify_new_task()
        RETURNS TRIGGER AS $$
        BEGIN
            PERFORM pg_notify('task_queue', NEW.task_type || ':' || NEW.id::text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER task_queue_notify
        AFTER INSERT ON fsma.task_queue
        FOR EACH ROW EXECUTE FUNCTION fsma.notify_new_task()
        """
    )
