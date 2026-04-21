"""RLS policies for fsma.transformation_links — #1217.

v057 created ``fsma.transformation_links`` and ran::

    ALTER TABLE fsma.transformation_links ENABLE ROW LEVEL SECURITY;
    ALTER TABLE fsma.transformation_links FORCE ROW LEVEL SECURITY;

but did not create any ``CREATE POLICY`` statements. With RLS
enabled+forced and no matching policies, Postgres returns zero rows
for every ``SELECT`` and rejects every ``INSERT/UPDATE/DELETE``,
regardless of tenant. The table silently behaves as an empty fortress.

``fsma.transformation_links`` backs Phase 2 lot-to-lot traceability
(transformation CTE adjacency). A TRANSFORMATION CTE that loses its
input/output lot linkage fails FSMA 204 traceability audits — either
the policy-less state silently drops writes, or the app connects as a
bypass role and defeats RLS altogether.

This migration adds the same tenant-isolation + sysadmin-branch policy
shape v056 installs on every other ``fsma.*`` tenant-scoped table,
plus the sysadmin audit trigger so cross-tenant reads are logged.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-04-18
"""
from alembic import op

revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # DO block wraps each statement so the migration is idempotent and
    # survives environments where v057 was never applied (e.g. tests
    # or partially-reset DBs).
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'fsma' AND tablename = 'transformation_links'
            ) THEN
                RAISE NOTICE 'fsma.transformation_links does not exist - skipping RLS policy create';
                RETURN;
            END IF;

            -- Drop any pre-existing partial policy to keep this idempotent.
            DROP POLICY IF EXISTS tenant_isolation_transformation_links
                ON fsma.transformation_links;

            CREATE POLICY tenant_isolation_transformation_links
                ON fsma.transformation_links
                FOR ALL TO regengine, regengine_sysadmin
                USING (
                    tenant_id = get_tenant_context()
                    OR (current_setting('regengine.is_sysadmin', true) = 'true'
                        AND current_user = 'regengine_sysadmin')
                )
                WITH CHECK (
                    tenant_id = get_tenant_context()
                    OR (current_setting('regengine.is_sysadmin', true) = 'true'
                        AND current_user = 'regengine_sysadmin')
                );

            -- Sysadmin-access audit trigger matches the v056 pattern
            -- so every cross-tenant read by a sysadmin session lands
            -- in audit.sysadmin_access_log.
            DROP TRIGGER IF EXISTS trg_audit_sysadmin_transformation_links
                ON fsma.transformation_links;
            CREATE TRIGGER trg_audit_sysadmin_transformation_links
                AFTER INSERT OR UPDATE OR DELETE ON fsma.transformation_links
                FOR EACH ROW EXECUTE FUNCTION audit.log_sysadmin_access();
        END $$;
        """
    )


def downgrade() -> None:
    # Dropping the policy does NOT re-open the table to broad reads —
    # RLS is still FORCEd by v057. The result is the pre-fix empty-
    # fortress state: every SELECT returns zero rows. Operators should
    # roll forward with a corrective migration rather than downgrade.
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'fsma' AND tablename = 'transformation_links'
            ) THEN
                RETURN;
            END IF;
            DROP TRIGGER IF EXISTS trg_audit_sysadmin_transformation_links
                ON fsma.transformation_links;
            DROP POLICY IF EXISTS tenant_isolation_transformation_links
                ON fsma.transformation_links;
        END $$;
        """
    )
