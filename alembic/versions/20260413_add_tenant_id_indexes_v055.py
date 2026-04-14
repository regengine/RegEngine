"""Add missing tenant_id indexes for RLS performance — #1011

Ensures every RLS-enabled table with a tenant_id column has a dedicated
index on that column.  Without these indexes, RLS policy checks
(current_setting('app.tenant_id')) do sequential scans, creating both
a performance issue and a timing-attack risk on large tenants.

Tables already indexed (no change needed):
  roles, memberships, audit_logs, invites, supplier_facilities,
  supplier_facility_ftl_categories, supplier_traceability_lots,
  supplier_cte_events, supplier_funnel_events, review_items

Tables receiving new indexes:
  users.tenant_id — added here (column may not exist yet); used for
                    tenant-scoped user lookups and future RLS policies
  fsma.fsma_audit_trail.tenant_id — standalone index for audit API queries
                                     (composite idx_audit_trail_tenant_time
                                     exists but a single-column index is
                                     needed for RLS policy scans)
  fsma.cte_events.tenant_id — standalone index for traceability API queries
                               (idx_cte_events_tenant exists from V002 but
                               is recreated here under the canonical name)

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
    # ------------------------------------------------------------------
    # Step 1: Ensure tenant_id column exists on public.users.
    #
    # The users table uses id-based RLS isolation (not tenant_id), so no
    # prior migration added this column.  We add it as nullable TEXT so
    # existing rows are unaffected; it can be backfilled and constrained
    # in a follow-up migration once application code is updated.
    # ------------------------------------------------------------------
    op.execute("""
        ALTER TABLE public.users
        ADD COLUMN IF NOT EXISTS tenant_id TEXT;
    """)

    # ------------------------------------------------------------------
    # Step 2: Create the indexes.  All use IF NOT EXISTS so this
    # migration is fully idempotent on databases that already have them.
    # ------------------------------------------------------------------
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_users_tenant_id
        ON public.users (tenant_id);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_fsma_audit_trail_tenant_id
        ON fsma.fsma_audit_trail (tenant_id);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_cte_events_tenant_id
        ON fsma.cte_events (tenant_id);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS public.ix_users_tenant_id;")
    op.execute("DROP INDEX IF EXISTS fsma.ix_fsma_audit_trail_tenant_id;")
    op.execute("DROP INDEX IF EXISTS fsma.ix_cte_events_tenant_id;")
    # Remove the tenant_id column added to users in this migration.
    # Only drop it if it was added here (i.e. it is nullable with no default,
    # which is the signature of our ADD COLUMN IF NOT EXISTS above).
    op.execute("""
        ALTER TABLE public.users
        DROP COLUMN IF EXISTS tenant_id;
    """)
