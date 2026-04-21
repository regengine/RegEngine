"""Composite trace indexes on fsma.transformation_links — #1282.

``CanonicalEventStore.trace_forward`` / ``trace_backward`` issue one
``SELECT`` per BFS frontier node, filtering by
``(tenant_id, input_tlc)`` or ``(tenant_id, output_tlc)`` respectively.
With a wide transformation tree each traversal fans out to potentially
thousands of point-lookups; without composite indexes Postgres has to
use the tenant_id index and then filter, which scales poorly.

This migration adds two explicit composite indexes. Both include
``tenant_id`` as the leading column so the index stays compatible with
the RLS policy's ``tenant_id = get_tenant_context()`` predicate — the
planner can use the index-only path when the RLS qual matches.

Indexes are created with ``IF NOT EXISTS`` so the migration is
idempotent and safe to re-run. We do NOT use ``CONCURRENTLY`` because
Alembic runs migrations inside a transaction and ``CREATE INDEX
CONCURRENTLY`` cannot run inside one; in the current deployment the
transformation_links table is small enough (~thousands of rows) that
a brief lock is acceptable. If the table grows large enough to make
this problematic, a follow-up migration can redo the index build
concurrently out-of-band.

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
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'fsma' AND tablename = 'transformation_links'
            ) THEN
                RAISE NOTICE 'fsma.transformation_links does not exist - skipping index create';
                RETURN;
            END IF;

            -- Forward trace: WHERE tenant_id = :tid AND input_tlc = :tlc
            CREATE INDEX IF NOT EXISTS idx_transformation_links_tenant_input_tlc
                ON fsma.transformation_links (tenant_id, input_tlc);

            -- Backward trace: WHERE tenant_id = :tid AND output_tlc = :tlc
            CREATE INDEX IF NOT EXISTS idx_transformation_links_tenant_output_tlc
                ON fsma.transformation_links (tenant_id, output_tlc);
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'fsma' AND tablename = 'transformation_links'
            ) THEN
                RETURN;
            END IF;
            DROP INDEX IF EXISTS fsma.idx_transformation_links_tenant_input_tlc;
            DROP INDEX IF EXISTS fsma.idx_transformation_links_tenant_output_tlc;
        END $$;
        """
    )
