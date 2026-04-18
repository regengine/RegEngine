"""Audit + restore tenant-isolation policies on RLS-enabled tables with none

Partially closes **#1227** and **#1247**.

#1227 flagged that v056 executes ``DROP FUNCTION get_tenant_context() CASCADE``
which silently drops every dependent RLS policy. v056 only recreates policies
for a fixed list of tables; any other table that had a policy referencing
``get_tenant_context()`` is left RLS-enabled but policy-less. With
``FORCE ROW LEVEL SECURITY``, a policy-less table returns **zero rows** to
every query from a non-bypass role.

#1247 documents the same underlying drift: v051 and v056 both consolidated
SQL_V048/V049/V050 work, so depending on migration history the final policy
shape on any given table is either v051's or v056's, but not predictable
from the migration DAG.

Fix approach:

  Rather than try to reconstruct the exact lost policy (we can't — the
  CASCADE left no audit trail), this migration scans ``pg_policies`` for
  any tenant-scoped table that:

    - Has ``tenant_id`` column.
    - Has ``relrowsecurity = true`` (ENABLE RLS).
    - Has **zero** policies attached.

  For each such table, it creates a standard ``tenant_isolation`` policy
  using ``get_tenant_context()`` with the sysadmin bypass branch, matching
  the shape v056 intended for every tenant-scoped core table.

  Tables that already have at least one policy are left alone — this
  migration never overwrites an existing one. It's a backstop, not a
  rewrite.

A log table ``audit.rls_policy_restoration_log`` records every restore
so operators can review what was added.

Downgrade drops any policy named ``tenant_isolation_restored`` but leaves
the log in place.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-04-17
"""
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure the audit schema exists (v056 creates it, but we want to be
    # resilient to partial-run environments).
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit.rls_policy_restoration_log (
            id              BIGSERIAL PRIMARY KEY,
            schema_name     TEXT NOT NULL,
            table_name      TEXT NOT NULL,
            policy_name     TEXT NOT NULL,
            restored_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            migration_rev   TEXT NOT NULL DEFAULT 'e1f2a3b4c5d6',
            reason          TEXT NOT NULL,
            UNIQUE (schema_name, table_name, policy_name)
        )
        """
    )

    # The audit-and-repair loop. We scan pg_class / pg_policies once and
    # generate the repair DDL dynamically inside a DO block. Only tables
    # that both (a) have a tenant_id column and (b) are RLS-enabled with
    # zero policies attached are touched.
    op.execute(
        """
        DO $$
        DECLARE
            rec RECORD;
            using_clause TEXT;
            policy_name TEXT := 'tenant_isolation_restored';
            has_sysadmin_role BOOLEAN;
            has_regengine_role BOOLEAN;
        BEGIN
            -- Resolve role availability once. Environments that never ran
            -- the sysadmin-defense-in-depth layer skip the TO clause.
            SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname = 'regengine')
              INTO has_regengine_role;
            SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin')
              INTO has_sysadmin_role;

            FOR rec IN
                SELECT
                    n.nspname      AS schema_name,
                    c.relname      AS table_name,
                    a.atttypid     AS tenant_id_type
                FROM pg_class c
                JOIN pg_namespace n ON c.relnamespace = n.oid
                JOIN pg_attribute a ON a.attrelid = c.oid
                    AND a.attname = 'tenant_id'
                    AND NOT a.attisdropped
                WHERE c.relkind = 'r'
                  AND c.relrowsecurity = TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM pg_policies p
                      WHERE p.schemaname = n.nspname
                        AND p.tablename = c.relname
                  )
                  -- Skip system schemas
                  AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'audit')
            LOOP
                -- Pick the right cast based on tenant_id's declared type.
                -- UUID column: tenant_id = get_tenant_context()
                -- TEXT column: tenant_id::uuid = get_tenant_context()
                IF rec.tenant_id_type = 'uuid'::regtype THEN
                    using_clause := 'tenant_id = get_tenant_context()';
                ELSE
                    using_clause := 'tenant_id::uuid = get_tenant_context()';
                END IF;

                IF has_regengine_role AND has_sysadmin_role THEN
                    EXECUTE format(
                        'CREATE POLICY %I ON %I.%I
                            FOR ALL TO regengine, regengine_sysadmin
                            USING (
                                %s
                                OR (current_setting(''regengine.is_sysadmin'', true) = ''true''
                                    AND current_user = ''regengine_sysadmin'')
                            )',
                        policy_name,
                        rec.schema_name,
                        rec.table_name,
                        using_clause
                    );
                ELSE
                    EXECUTE format(
                        'CREATE POLICY %I ON %I.%I FOR ALL USING (%s)',
                        policy_name,
                        rec.schema_name,
                        rec.table_name,
                        using_clause
                    );
                END IF;

                INSERT INTO audit.rls_policy_restoration_log
                    (schema_name, table_name, policy_name, reason)
                VALUES (
                    rec.schema_name, rec.table_name, policy_name,
                    '#1227/#1247: RLS-enabled table had zero policies, '
                    'restored default tenant_isolation policy'
                )
                ON CONFLICT (schema_name, table_name, policy_name)
                DO NOTHING;

                RAISE NOTICE
                    'Restored tenant_isolation policy on %.% (tenant_id type: %)',
                    rec.schema_name, rec.table_name,
                    (SELECT typname FROM pg_type WHERE oid = rec.tenant_id_type);
            END LOOP;
        END $$
        """
    )


def downgrade() -> None:
    # Drop any policy this migration restored, identified via the log.
    # Leave the log table in place so the history of restores is
    # preserved across downgrade/re-upgrade cycles.
    op.execute(
        """
        DO $$
        DECLARE
            rec RECORD;
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'audit'
                  AND tablename = 'rls_policy_restoration_log'
            ) THEN
                RAISE NOTICE 'Log table missing - nothing to downgrade';
                RETURN;
            END IF;

            FOR rec IN
                SELECT DISTINCT schema_name, table_name, policy_name
                FROM audit.rls_policy_restoration_log
                WHERE migration_rev = 'e1f2a3b4c5d6'
            LOOP
                EXECUTE format(
                    'DROP POLICY IF EXISTS %I ON %I.%I',
                    rec.policy_name, rec.schema_name, rec.table_name
                );
            END LOOP;
        END $$
        """
    )
