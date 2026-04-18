"""Restore tenant_isolation_memberships policy dropped by v056 (#1257)

Closes **#1257**.

v056 rls_hardening.py creates the memberships policy at lines 144-146::

    _rls_tables = [
        ...
        ("memberships", "tenant_isolation_memberships",
         "trg_audit_sysadmin_memberships",
         "tenant_id = get_tenant_context()"),
    ]

…then drops it 40 lines later at line 207::

    # Drop stale memberships policy
    op.execute("DROP POLICY IF EXISTS tenant_isolation_memberships ON memberships")

The "stale" comment referred to a pre-v056 policy, but v056 already
recreated a policy with the same name earlier in the same transaction.
The DROP removes the fresh policy. After v056 runs, `memberships` has:
  - RLS enabled + forced.
  - The audit trigger still attached.
  - **No tenant-isolation policy.**

With FORCE RLS, that means every query against `memberships` returns
zero rows unless executed as `regengine_sysadmin` with the bypass
flag. `memberships` is the user-to-tenant join table, so this breaks
login / session lookup for every regular-role connection.

The fix cannot be an in-place rewrite of v056 — v056 has already run
in production. A forward migration that re-creates the policy is the
safe path. Environments that haven't yet run v056 aren't affected
either: v063's CREATE POLICY IF NOT EXISTS-style idempotency means it
no-ops if the policy is already present.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-04-17
"""
from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Skip cleanly if the memberships table doesn't exist (e.g., in an
    # admin-only environment that never ran V27 or in a fresh DB where
    # the table is created by the admin migrations which may or may not
    # have been applied).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON c.relnamespace = n.oid
                WHERE c.relname = 'memberships'
                  AND n.nspname = ANY (current_schemas(false))
                  AND c.relkind = 'r'
            ) THEN
                RAISE NOTICE 'Table memberships does not exist - skipping #1257 fix';
                RETURN;
            END IF;

            -- Drop + create, matching the shape from v056 Part 2 so the
            -- restored policy is byte-identical to what v056 intended.
            DROP POLICY IF EXISTS tenant_isolation_memberships ON memberships;

            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine')
               AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                EXECUTE $policy$
                    CREATE POLICY tenant_isolation_memberships ON memberships
                        FOR ALL TO regengine, regengine_sysadmin
                        USING (
                            tenant_id = get_tenant_context()
                            OR (current_setting('regengine.is_sysadmin', true) = 'true'
                                AND current_user = 'regengine_sysadmin')
                        )
                $policy$;
            ELSE
                -- Fallback for envs without the sysadmin role split.
                EXECUTE $policy$
                    CREATE POLICY tenant_isolation_memberships ON memberships
                        FOR ALL
                        USING (tenant_id = get_tenant_context())
                $policy$;
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    # Drop the restored policy. The table is left RLS-enabled with only
    # the audit trigger — matching the broken post-v056 state that
    # prompted this fix. Operators should not downgrade past this.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON c.relnamespace = n.oid
                WHERE c.relname = 'memberships'
                  AND n.nspname = ANY (current_schemas(false))
                  AND c.relkind = 'r'
            ) THEN
                DROP POLICY IF EXISTS tenant_isolation_memberships ON memberships;
            END IF;
        END $$
        """
    )
