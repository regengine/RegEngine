"""Enforce NOT NULL tenant_id on fsma.fsma_audit_trail and fsma.task_queue

Closes **#1287**.

Both tables declare ``tenant_id TEXT`` nullable. With an RLS policy
comparing ``tenant_id::text = current_setting('app.tenant_id', true)``,
a row with ``tenant_id IS NULL`` never matches any tenant context
(NULL = anything → NULL → filtered). Such rows persist indefinitely,
invisible to every tenant, visible only via owner-bypass or
regengine_sysadmin. This breaks:

  - **Audit-trail integrity**: fsma_audit_trail is hash-chained; null
    rows hide from "where is tenant X's audit log" queries.
  - **Task loss / leakage**: task_queue rows with null tenant are
    invisible to tenant-scoped workers; they accumulate silently.
  - **FSMA 204 traceability defense**: audit events without tenant_id
    are not defensible in an FDA request-response cycle.

Backfill strategy:

  Rather than DELETE (unsafe — an auditor pulling these rows post hoc
  would see a gap), we backfill NULL rows with the reserved
  ``00000000-0000-0000-0000-000000000000`` tenant_id. This is the
  "orphan / pre-migration" tenant, distinct from the
  ``...000000000001`` sandbox tenant used by v059 as the legacy
  fallback.

  Operators who prefer DELETE can run it manually before this
  migration; the backfill is a no-op if no nulls remain.

After backfill, both columns are set NOT NULL. The tenant_id type
stays TEXT for compatibility — #1271 tracks the UUID migration
separately.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-04-17
"""
from alembic import op

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


# UUID reserved for orphaned rows whose tenant was lost before this
# migration ran. Distinct from the '...000000000001' sandbox tenant —
# that one is a CI fixture, whereas this one flags "never had a tenant".
_ORPHAN_TENANT_UUID = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    # --- fsma.fsma_audit_trail ---
    op.execute(
        f"""
        DO $$
        DECLARE
            orphan_count BIGINT;
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'fsma' AND tablename = 'fsma_audit_trail'
            ) THEN
                RAISE NOTICE 'fsma.fsma_audit_trail does not exist - skipping';
                RETURN;
            END IF;

            SELECT COUNT(*) INTO orphan_count
            FROM fsma.fsma_audit_trail
            WHERE tenant_id IS NULL;

            IF orphan_count > 0 THEN
                RAISE NOTICE 'Backfilling % NULL-tenant rows in fsma.fsma_audit_trail → %',
                    orphan_count, '{_ORPHAN_TENANT_UUID}';
                UPDATE fsma.fsma_audit_trail
                   SET tenant_id = '{_ORPHAN_TENANT_UUID}'
                 WHERE tenant_id IS NULL;
            END IF;

            EXECUTE 'ALTER TABLE fsma.fsma_audit_trail ALTER COLUMN tenant_id SET NOT NULL';
        END $$
        """
    )

    # --- fsma.task_queue ---
    op.execute(
        f"""
        DO $$
        DECLARE
            orphan_count BIGINT;
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'fsma' AND tablename = 'task_queue'
            ) THEN
                RAISE NOTICE 'fsma.task_queue does not exist - skipping';
                RETURN;
            END IF;

            SELECT COUNT(*) INTO orphan_count
            FROM fsma.task_queue
            WHERE tenant_id IS NULL;

            IF orphan_count > 0 THEN
                RAISE NOTICE 'Backfilling % NULL-tenant rows in fsma.task_queue → %',
                    orphan_count, '{_ORPHAN_TENANT_UUID}';
                UPDATE fsma.task_queue
                   SET tenant_id = '{_ORPHAN_TENANT_UUID}'
                 WHERE tenant_id IS NULL;
            END IF;

            EXECUTE 'ALTER TABLE fsma.task_queue ALTER COLUMN tenant_id SET NOT NULL';
        END $$
        """
    )


def downgrade() -> None:
    # Drop the NOT NULL constraint; do not un-backfill the orphan-tenant
    # rows (there's no way to know which rows originated as NULL).
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_tables
                       WHERE schemaname = 'fsma' AND tablename = 'fsma_audit_trail') THEN
                EXECUTE 'ALTER TABLE fsma.fsma_audit_trail ALTER COLUMN tenant_id DROP NOT NULL';
            END IF;
            IF EXISTS (SELECT 1 FROM pg_tables
                       WHERE schemaname = 'fsma' AND tablename = 'task_queue') THEN
                EXECUTE 'ALTER TABLE fsma.task_queue ALTER COLUMN tenant_id DROP NOT NULL';
            END IF;
        END $$
        """
    )
