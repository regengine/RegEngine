"""Task queue RLS fail-closed — remove empty-string bypass, add sysadmin branch

Closes **#1204**.

The v050 migration defined::

    CREATE POLICY tenant_isolation_tasks ON fsma.task_queue
    USING (tenant_id::text = current_setting('app.tenant_id', true)
           OR current_setting('app.tenant_id', true) = '')

The ``OR current_setting(...) = ''`` clause short-circuits the tenant
filter the moment ``app.tenant_id`` is unset or empty — any misconfigured
worker, raw psql session, or missing-middleware path reads every
tenant's task payloads (``task_queue.payload`` is JSONB and carries
extraction documents, PII, and cross-service messages).

This is a **distinct** fail-open pattern from #1091 (hardcoded UUID
fallback) and is not rewritten by v059's ``rls_fail_closed_hardening``
because that migration only targets policies matching the COALESCE
pattern. The task_queue policy uses a boolean OR against the raw
session variable.

Fix:
  1. Drop the v050 policy.
  2. Recreate it using ``get_tenant_context()`` (fail-hard) with an
     explicit, auditable sysadmin branch (same shape as v056 core
     policies).
  3. ``ALTER TABLE ... FORCE ROW LEVEL SECURITY`` — without FORCE the
     owner role bypasses RLS entirely (see companion issue #1281).
  4. Register a matching audit trigger so sysadmin reads of
     task_queue land in audit.sysadmin_access_log.

Downgrade restores the v050 fail-open policy so the chain is
symmetric, but operators should prefer fail-forward.

Revision ID: a7b8c9d0e1f2
Revises: f5a6b7c8d9e0
Create Date: 2026-04-17
"""
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Re-assert that get_tenant_context() exists as a fail-hard UUID
    # resolver. v056 defined it; v059's rls_fail_closed_hardening
    # re-creates it. Any future collision drift is caught here.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_proc p
                JOIN pg_namespace n ON p.pronamespace = n.oid
                WHERE p.proname = 'get_tenant_context'
                  AND n.nspname = 'public'
            ) THEN
                RAISE EXCEPTION
                    'get_tenant_context() missing — v056/v059 must run before v061';
            END IF;
        END $$
        """
    )

    # 1. Drop the v050 fail-open policy.
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_tasks ON fsma.task_queue"
    )

    # 2. Recreate the policy with fail-closed semantics and an explicit
    #    sysadmin bypass. The sysadmin branch requires BOTH
    #    ``regengine.is_sysadmin = 'true'`` AND the connection to use
    #    the ``regengine_sysadmin`` role, preventing a regular-role
    #    session from flipping the GUC to bypass isolation.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine')
               AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                EXECUTE $policy$
                    CREATE POLICY tenant_isolation_tasks ON fsma.task_queue
                        FOR ALL TO regengine, regengine_sysadmin
                        USING (
                            tenant_id::uuid = get_tenant_context()
                            OR (current_setting('regengine.is_sysadmin', true) = 'true'
                                AND current_user = 'regengine_sysadmin')
                        )
                        WITH CHECK (
                            tenant_id::uuid = get_tenant_context()
                            OR (current_setting('regengine.is_sysadmin', true) = 'true'
                                AND current_user = 'regengine_sysadmin')
                        )
                $policy$;
            ELSE
                -- Fall back to a policy without role scoping for envs that
                -- don't run the sysadmin-defense-in-depth layer yet
                -- (SQL_V048 / v051). Still fail-hard via get_tenant_context().
                EXECUTE $policy$
                    CREATE POLICY tenant_isolation_tasks ON fsma.task_queue
                        FOR ALL
                        USING (tenant_id::uuid = get_tenant_context())
                        WITH CHECK (tenant_id::uuid = get_tenant_context())
                $policy$;
            END IF;
        END $$
        """
    )

    # 3. FORCE RLS so the table owner can't bypass the policy. This also
    #    partially addresses #1281 for the task_queue entry.
    op.execute("ALTER TABLE fsma.task_queue FORCE ROW LEVEL SECURITY")

    # 4. Attach the sysadmin-access audit trigger if the function exists
    #    (it's created by v051 Part 2 / v056 Part 1). Skip when absent
    #    so environments that haven't run the sysadmin-defense-in-depth
    #    hardening still upgrade cleanly.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_proc p
                JOIN pg_namespace n ON p.pronamespace = n.oid
                WHERE p.proname = 'log_sysadmin_access'
                  AND n.nspname = 'audit'
            ) THEN
                DROP TRIGGER IF EXISTS trg_audit_sysadmin_task_queue
                    ON fsma.task_queue;
                CREATE TRIGGER trg_audit_sysadmin_task_queue
                    AFTER INSERT OR UPDATE OR DELETE ON fsma.task_queue
                    FOR EACH ROW EXECUTE FUNCTION audit.log_sysadmin_access();
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    # Restore the v050 policy exactly, so the chain is reversible.
    # NOTE: this re-introduces the #1204 fail-open — prefer forward-fix.
    op.execute("DROP TRIGGER IF EXISTS trg_audit_sysadmin_task_queue ON fsma.task_queue")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_tasks ON fsma.task_queue")
    op.execute("ALTER TABLE fsma.task_queue NO FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_tasks ON fsma.task_queue
        USING (tenant_id::text = current_setting('app.tenant_id', true)
               OR current_setting('app.tenant_id', true) = '')
        """
    )
