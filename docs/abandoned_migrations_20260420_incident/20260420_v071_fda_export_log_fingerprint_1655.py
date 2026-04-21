"""fsma.fda_export_log: add export_fingerprint + UNIQUE(tenant_id, fingerprint) — #1655.

EPIC-L (#1655) requires that a re-run of the same FDA export (same
tenant, same window, same filters, same content hash) does not produce
a second audit-log row. Without idempotency, a client that retries
after a transient 503 — or two operators who happen to run the same
canonical traceback in the same minute — inflate the export count
and pollute the FSMA 204 chain-of-custody with duplicates.

This migration:

* Adds a nullable ``export_fingerprint TEXT`` column to
  ``fsma.fda_export_log``. Nullable so legacy rows written before the
  EPIC-L code landed keep their existing shape; the app stops writing
  NULLs as soon as it's running against a schema that has the column.
* Creates a partial unique index ``idx_export_log_tenant_fingerprint``
  on ``(tenant_id, export_fingerprint)`` where the fingerprint is not
  null. Callers can hand the DB an ``ON CONFLICT (tenant_id,
  export_fingerprint) DO NOTHING`` clause to make the insert a no-op
  on the second attempt, and the application code then looks up the
  pre-existing row's id.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-04-20
"""
from alembic import op

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            -- Skip cleanly on stripped-down test DBs that never ran V002.
            IF NOT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'fsma' AND tablename = 'fda_export_log'
            ) THEN
                RAISE NOTICE 'fsma.fda_export_log does not exist — skipping #1655 fingerprint migration';
                RETURN;
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'fsma'
                  AND table_name = 'fda_export_log'
                  AND column_name = 'export_fingerprint'
            ) THEN
                ALTER TABLE fsma.fda_export_log
                    ADD COLUMN export_fingerprint TEXT;
                COMMENT ON COLUMN fsma.fda_export_log.export_fingerprint IS
                    'EPIC-L (#1655): stable hash over (tenant, type, tlc, window, count, export_hash). Paired with a partial UNIQUE index so retries are idempotent.';
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'fsma'
                  AND indexname = 'idx_export_log_tenant_fingerprint'
            ) THEN
                CREATE UNIQUE INDEX idx_export_log_tenant_fingerprint
                    ON fsma.fda_export_log (tenant_id, export_fingerprint)
                    WHERE export_fingerprint IS NOT NULL;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'fsma'
                  AND indexname = 'idx_export_log_tenant_fingerprint'
            ) THEN
                DROP INDEX fsma.idx_export_log_tenant_fingerprint;
            END IF;

            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'fsma'
                  AND table_name = 'fda_export_log'
                  AND column_name = 'export_fingerprint'
            ) THEN
                ALTER TABLE fsma.fda_export_log
                    DROP COLUMN export_fingerprint;
            END IF;
        END
        $$;
        """
    )
