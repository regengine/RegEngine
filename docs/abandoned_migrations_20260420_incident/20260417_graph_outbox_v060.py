"""Add graph_outbox table for Postgres -> Neo4j write-ahead log (#1398).

Revision ID: a7b8c9d0e1f2
Revises: e4f5a6b7c8d9
Create Date: 2026-04-17

NOTE: this migration intentionally chains after v058 (e4f5a6b7c8d9, the
current head). Several in-flight PRs (#1437-family, #1444-family) have
staged their own ``f5a6b7c8d9e0`` migrations as v059 candidates. Whichever
of those merges first becomes the real v059; this migration then needs its
``down_revision`` rebased onto that SHA at merge time. The revision ID
itself (``a7b8c9d0e1f2``) is unique across the in-flight set to avoid the
revision-duplicate warning during rebase.

Why
---
Today every call site that mirrors state into Neo4j (``invite_routes.py``,
``supplier_facilities_routes.py``, ``supplier_funnel_routes.py``,
``bulk_upload/transaction_manager.py``) runs ``supplier_graph_sync.record_*``
**after** the Postgres transaction has committed. If Neo4j is down:

  * Postgres write lands.
  * Neo4j mirror is lost.
  * Only signal is a ``supplier_graph_sync_write_failed`` log line.
  * No outbox, no retry, no drift reconciler, no metric.

The fix is a write-ahead log. A caller enqueues a Postgres row describing
the Neo4j write inside the same session/transaction that made the Postgres
change. Commit atomically persists both. A separate drainer worker pulls
pending rows, runs them against Neo4j, and marks them ``drained`` on
success or bumps ``attempts`` + ``last_error`` on failure. Reconciliation
queries the oldest pending row to expose drift as a metric.

This migration adds the table only. The Python module and drainer live in
``services/admin/app/graph_outbox.py``. Existing call sites continue to
use the best-effort ``supplier_graph_sync`` path; adopting the outbox is a
per-caller migration that lands separately.

RLS
---
``graph_outbox`` is tenant-scoped — it carries a nullable ``tenant_id``
column. We enable RLS and add a tenant-isolation policy that mirrors the
``fsma.task_queue`` pattern from V050.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS graph_outbox (
            id              BIGSERIAL PRIMARY KEY,
            tenant_id       UUID NULL,
            operation       TEXT NOT NULL,
            cypher          TEXT NOT NULL,
            params          JSONB NOT NULL DEFAULT '{}',
            status          TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'drained', 'failed')),
            attempts        INTEGER NOT NULL DEFAULT 0,
            max_attempts    INTEGER NOT NULL DEFAULT 10,
            last_error      TEXT NULL,
            enqueued_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            drained_at      TIMESTAMPTZ NULL,
            next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            -- Idempotency guard: if the same (operation, dedupe_key) lands
            -- twice (e.g. client retry), we upsert instead of duplicating.
            dedupe_key      TEXT NULL
        )
    """)

    # Drainer pulls in (next_attempt_at, id) order, oldest eligible first.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_graph_outbox_pending
        ON graph_outbox (next_attempt_at ASC, id ASC)
        WHERE status = 'pending'
    """)

    # Tenant-scoped drift query: "how many pending rows for tenant X"
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_graph_outbox_tenant_status
        ON graph_outbox (tenant_id, status)
    """)

    # Dedupe lookup for idempotent upsert on retries.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_graph_outbox_dedupe
        ON graph_outbox (operation, dedupe_key)
        WHERE dedupe_key IS NOT NULL
    """)

    # Enable RLS (defense-in-depth against a future caller reading across
    # tenants). Pending/failed rows are tenant-scoped reads.
    op.execute("ALTER TABLE graph_outbox ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_graph_outbox ON graph_outbox
        USING (
            tenant_id IS NULL
            OR tenant_id::text = current_setting('app.tenant_id', true)
            -- Sysadmin bypass only effective on the sysadmin DB role,
            -- matching the V028/V056 pattern.
            OR (
                current_user = 'regengine_sysadmin'
                AND current_setting('regengine.is_sysadmin', true) = 'true'
            )
        )
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_graph_outbox ON graph_outbox")
    op.execute("DROP INDEX IF EXISTS uq_graph_outbox_dedupe")
    op.execute("DROP INDEX IF EXISTS idx_graph_outbox_tenant_status")
    op.execute("DROP INDEX IF EXISTS idx_graph_outbox_pending")
    op.execute("DROP TABLE IF EXISTS graph_outbox")
