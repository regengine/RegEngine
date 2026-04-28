"""v069 — Phase C #2: Add tenant_id to 8 V31-era fsma tables; replace stale RLS policies.

Background
----------
Flyway V31__fsma_204_infrastructure.sql (2023-era) created eight fsma.*
tables with ``org_id UUID REFERENCES fsma.organizations(id)`` as the
isolation column and RLS policies that read the ``app.current_org_id``
GUC via ``fsma.current_org_id()``.

Two problems were introduced during the tenant-isolation convergence:

  1. The canonical GUC the application sets is ``app.tenant_id``
     (via ``set_tenant_guc`` / ``set_config('app.tenant_id', ...)``)
     — **not** ``app.current_org_id``.  The helper that reads
     ``app.current_org_id`` is never called, so
     ``fsma.current_org_id()`` always returns NULL.

  2. ``org_id = NULL`` is always FALSE in SQL, so every policy
     predicate silently denies all reads/writes for regular roles.
     Because V31 only sets ``ENABLE`` (not ``FORCE``) RLS, the
     superuser/owner role bypasses the policies entirely — meaning
     any session running as the table owner sees ALL tenants' rows.

This migration fixes both:

  * Adds ``tenant_id UUID NOT NULL`` to the seven tables that carry
    ``org_id``, back-filling from ``org_id`` (which the application
    already treats as the tenant UUID — see ``product_catalog.py``'s
    ``WHERE org_id = CAST(:tid AS uuid)`` pattern).

  * For ``fsma.key_data_elements`` (which has no ``org_id`` — it
    isolates via ``cte_id → critical_tracking_events``), updates the
    subquery in the policy to join on ``cte.tenant_id`` instead of
    ``cte.org_id``.

  * Drops the eight stale ``fsma_org_isolation_*`` policies and
    replaces them with ``tenant_isolation_*`` policies using
    ``get_tenant_context()::uuid`` (the canonical function, defined in
    V29__jwt_rls_integration.sql, that reads ``app.tenant_id``).

  * Adds ``FORCE ROW LEVEL SECURITY`` to all eight tables (V31 only
    had ``ENABLE``), closing the owner-bypass gap.

  * Adds covering tenant indexes and tenant-scoped unique indexes for
    tables that had ``UNIQUE(org_id, …)`` constraints (products, loca-
    tions, compliance_snapshots).

Tables affected
---------------
  fsma.products              org_id → tenant_id  (active in product_catalog.py)
  fsma.locations             org_id → tenant_id
  fsma.suppliers             org_id → tenant_id
  fsma.critical_tracking_events  org_id → tenant_id
  fsma.key_data_elements     policy only (no org_id column)
  fsma.audit_log             org_id → tenant_id
  fsma.recall_assessments    org_id → tenant_id
  fsma.compliance_snapshots  org_id → tenant_id

Companion change: ``services/ingestion/app/product_catalog.py`` updated
to query ``WHERE tenant_id = …`` and use ``ON CONFLICT (tenant_id, gtin)``
in the same PR.

Note: ``org_id`` columns and the ``UNIQUE(org_id, …)`` constraints are
intentionally left in place.  They will be dropped in Phase C #3 once
read paths are fully migrated off ``org_id``.

Note: ``fsma.compliance_alerts`` is **not** in scope — V053 already
replaced its V31 policy with a ``tenant_isolation_alerts`` policy;
that table's ``tenant_id`` column was added by a prior migration.

Revision ID: abc565b7dc47
Revises: f0a1b2c3d4e5
Create Date: 2026-04-24
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "abc565b7dc47"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Flyway V31 dependency guard
# ---------------------------------------------------------------------------
# This migration retrofits eight fsma.* tables originally created by
# Flyway V31__fsma_204_infrastructure.sql (2023-era).  Railway runs
# Alembic only, so on Railway-managed environments those tables don't
# exist and every ALTER / DROP POLICY in this migration would crash
# with ``relation "fsma.products" does not exist``.
#
# Same compatibility gap that v066 documented for its V30 trigger port.
# Resolution: probe one of the V31 tables up-front; if it's absent the
# whole migration is a no-op on this environment.  When V31 has been
# applied (legacy on-prem deployments that ran Flyway), the migration
# proceeds exactly as before.
#
# ``fsma.products`` is the canary because it's the first table the
# migration touched in the original (failing) ordering and because it
# carries the live ``WHERE tenant_id = ...`` query path in
# ``services/ingestion/app/product_catalog.py`` — if it ever does exist
# on a Railway env in the future, that's the table we'd care about.
_V31_CANARY = "fsma.products"


def _v31_present() -> bool:
    """True iff the Flyway V31 fsma.* tables are present in this DB.

    Uses ``to_regclass`` rather than ``information_schema.tables`` so
    the probe respects search_path and returns NULL (treated as False)
    for missing schemas as well as missing tables.
    """
    bind = op.get_bind()
    return bind.execute(
        text("SELECT to_regclass(:t)"), {"t": _V31_CANARY}
    ).scalar() is not None


# ---------------------------------------------------------------------------
# Upgrade helpers
# ---------------------------------------------------------------------------

# Policy body shared by all seven org_id tables.  The sysadmin branch
# mirrors the v056/v068 pattern: both the session variable AND the
# role must match to activate the bypass.
_POLICY_USING = """\
    tenant_id = get_tenant_context()::uuid
    OR (current_setting('regengine.is_sysadmin', true) = 'true'
        AND current_user = 'regengine_sysadmin')"""

_POLICY_KDE_USING = """\
    EXISTS (
        SELECT 1 FROM fsma.critical_tracking_events cte
        WHERE cte.id = key_data_elements.cte_id
          AND (
              cte.tenant_id = get_tenant_context()::uuid
              OR (current_setting('regengine.is_sysadmin', true) = 'true'
                  AND current_user = 'regengine_sysadmin')
          )
    )"""


def upgrade() -> None:
    if not _v31_present():
        # Alembic-only environment (e.g. Railway).  The V31 fsma.*
        # tables this migration retrofits don't exist here, so there's
        # nothing to alter.  Logged at INFO via ``RAISE NOTICE`` so the
        # deploy log records that the skip happened.
        op.execute(
            "DO $$ BEGIN "
            "RAISE NOTICE 'v069: Flyway V31 tables not present "
            "(canary fsma.products missing) — skipping retrofit'; "
            "END $$;"
        )
        return

    # ------------------------------------------------------------------
    # fsma.products
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE fsma.products ADD COLUMN IF NOT EXISTS tenant_id UUID")
    op.execute("UPDATE fsma.products SET tenant_id = org_id WHERE tenant_id IS NULL")
    op.execute("ALTER TABLE fsma.products ALTER COLUMN tenant_id SET NOT NULL")
    op.execute("ALTER TABLE fsma.products FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS fsma_org_isolation_products ON fsma.products")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_products ON fsma.products")
    op.execute(f"""
        CREATE POLICY tenant_isolation_products ON fsma.products
            FOR ALL TO regengine, regengine_sysadmin
            USING ({_POLICY_USING})
            WITH CHECK ({_POLICY_USING})
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_fsma_products_tenant ON fsma.products(tenant_id)"
    )
    # Tenant-scoped unique index; required for ON CONFLICT (tenant_id, gtin) in
    # product_catalog.py.  The legacy UNIQUE(org_id, gtin) constraint remains
    # until Phase C #3.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_fsma_products_tenant_gtin"
        " ON fsma.products(tenant_id, gtin)"
        " WHERE gtin IS NOT NULL AND gtin != ''"
    )

    # ------------------------------------------------------------------
    # fsma.locations
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE fsma.locations ADD COLUMN IF NOT EXISTS tenant_id UUID")
    op.execute("UPDATE fsma.locations SET tenant_id = org_id WHERE tenant_id IS NULL")
    op.execute("ALTER TABLE fsma.locations ALTER COLUMN tenant_id SET NOT NULL")
    op.execute("ALTER TABLE fsma.locations FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS fsma_org_isolation_locations ON fsma.locations")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_locations ON fsma.locations")
    op.execute(f"""
        CREATE POLICY tenant_isolation_locations ON fsma.locations
            FOR ALL TO regengine, regengine_sysadmin
            USING ({_POLICY_USING})
            WITH CHECK ({_POLICY_USING})
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_fsma_locations_tenant ON fsma.locations(tenant_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_fsma_locations_tenant_gln"
        " ON fsma.locations(tenant_id, gln)"
        " WHERE gln IS NOT NULL AND gln != ''"
    )

    # ------------------------------------------------------------------
    # fsma.suppliers
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE fsma.suppliers ADD COLUMN IF NOT EXISTS tenant_id UUID")
    op.execute("UPDATE fsma.suppliers SET tenant_id = org_id WHERE tenant_id IS NULL")
    op.execute("ALTER TABLE fsma.suppliers ALTER COLUMN tenant_id SET NOT NULL")
    op.execute("ALTER TABLE fsma.suppliers FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS fsma_org_isolation_suppliers ON fsma.suppliers")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_suppliers ON fsma.suppliers")
    op.execute(f"""
        CREATE POLICY tenant_isolation_suppliers ON fsma.suppliers
            FOR ALL TO regengine, regengine_sysadmin
            USING ({_POLICY_USING})
            WITH CHECK ({_POLICY_USING})
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_fsma_suppliers_tenant ON fsma.suppliers(tenant_id)"
    )

    # ------------------------------------------------------------------
    # fsma.critical_tracking_events
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE fsma.critical_tracking_events"
        " ADD COLUMN IF NOT EXISTS tenant_id UUID"
    )
    op.execute(
        "UPDATE fsma.critical_tracking_events"
        " SET tenant_id = org_id WHERE tenant_id IS NULL"
    )
    op.execute(
        "ALTER TABLE fsma.critical_tracking_events"
        " ALTER COLUMN tenant_id SET NOT NULL"
    )
    op.execute("ALTER TABLE fsma.critical_tracking_events FORCE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS fsma_org_isolation_cte"
        " ON fsma.critical_tracking_events"
    )
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_cte ON fsma.critical_tracking_events"
    )
    op.execute(f"""
        CREATE POLICY tenant_isolation_cte ON fsma.critical_tracking_events
            FOR ALL TO regengine, regengine_sysadmin
            USING ({_POLICY_USING})
            WITH CHECK ({_POLICY_USING})
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_fsma_cte_tenant"
        " ON fsma.critical_tracking_events(tenant_id)"
    )

    # ------------------------------------------------------------------
    # fsma.key_data_elements  (no org_id — isolation via cte_id → CTEs)
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE fsma.key_data_elements FORCE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS fsma_org_isolation_kdes ON fsma.key_data_elements"
    )
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_kdes ON fsma.key_data_elements"
    )
    op.execute(f"""
        CREATE POLICY tenant_isolation_kdes ON fsma.key_data_elements
            FOR ALL TO regengine, regengine_sysadmin
            USING ({_POLICY_KDE_USING})
            WITH CHECK ({_POLICY_KDE_USING})
    """)

    # ------------------------------------------------------------------
    # fsma.audit_log
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE fsma.audit_log ADD COLUMN IF NOT EXISTS tenant_id UUID")
    op.execute("UPDATE fsma.audit_log SET tenant_id = org_id WHERE tenant_id IS NULL")
    op.execute("ALTER TABLE fsma.audit_log ALTER COLUMN tenant_id SET NOT NULL")
    op.execute("ALTER TABLE fsma.audit_log FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS fsma_org_isolation_audit ON fsma.audit_log")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_audit_log ON fsma.audit_log")
    op.execute(f"""
        CREATE POLICY tenant_isolation_audit_log ON fsma.audit_log
            FOR ALL TO regengine, regengine_sysadmin
            USING ({_POLICY_USING})
            WITH CHECK ({_POLICY_USING})
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_fsma_audit_log_tenant ON fsma.audit_log(tenant_id)"
    )

    # ------------------------------------------------------------------
    # fsma.recall_assessments
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE fsma.recall_assessments ADD COLUMN IF NOT EXISTS tenant_id UUID"
    )
    op.execute(
        "UPDATE fsma.recall_assessments SET tenant_id = org_id WHERE tenant_id IS NULL"
    )
    op.execute(
        "ALTER TABLE fsma.recall_assessments ALTER COLUMN tenant_id SET NOT NULL"
    )
    op.execute("ALTER TABLE fsma.recall_assessments FORCE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS fsma_org_isolation_recall ON fsma.recall_assessments"
    )
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_recall_assessments"
        " ON fsma.recall_assessments"
    )
    op.execute(f"""
        CREATE POLICY tenant_isolation_recall_assessments ON fsma.recall_assessments
            FOR ALL TO regengine, regengine_sysadmin
            USING ({_POLICY_USING})
            WITH CHECK ({_POLICY_USING})
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_fsma_recall_assessments_tenant"
        " ON fsma.recall_assessments(tenant_id)"
    )

    # ------------------------------------------------------------------
    # fsma.compliance_snapshots
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE fsma.compliance_snapshots ADD COLUMN IF NOT EXISTS tenant_id UUID"
    )
    op.execute(
        "UPDATE fsma.compliance_snapshots SET tenant_id = org_id WHERE tenant_id IS NULL"
    )
    op.execute(
        "ALTER TABLE fsma.compliance_snapshots ALTER COLUMN tenant_id SET NOT NULL"
    )
    op.execute("ALTER TABLE fsma.compliance_snapshots FORCE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS fsma_org_isolation_snapshots ON fsma.compliance_snapshots"
    )
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_compliance_snapshots"
        " ON fsma.compliance_snapshots"
    )
    op.execute(f"""
        CREATE POLICY tenant_isolation_compliance_snapshots ON fsma.compliance_snapshots
            FOR ALL TO regengine, regengine_sysadmin
            USING ({_POLICY_USING})
            WITH CHECK ({_POLICY_USING})
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_fsma_compliance_snapshots_tenant"
        " ON fsma.compliance_snapshots(tenant_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_fsma_compliance_snapshots_tenant_date"
        " ON fsma.compliance_snapshots(tenant_id, snapshot_date)"
    )


def downgrade() -> None:
    # Drop tenant_isolation_* policies and tenant_id columns.
    # Re-creates the original fsma_org_isolation_* policies using
    # fsma.current_org_id() so the tables return to their V31 state
    # (ENABLE-only RLS, isolation via the legacy app.current_org_id GUC).
    # Note: app.current_org_id is never set by the current application,
    # so the restored policies will silently deny all reads for regular
    # roles — the same behaviour as before this migration.

    if not _v31_present():
        # Mirror the upgrade-side guard.  If V31 wasn't present we
        # never altered anything, so there's nothing to revert.
        op.execute(
            "DO $$ BEGIN "
            "RAISE NOTICE 'v069 downgrade: Flyway V31 tables not present "
            "— nothing to revert'; "
            "END $$;"
        )
        return

    # fsma.compliance_snapshots
    op.execute(
        "DROP INDEX IF EXISTS uq_fsma_compliance_snapshots_tenant_date"
    )
    op.execute(
        "DROP INDEX IF EXISTS idx_fsma_compliance_snapshots_tenant"
    )
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_compliance_snapshots"
        " ON fsma.compliance_snapshots"
    )
    op.execute("""
        CREATE POLICY fsma_org_isolation_snapshots ON fsma.compliance_snapshots
            USING (org_id = fsma.current_org_id())
            WITH CHECK (org_id = fsma.current_org_id())
    """)
    op.execute("ALTER TABLE fsma.compliance_snapshots NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fsma.compliance_snapshots DROP COLUMN IF EXISTS tenant_id")

    # fsma.recall_assessments
    op.execute("DROP INDEX IF EXISTS idx_fsma_recall_assessments_tenant")
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_recall_assessments"
        " ON fsma.recall_assessments"
    )
    op.execute("""
        CREATE POLICY fsma_org_isolation_recall ON fsma.recall_assessments
            USING (org_id = fsma.current_org_id())
            WITH CHECK (org_id = fsma.current_org_id())
    """)
    op.execute("ALTER TABLE fsma.recall_assessments NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fsma.recall_assessments DROP COLUMN IF EXISTS tenant_id")

    # fsma.audit_log
    op.execute("DROP INDEX IF EXISTS idx_fsma_audit_log_tenant")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_audit_log ON fsma.audit_log")
    op.execute("""
        CREATE POLICY fsma_org_isolation_audit ON fsma.audit_log
            USING (org_id = fsma.current_org_id())
            WITH CHECK (org_id = fsma.current_org_id())
    """)
    op.execute("ALTER TABLE fsma.audit_log NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fsma.audit_log DROP COLUMN IF EXISTS tenant_id")

    # fsma.key_data_elements
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_kdes ON fsma.key_data_elements"
    )
    op.execute("""
        CREATE POLICY fsma_org_isolation_kdes ON fsma.key_data_elements
            USING (
                EXISTS (
                    SELECT 1 FROM fsma.critical_tracking_events cte
                    WHERE cte.id = cte_id
                      AND cte.org_id = fsma.current_org_id()
                )
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1 FROM fsma.critical_tracking_events cte
                    WHERE cte.id = cte_id
                      AND cte.org_id = fsma.current_org_id()
                )
            )
    """)
    op.execute("ALTER TABLE fsma.key_data_elements NO FORCE ROW LEVEL SECURITY")

    # fsma.critical_tracking_events
    op.execute("DROP INDEX IF EXISTS idx_fsma_cte_tenant")
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_cte ON fsma.critical_tracking_events"
    )
    op.execute("""
        CREATE POLICY fsma_org_isolation_cte ON fsma.critical_tracking_events
            USING (org_id = fsma.current_org_id())
            WITH CHECK (org_id = fsma.current_org_id())
    """)
    op.execute(
        "ALTER TABLE fsma.critical_tracking_events NO FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE fsma.critical_tracking_events DROP COLUMN IF EXISTS tenant_id"
    )

    # fsma.suppliers
    op.execute("DROP INDEX IF EXISTS idx_fsma_suppliers_tenant")
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_suppliers ON fsma.suppliers"
    )
    op.execute("""
        CREATE POLICY fsma_org_isolation_suppliers ON fsma.suppliers
            USING (org_id = fsma.current_org_id())
            WITH CHECK (org_id = fsma.current_org_id())
    """)
    op.execute("ALTER TABLE fsma.suppliers NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fsma.suppliers DROP COLUMN IF EXISTS tenant_id")

    # fsma.locations
    op.execute("DROP INDEX IF EXISTS uq_fsma_locations_tenant_gln")
    op.execute("DROP INDEX IF EXISTS idx_fsma_locations_tenant")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_locations ON fsma.locations")
    op.execute("""
        CREATE POLICY fsma_org_isolation_locations ON fsma.locations
            USING (org_id = fsma.current_org_id())
            WITH CHECK (org_id = fsma.current_org_id())
    """)
    op.execute("ALTER TABLE fsma.locations NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fsma.locations DROP COLUMN IF EXISTS tenant_id")

    # fsma.products
    op.execute("DROP INDEX IF EXISTS uq_fsma_products_tenant_gtin")
    op.execute("DROP INDEX IF EXISTS idx_fsma_products_tenant")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_products ON fsma.products")
    op.execute("""
        CREATE POLICY fsma_org_isolation_products ON fsma.products
            USING (org_id = fsma.current_org_id())
            WITH CHECK (org_id = fsma.current_org_id())
    """)
    op.execute("ALTER TABLE fsma.products NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fsma.products DROP COLUMN IF EXISTS tenant_id")
