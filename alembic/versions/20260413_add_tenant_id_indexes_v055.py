"""Add missing tenant_id indexes for RLS performance — #1011

Ensures every RLS-enabled table with a tenant_id column has a dedicated
index on that column.  Without these indexes, RLS policy checks
(current_setting('app.tenant_id')) do sequential scans, creating both
a performance issue and a timing-attack risk on large tenants.

Tables already indexed (no change needed):
  roles, memberships, audit_logs, invites, supplier_facilities,
  supplier_facility_ftl_categories, supplier_traceability_lots,
  supplier_cte_events, supplier_funnel_events, review_items

Tables needing indexes:
  fsma.fsma_audit_trail.tenant_id — queried by tenant in audit API
  fsma.cte_events.tenant_id — queried by tenant in traceability API

NOTE: public.users does NOT have a tenant_id column (users is a global
identity table; tenant association is via the memberships table).
The original migration incorrectly tried to index users.tenant_id.

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
    # NOTE: public.users has no tenant_id column (global identity table).
    # Tenant scoping is via the memberships join table, not a direct FK.
    # The original ix_users_tenant_id index was removed — it would crash
    # because the column does not exist.

    # Use IF NOT EXISTS so the migration is idempotent
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_fsma_audit_trail_tenant_id
        ON fsma.fsma_audit_trail (tenant_id);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_cte_events_tenant_id
        ON fsma.cte_events (tenant_id);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS fsma.ix_fsma_audit_trail_tenant_id;")
    op.execute("DROP INDEX IF EXISTS fsma.ix_cte_events_tenant_id;")
