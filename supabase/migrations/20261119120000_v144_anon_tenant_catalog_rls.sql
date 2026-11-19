-- alembic-revision: d8f3a1c6b902
-- rendered-from: alembic/versions/20261119_d8f3a1c6b902_v144_anon_tenant_catalog_rls.py (upgrade)
-- v144: fail-closed tenant and product catalog client reads.
-- Membership self-read comes first; the legacy context policy stays backend-only.
-- Tenant clients become read-only; backend column grants and catalog service-role
-- access are unchanged. Catalog tenant text is compared with membership UUID text.
-- Idempotent. NOT applied to production. Do not apply without C.Lee's explicit yes.
-- Absent Supabase-only tables/client identity functions and roles are skipped on app-only databases.
-- Authenticated membership reads retain the existing memberships SELECT grants.

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
            ELSE id::text = NULLIF(current_setting('app.tenant_id', true), '')
        END
    );

DROP POLICY IF EXISTS tenants_write_own ON public.tenants;
CREATE POLICY tenants_write_own ON public.tenants
    FOR UPDATE TO regengine, regengine_sysadmin
    USING (
        CASE
            WHEN NULLIF(current_setting('app.tenant_id', true), '') IS NULL
                THEN false
            ELSE id = public.get_tenant_context()
        END
    )
    WITH CHECK (
        CASE
            WHEN NULLIF(current_setting('app.tenant_id', true), '') IS NULL
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

-- Downgrade (restores public exposure; run by hand only):
--
-- DO $catalog$
-- BEGIN
--     IF to_regclass('public.product_catalog') IS NOT NULL THEN
--         DROP POLICY IF EXISTS product_catalog_authenticated_member_read ON public.product_catalog;
--         DROP POLICY IF EXISTS public_read_product_catalog ON public.product_catalog;
--         IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon')
--            AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
--             CREATE POLICY public_read_product_catalog ON public.product_catalog
--                 FOR SELECT TO anon, authenticated USING (true);
--         END IF;
--         ALTER TABLE public.product_catalog NO FORCE ROW LEVEL SECURITY;
--         IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
--             GRANT SELECT ON TABLE public.product_catalog TO anon;
--         END IF;
--     END IF;
-- END
-- $catalog$;
--
-- DROP POLICY IF EXISTS tenants_authenticated_member_read ON public.tenants;
-- DROP POLICY IF EXISTS tenants_backend_context_read ON public.tenants;
-- DROP POLICY IF EXISTS tenants_read_all ON public.tenants;
-- CREATE POLICY tenants_read_all ON public.tenants
--     FOR SELECT TO PUBLIC USING (true);
-- DROP POLICY IF EXISTS tenants_write_own ON public.tenants;
-- CREATE POLICY tenants_write_own ON public.tenants
--     FOR UPDATE TO PUBLIC
--     USING (id = public.get_tenant_context())
--     WITH CHECK (id = public.get_tenant_context());
-- DO $client_grants$
-- BEGIN
--     IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
--         GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER, REFERENCES
--             ON TABLE public.tenants TO anon;
--     END IF;
--     IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
--         GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER, REFERENCES
--             ON TABLE public.tenants TO authenticated;
--     END IF;
-- END
-- $client_grants$;
--
-- DROP POLICY IF EXISTS memberships_authenticated_self_read ON public.memberships;
-- DO $memberships$
-- BEGIN
--     IF EXISTS (
--         SELECT 1 FROM pg_policies
--         WHERE schemaname = 'public' AND tablename = 'memberships'
--           AND policyname = 'tenant_isolation_memberships'
--     ) THEN
--         ALTER POLICY tenant_isolation_memberships ON public.memberships TO PUBLIC;
--     END IF;
-- END
-- $memberships$;
