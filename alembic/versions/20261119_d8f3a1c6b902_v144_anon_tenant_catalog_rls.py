"""Close anonymous tenant/catalog reads and scope client reads to membership.

The verified hosted baseline still has PUBLIC tenant reads and an anon/catalog
read policy. Memberships must gain a context-free authenticated self-read before
either member lookup can work. Its legacy ALL policy is retained for backend
roles only: a permissive OR does not guarantee that PostgreSQL skips a raising
get_tenant_context() expression (see v111's membership policies).

Client tenant access becomes read-only. In particular, TRUNCATE is not protected
by RLS. Backend column grants from v139 and the role-and-flag sysadmin pattern
from v111 remain intact; no table-level tenant grant is added for regengine.
Catalog tenant IDs are text, so cast membership UUIDs to text, never catalog IDs
to UUID. Invalid/legacy catalog tenant strings simply cannot match a member.
The catalog, client roles and auth.uid() are Supabase-specific; absent client
identity surfaces are skipped on app-only databases (client reads stay denied). Existing tables still lose their legacy PUBLIC policies.
Authenticated membership reads require the existing memberships SELECT grants;
this revision does not expand grants or writes on the identity table.

Mirrors supabase/migrations/20261119120000_v144_anon_tenant_catalog_rls.sql.
NOT applied to production. Do not apply without C.Lee's explicit yes.
Downgrade intentionally restores the verified prior public exposure and grants.

Revision ID: d8f3a1c6b902
Revises: c4a9d2e761b0
Create Date: 2026-11-19
"""

from alembic import op

revision = "d8f3a1c6b902"  # pragma: allowlist secret
down_revision = "c4a9d2e761b0"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $memberships$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public' AND tablename = 'memberships'
                  AND policyname = 'tenant_isolation_memberships'
            ) THEN
                ALTER POLICY tenant_isolation_memberships ON public.memberships
                    TO regengine, regengine_sysadmin;
            END IF;
            DROP POLICY IF EXISTS memberships_authenticated_self_read ON public.memberships;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated')
               AND EXISTS (
                   SELECT 1 FROM pg_proc AS p
                   JOIN pg_namespace AS n ON n.oid = p.pronamespace
                   WHERE n.nspname = 'auth' AND p.proname = 'uid' AND p.pronargs = 0
               ) THEN
                CREATE POLICY memberships_authenticated_self_read ON public.memberships
                    FOR SELECT TO authenticated
                    USING (user_id = (SELECT auth.uid()));
            END IF;
        END
        $memberships$;
    """)
    op.execute("""
        DROP POLICY IF EXISTS tenants_read_all ON public.tenants;
        DROP POLICY IF EXISTS tenants_authenticated_member_read ON public.tenants;
        DO $client_read$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated')
               AND EXISTS (
                   SELECT 1 FROM pg_proc AS p
                   JOIN pg_namespace AS n ON n.oid = p.pronamespace
                   WHERE n.nspname = 'auth' AND p.proname = 'uid' AND p.pronargs = 0
               ) THEN
                CREATE POLICY tenants_authenticated_member_read ON public.tenants
                    FOR SELECT TO authenticated
                    USING (id IN (
                        SELECT m.tenant_id FROM public.memberships AS m
                        WHERE m.user_id = (SELECT auth.uid())
                    ));
            END IF;
        END
        $client_read$;

        -- Preserve v139 status/id reads and v111's existing sysadmin contract,
        -- including databases that still have only the legacy PUBLIC policies.
        -- Use a distinct name so downgrade leaves pre-existing v111 policies.
        DROP POLICY IF EXISTS tenants_backend_context_read ON public.tenants;
        CREATE POLICY tenants_backend_context_read ON public.tenants
            FOR SELECT TO regengine, regengine_sysadmin
            USING (
                CASE
                    WHEN current_user = 'regengine_sysadmin'
                         AND current_setting('regengine.is_sysadmin', true) = 'true'
                        THEN true
                    ELSE id = public.get_tenant_context()
                END
            );

        DROP POLICY IF EXISTS tenants_write_own ON public.tenants;
        CREATE POLICY tenants_write_own ON public.tenants
            FOR UPDATE TO regengine, regengine_sysadmin
            -- Global sysadmin writes remain authorized by v111's separate
            -- policy. Do not evaluate the raising helper on that path.
            USING (
                CASE
                    WHEN current_user = 'regengine_sysadmin'
                         AND current_setting('regengine.is_sysadmin', true) = 'true'
                        THEN false
                    ELSE id = public.get_tenant_context()
                END
            )
            WITH CHECK (
                CASE
                    WHEN current_user = 'regengine_sysadmin'
                         AND current_setting('regengine.is_sysadmin', true) = 'true'
                        THEN false
                    ELSE id = public.get_tenant_context()
                END
            );

        DO $client_grants$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                REVOKE SELECT, INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER, REFERENCES
                    ON TABLE public.tenants FROM anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                REVOKE INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER, REFERENCES
                    ON TABLE public.tenants FROM authenticated;
            END IF;
        END
        $client_grants$;
    """)
    op.execute("""
        DO $catalog$
        BEGIN
            IF to_regclass('public.product_catalog') IS NOT NULL THEN
                DROP POLICY IF EXISTS public_read_product_catalog ON public.product_catalog;
                DROP POLICY IF EXISTS product_catalog_authenticated_member_read ON public.product_catalog;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated')
                   AND EXISTS (
                       SELECT 1 FROM pg_proc AS p
                       JOIN pg_namespace AS n ON n.oid = p.pronamespace
                       WHERE n.nspname = 'auth' AND p.proname = 'uid' AND p.pronargs = 0
                   ) THEN
                    CREATE POLICY product_catalog_authenticated_member_read ON public.product_catalog
                        FOR SELECT TO authenticated
                        USING (tenant_id IN (
                            SELECT m.tenant_id::text FROM public.memberships AS m
                            WHERE m.user_id = (SELECT auth.uid())
                        ));
                END IF;
                ALTER TABLE public.product_catalog FORCE ROW LEVEL SECURITY;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                    REVOKE SELECT ON TABLE public.product_catalog FROM anon;
                END IF;
                -- service_role_full_access and service_role grants are untouched.
            END IF;
        END
        $catalog$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $catalog$
        BEGIN
            IF to_regclass('public.product_catalog') IS NOT NULL THEN
                DROP POLICY IF EXISTS product_catalog_authenticated_member_read ON public.product_catalog;
                DROP POLICY IF EXISTS public_read_product_catalog ON public.product_catalog;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon')
                   AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                    CREATE POLICY public_read_product_catalog ON public.product_catalog
                        FOR SELECT TO anon, authenticated USING (true);
                END IF;
                ALTER TABLE public.product_catalog NO FORCE ROW LEVEL SECURITY;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                    GRANT SELECT ON TABLE public.product_catalog TO anon;
                END IF;
            END IF;
        END
        $catalog$;
    """)
    op.execute("""
        DROP POLICY IF EXISTS tenants_authenticated_member_read ON public.tenants;
        DROP POLICY IF EXISTS tenants_backend_context_read ON public.tenants;
        DROP POLICY IF EXISTS tenants_read_all ON public.tenants;
        CREATE POLICY tenants_read_all ON public.tenants
            FOR SELECT TO PUBLIC USING (true);
        DROP POLICY IF EXISTS tenants_write_own ON public.tenants;
        CREATE POLICY tenants_write_own ON public.tenants
            FOR UPDATE TO PUBLIC
            USING (id = public.get_tenant_context())
            WITH CHECK (id = public.get_tenant_context());
        DO $client_grants$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER, REFERENCES
                    ON TABLE public.tenants TO anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER, REFERENCES
                    ON TABLE public.tenants TO authenticated;
            END IF;
        END
        $client_grants$;
    """)
    op.execute("""
        DROP POLICY IF EXISTS memberships_authenticated_self_read ON public.memberships;
        DO $memberships$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public' AND tablename = 'memberships'
                  AND policyname = 'tenant_isolation_memberships'
            ) THEN
                ALTER POLICY tenant_isolation_memberships ON public.memberships TO PUBLIC;
            END IF;
        END
        $memberships$;
    """)
