"""Add task_queue table to replace Kafka message broker.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-29 10:00:00.000000

PostgreSQL-native task queue using pg_notify for real-time delivery
and a polling fallback. Replaces three Kafka consumers:
  1. NLP extraction (topic: documents.ingested)
  2. Graph FSMA ingestion (topic: fsma.events.extracted)
  3. Admin review queue (topic: nlp.needs_review)
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS fsma")

    op.execute("""
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
    """)

    # Index for worker polling: fetch oldest pending tasks by priority
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_task_queue_pending
        ON fsma.task_queue (priority DESC, created_at ASC)
        WHERE status = 'pending'
    """)

    # Index for tenant-scoped queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_task_queue_tenant
        ON fsma.task_queue (tenant_id, status)
    """)

    # Index for stale lock detection
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_task_queue_locked
        ON fsma.task_queue (locked_until)
        WHERE status = 'processing'
    """)

    # Notify function — fires on INSERT so workers wake up immediately
    op.execute("""
        CREATE OR REPLACE FUNCTION fsma.notify_new_task()
        RETURNS TRIGGER AS $$
        BEGIN
            PERFORM pg_notify('task_queue', NEW.task_type || ':' || NEW.id::text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER task_queue_notify
        AFTER INSERT ON fsma.task_queue
        FOR EACH ROW EXECUTE FUNCTION fsma.notify_new_task()
    """)

    # Enable RLS for tenant isolation
    op.execute("ALTER TABLE fsma.task_queue ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_tasks ON fsma.task_queue
        USING (tenant_id::text = current_setting('app.tenant_id', true)
               OR current_setting('app.tenant_id', true) = '')
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS task_queue_notify ON fsma.task_queue")
    op.execute("DROP FUNCTION IF EXISTS fsma.notify_new_task()")
    op.execute("DROP TABLE IF EXISTS fsma.task_queue CASCADE")
