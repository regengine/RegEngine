"""SET search_path on SECURITY DEFINER functions — #1096.

Two Postgres functions are declared ``SECURITY DEFINER`` without an
explicit ``SET search_path`` clause. ``SECURITY DEFINER`` means the
function executes with the privileges of its owner (usually the
superuser who created it). If an attacker can create objects in any
schema on the function's effective ``search_path`` (typically
``public``), they can shadow built-in functions the function calls and
hijack execution with owner privileges — a classic privilege-escalation
vector documented in the Postgres manual.

Functions fixed here:

    audit.log_sysadmin_access()
        Trigger that inserts a row into ``audit.sysadmin_access_log``
        whenever a sysadmin-context session touches a protected table.
        Originally defined in v051 (with an `SET search_path TO fsma,
        public` at migration scope, not function scope) and recreated
        in v056 without any search_path clause.

    get_user_tenant_id()
        Resolves the current user's tenant via
        ``SELECT tenant_id FROM memberships WHERE user_id = auth.uid()``.
        Defined in v059 ``rls_fail_closed_hardening``.

Fix:
  Re-CREATE each function with the body unchanged but with an explicit
  ``SET search_path = pg_catalog, <schemas-it-needs>`` clause on the
  function definition. Putting ``pg_catalog`` first ensures built-ins
  like ``current_user``, ``current_setting``, ``inet_client_addr`` etc.
  are always resolved against the system catalog rather than a shadowed
  user object. The remaining schemas are the minimum the function body
  references.

This is a behavior-preserving change — the functions execute the exact
same SQL; they merely no longer inherit the caller's search_path.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-04-18
"""
from alembic import op

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # audit.log_sysadmin_access
    #
    # Body references:
    #   - audit.sysadmin_access_log  (INSERT target) — schema ``audit``
    #   - current_user, session_user, inet_client_addr,
    #     current_setting, pg_backend_pid  — all ``pg_catalog``
    #   - jsonb_build_object                          — ``pg_catalog``
    # Minimum search_path: pg_catalog, audit.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit.log_sysadmin_access()
        RETURNS TRIGGER AS $fn$
        BEGIN
            IF current_setting('regengine.is_sysadmin', true) = 'true'
               AND current_user = 'regengine_sysadmin' THEN
                INSERT INTO audit.sysadmin_access_log (table_name, operation, connection_info)
                VALUES (
                    TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME,
                    TG_OP,
                    jsonb_build_object(
                        'current_user', current_user,
                        'session_user', session_user,
                        'client_addr', inet_client_addr()::TEXT,
                        'application_name', current_setting('application_name', true),
                        'backend_pid', pg_backend_pid()
                    )
                );
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $fn$ LANGUAGE plpgsql SECURITY DEFINER
           SET search_path = pg_catalog, audit
        """
    )

    # ------------------------------------------------------------------
    # get_user_tenant_id
    #
    # Body references:
    #   - memberships     (SELECT) — typically ``public`` schema
    #   - auth.uid()      — Supabase ``auth`` schema
    #   - COALESCE, ::UUID cast — ``pg_catalog``
    # Minimum search_path: pg_catalog, auth, public.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION get_user_tenant_id()
        RETURNS UUID AS $fn$
        DECLARE
            user_tenant_id UUID;
        BEGIN
            SELECT tenant_id INTO user_tenant_id
            FROM memberships
            WHERE user_id = auth.uid()
            LIMIT 1;
            RETURN COALESCE(user_tenant_id, '00000000-0000-0000-0000-000000000001'::UUID);
        END;
        $fn$ LANGUAGE plpgsql SECURITY DEFINER
           SET search_path = pg_catalog, auth, public
        """
    )


def downgrade() -> None:
    # Restore the pre-migration function definitions — same bodies
    # without the SET search_path clause. Operators are discouraged
    # from running this in production; it reopens the function-shadowing
    # privilege-escalation vector.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit.log_sysadmin_access()
        RETURNS TRIGGER AS $fn$
        BEGIN
            IF current_setting('regengine.is_sysadmin', true) = 'true'
               AND current_user = 'regengine_sysadmin' THEN
                INSERT INTO audit.sysadmin_access_log (table_name, operation, connection_info)
                VALUES (
                    TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME,
                    TG_OP,
                    jsonb_build_object(
                        'current_user', current_user,
                        'session_user', session_user,
                        'client_addr', inet_client_addr()::TEXT,
                        'application_name', current_setting('application_name', true),
                        'backend_pid', pg_backend_pid()
                    )
                );
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $fn$ LANGUAGE plpgsql SECURITY DEFINER
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION get_user_tenant_id()
        RETURNS UUID AS $fn$
        DECLARE
            user_tenant_id UUID;
        BEGIN
            SELECT tenant_id INTO user_tenant_id
            FROM memberships
            WHERE user_id = auth.uid()
            LIMIT 1;
            RETURN COALESCE(user_tenant_id, '00000000-0000-0000-0000-000000000001'::UUID);
        END;
        $fn$ LANGUAGE plpgsql SECURITY DEFINER
        """
    )
