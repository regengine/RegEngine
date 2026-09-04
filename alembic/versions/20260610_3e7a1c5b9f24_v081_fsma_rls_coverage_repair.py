"""v081 — Close the fsma RLS coverage gaps left by the v078 forward-port.

Background
----------
The EPIC-B coverage gate (tests/migrations/test_rls_coverage.py) asserts
that every non-exempt ``fsma.*`` table has (1) ``tenant_id NOT NULL``,
(2) ``FORCE ROW LEVEL SECURITY`` and (3) a tenant-isolation policy.
On a fresh Alembic-only database three migrations leave gaps:

  * v078 forward-ported the Flyway V31 fsma tables (products, locations,
    suppliers, critical_tracking_events, key_data_elements, audit_log,
    recall_assessments, compliance_snapshots) with ``tenant_id UUID``
    *nullable*.  Its ``_tenant_rls`` helper added FORCE RLS + policies
    to the seven org_id tables, but never set NOT NULL, and skipped
    ``key_data_elements`` entirely (no tenant_id column → helper
    returns early).  v069 — which did all of this for Flyway-managed
    databases — no-ops on Alembic-only environments because its V31
    canary probe ran before v078 created the tables.

  * v080 (rule_rejections) enabled RLS but forgot ``FORCE``, so the
    table owner bypasses the tenant policy.

  * v078's ``_cte_kdes_jsonb`` conversion creates the quarantine log
    ``fsma.cte_kdes_backfill_log_v059`` with no RLS at all.  On legacy
    databases it can hold cross-tenant KDE values.

This migration:

  * Backfills ``tenant_id`` from ``org_id`` (idempotent — v078 already
    backfilled on legacy databases) and sets NOT NULL on the seven
    org_id tables.

  * Adds ``tenant_id UUID NOT NULL`` to ``fsma.key_data_elements``,
    backfilled from the parent ``critical_tracking_events`` row
    (``cte_id`` is NOT NULL with an FK, and the parent's tenant_id is
    made NOT NULL earlier in this migration, so the backfill is total).
    Adds FORCE RLS and a direct ``tenant_isolation_kdes`` policy,
    replacing v069's join-based policy where it exists.  The table has
    no live application write path (V31-era; the active KDE store is
    ``fsma.cte_kdes``), so requiring tenant_id breaks nothing.

  * Adds ``FORCE ROW LEVEL SECURITY`` to ``fsma.rule_rejections``.

  * Locks down ``fsma.cte_kdes_backfill_log_v059``: FORCE RLS with no
    policy (deny-all for non-superusers) and revokes PUBLIC access.
    It is a migration-internal artifact with no application read path;
    it stays exempt from the coverage gate (see TABLES_EXEMPT).

Policy predicates follow v078's ``_tenant_rls`` convention
(``tenant_id = get_tenant_context()``, no TO clause, no sysadmin
branch) — get_tenant_context() is created by v056 on Alembic-only
environments and by Flyway V29 elsewhere.

Revision ID: 3e7a1c5b9f24
Revises: d2e3f4a5b6c7
Create Date: 2026-06-10
"""

from typing import Sequence, Union

from alembic import op

revision: str = "3e7a1c5b9f24"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Order matters: critical_tracking_events must be first so the
# key_data_elements backfill below can join on a NOT NULL parent
# tenant_id.
_ORG_ID_TABLES = (
    "critical_tracking_events",
    "products",
    "locations",
    "suppliers",
    "audit_log",
    "recall_assessments",
    "compliance_snapshots",
)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. tenant_id NOT NULL on the seven V31-era org_id tables.
    #    The backfill is a no-op on fresh databases (tables empty) and
    #    on legacy databases (v069/v078 already backfilled); it only
    #    matters for rows written with a NULL tenant_id since v078.
    # ------------------------------------------------------------------
    # The migration credential is deliberately NOBYPASSRLS.  These tables were
    # already FORCE-RLS in v078, so even their owner cannot run the repair DML
    # while FORCE is active.  Temporarily restore the normal owner semantics
    # inside this transactional migration, then force every table again after
    # both parent and child backfills are complete.
    for table in _ORG_ID_TABLES:
        op.execute(f"ALTER TABLE fsma.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"UPDATE fsma.{table} SET tenant_id = org_id WHERE tenant_id IS NULL")
        op.execute(f"ALTER TABLE fsma.{table} ALTER COLUMN tenant_id SET NOT NULL")

    # ------------------------------------------------------------------
    # 2. fsma.key_data_elements — direct tenant_id + FORCE RLS + policy.
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE fsma.key_data_elements ADD COLUMN IF NOT EXISTS tenant_id UUID")
    # v069 may already have forced this table on the legacy/Flyway lineage.
    op.execute("ALTER TABLE fsma.key_data_elements NO FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        UPDATE fsma.key_data_elements kde
        SET tenant_id = cte.tenant_id
        FROM fsma.critical_tracking_events cte
        WHERE cte.id = kde.cte_id
          AND kde.tenant_id IS NULL
        """
    )
    op.execute("ALTER TABLE fsma.key_data_elements ALTER COLUMN tenant_id SET NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_fsma_kde_tenant ON fsma.key_data_elements(tenant_id)")
    op.execute("ALTER TABLE fsma.key_data_elements ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fsma.key_data_elements FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS fsma_org_isolation_kdes ON fsma.key_data_elements")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_kdes ON fsma.key_data_elements")
    op.execute(
        """
        CREATE POLICY tenant_isolation_kdes ON fsma.key_data_elements
            FOR ALL
            USING (tenant_id = get_tenant_context())
            WITH CHECK (tenant_id = get_tenant_context())
        """
    )

    for table in _ORG_ID_TABLES:
        op.execute(f"ALTER TABLE fsma.{table} FORCE ROW LEVEL SECURITY")

    # ------------------------------------------------------------------
    # 3. fsma.rule_rejections — v080 enabled RLS but forgot FORCE.
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE fsma.rule_rejections FORCE ROW LEVEL SECURITY")

    # ------------------------------------------------------------------
    # 4. fsma.cte_kdes_backfill_log_v059 — deny-all lockdown.
    #    Guarded: v078 only creates the log when it actually converts
    #    fsma.cte_kdes.kde_value to JSONB, so the table may be absent.
    # ------------------------------------------------------------------
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('fsma.cte_kdes_backfill_log_v059') IS NOT NULL THEN
                EXECUTE 'ALTER TABLE fsma.cte_kdes_backfill_log_v059 ENABLE ROW LEVEL SECURITY';
                EXECUTE 'ALTER TABLE fsma.cte_kdes_backfill_log_v059 FORCE ROW LEVEL SECURITY';
                EXECUTE 'REVOKE ALL ON fsma.cte_kdes_backfill_log_v059 FROM PUBLIC';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Restores the Alembic-only (post-v080, fresh-DB) state. On
    # Flyway-managed databases v069's state (ENABLE RLS + join policy
    # on key_data_elements) is not reconstructed — v069's own downgrade
    # handles the Flyway lineage.
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('fsma.cte_kdes_backfill_log_v059') IS NOT NULL THEN
                EXECUTE 'ALTER TABLE fsma.cte_kdes_backfill_log_v059 NO FORCE ROW LEVEL SECURITY';
                EXECUTE 'ALTER TABLE fsma.cte_kdes_backfill_log_v059 DISABLE ROW LEVEL SECURITY';
            END IF;
        END $$;
        """
    )

    op.execute("ALTER TABLE fsma.rule_rejections NO FORCE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_kdes ON fsma.key_data_elements")
    op.execute("ALTER TABLE fsma.key_data_elements NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fsma.key_data_elements DISABLE ROW LEVEL SECURITY")
    op.execute("DROP INDEX IF EXISTS fsma.idx_fsma_kde_tenant")
    op.execute("ALTER TABLE fsma.key_data_elements DROP COLUMN IF EXISTS tenant_id")

    for table in reversed(_ORG_ID_TABLES):
        op.execute(f"ALTER TABLE fsma.{table} ALTER COLUMN tenant_id DROP NOT NULL")
