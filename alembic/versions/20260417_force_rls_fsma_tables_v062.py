"""FORCE ROW LEVEL SECURITY on the remaining tenant-scoped fsma.* tables

Closes **#1281** (completes the task_queue entry handled by v061).

v048, v049, and v050 created four tenant-scoped fsma tables with
``ENABLE ROW LEVEL SECURITY`` but without ``FORCE ROW LEVEL SECURITY``.
Without FORCE, the **table owner role bypasses RLS entirely**. If the
application connects as the table owner (or superuser, which is common
in legacy deploys), every RLS policy on these tables is silently
ineffective against that connection.

Affected tables:

  fsma.fda_sla_requests        — FDA 24-hour response SLA tracking
  fsma.chain_verification_log  — hash-chain integrity attestation log
  fsma.fsma_audit_trail        — hash-chained audit log (critical)
  fsma.task_queue              — (handled by v061)

Loss of FORCE on these tables is a cross-tenant leak of deal-breaking
regulatory and audit data.

Implementation:

  Each ALTER TABLE is emitted inside a DO block that checks the table
  exists and is not already FORCEd, so the migration is idempotent and
  can run on environments that never created these tables (e.g.,
  admin-only deployments) without raising.

Downgrade removes FORCE to restore the exact pre-migration state —
operators are strongly discouraged from running it in production.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-04-17
"""
from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


# Tables from v048 / v049 that need FORCE RLS. task_queue is handled by
# v061's rewrite; it's already FORCEd by the time this migration runs.
_FORCE_TABLES = [
    "fsma.fda_sla_requests",
    "fsma.chain_verification_log",
    "fsma.fsma_audit_trail",
]


def upgrade() -> None:
    for fq_table in _FORCE_TABLES:
        schema, table = fq_table.split(".", 1)
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_tables
                    WHERE schemaname = '{schema}' AND tablename = '{table}'
                ) THEN
                    EXECUTE 'ALTER TABLE {fq_table} FORCE ROW LEVEL SECURITY';
                ELSE
                    RAISE NOTICE 'Table {fq_table} does not exist — skipping FORCE RLS';
                END IF;
            END $$
            """
        )


def downgrade() -> None:
    for fq_table in _FORCE_TABLES:
        schema, table = fq_table.split(".", 1)
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_tables
                    WHERE schemaname = '{schema}' AND tablename = '{table}'
                ) THEN
                    EXECUTE 'ALTER TABLE {fq_table} NO FORCE ROW LEVEL SECURITY';
                END IF;
            END $$
            """
        )
