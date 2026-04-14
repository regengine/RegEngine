"""Add missing tenant_id indexes for RLS performance — #1011

Ensures every RLS-enabled table with a tenant_id column has a dedicated
index on that column.  Without these indexes, RLS policy checks
(current_setting('app.tenant_id')) do sequential scans, creating both
a performance issue and a timing-attack risk on large tenants.

Tables needing indexes (if they exist on this database):
  fsma.fsma_audit_trail.tenant_id — queried by tenant in audit API
  fsma.cte_events.tenant_id — queried by tenant in traceability API

NOTE: public.users does NOT have a tenant_id column (users is a global
identity table; tenant association is via the memberships table).

NOTE: The fsma schema tables only exist on databases that run the
compliance/ingestion services.  The Worker and Admin services share the
same Alembic history but may not have these tables, so every statement
must guard with DO $$ ... IF EXISTS ... $$ to stay safe.

Revision ID: b1c2d3e4f5a6
Revises: a8b9c0d1e2f3
Create Date: 2026-04-13
"""
from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guard each index creation: only run if the target table actually
    # exists on this database.  Not all services have the fsma schema.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'fsma' AND table_name = 'fsma_audit_trail'
            ) THEN
                EXECUTE 'CREATE INDEX IF NOT EXISTS ix_fsma_audit_trail_tenant_id
                         ON fsma.fsma_audit_trail (tenant_id)';
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'fsma' AND table_name = 'cte_events'
            ) THEN
                EXECUTE 'CREATE INDEX IF NOT EXISTS ix_cte_events_tenant_id
                         ON fsma.cte_events (tenant_id)';
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS fsma.ix_fsma_audit_trail_tenant_id;")
    op.execute("DROP INDEX IF EXISTS fsma.ix_cte_events_tenant_id;")
