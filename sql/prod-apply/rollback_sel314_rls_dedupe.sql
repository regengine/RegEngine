-- alembic-revision: 1faec7148e78
-- rendered-from: alembic/versions/20261020_1faec7148e78_v134_sel314_rls_policy_dedupe.py (downgrade)
-- Rollback for apply_sel314_rls_dedupe.sql. Recreates the eleven out-of-band
-- `authenticated` policies exactly as they were observed on 2026-10-20 and
-- restores the two original fsma.tenant_portal_links policies.
-- Idempotent. One transaction.

BEGIN;

DO $sel314_rb$
DECLARE
    r RECORD;
    tenant_fallback CONSTANT text :=
        $q$tenant_id = COALESCE(NULLIF(current_setting('app.tenant_id', true), '')::uuid,
                                '00000000-0000-0000-0000-000000000001'::uuid)$q$;
BEGIN
    FOR r IN
        SELECT * FROM (VALUES
            ('api_keys',                 'tenant_isolation_policy',
             $q$tenant_id::uuid = COALESCE(NULLIF(current_setting('app.tenant_id', true), '')::uuid,
                                           '00000000-0000-0000-0000-000000000001'::uuid)$q$),
            ('compliance_alerts',        'compliance_alerts_tenant_isolation',        NULL),
            ('compliance_status_log',    'compliance_status_log_tenant_isolation',    NULL),
            ('invites',                  'invites_tenant_isolation',                  NULL),
            ('memberships',              'memberships_tenant_isolation',              NULL),
            ('review_items',             'tenant_isolation_policy',                   NULL),
            ('roles',                    'roles_tenant_isolation',                    NULL),
            ('sessions',                 'sessions_user_owns',    $q$user_id = (SELECT auth.uid())$q$),
            ('tenant_compliance_status', 'tenant_compliance_status_isolation',        NULL),
            ('tenant_product_profile',   'tenant_product_profile_isolation',          NULL),
            ('users',                    'users_own_data',        $q$id = (SELECT auth.uid())$q$)
        ) AS t(tbl, pol, expr)
    LOOP
        IF to_regclass('public.' || r.tbl) IS NULL
           OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            CONTINUE;
        END IF;
        EXECUTE 'SET LOCAL lock_timeout = ''10s''';
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', r.pol, r.tbl);
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR ALL TO authenticated USING (%s)',
            r.pol, r.tbl, COALESCE(r.expr, tenant_fallback)
        );
    END LOOP;
END
$sel314_rb$;

DO $sel314_rb_portal$
BEGIN
    IF to_regclass('fsma.tenant_portal_links') IS NULL THEN
        RETURN;
    END IF;
    EXECUTE 'SET LOCAL lock_timeout = ''10s''';

    DROP POLICY IF EXISTS portal_links_select ON fsma.tenant_portal_links;
    DROP POLICY IF EXISTS portal_links_insert ON fsma.tenant_portal_links;
    DROP POLICY IF EXISTS portal_links_update ON fsma.tenant_portal_links;
    DROP POLICY IF EXISTS portal_links_delete ON fsma.tenant_portal_links;
    DROP POLICY IF EXISTS portal_links_token_lookup     ON fsma.tenant_portal_links;
    DROP POLICY IF EXISTS tenant_isolation_portal_links ON fsma.tenant_portal_links;
    DROP POLICY IF EXISTS tenant_isolation_tenant_portal_links ON fsma.tenant_portal_links;

    CREATE POLICY portal_links_token_lookup ON fsma.tenant_portal_links
        FOR SELECT
        USING (
            link_token = NULLIF(current_setting('app.portal_link_token', true), '')
            AND status = 'active'
            AND expires_at > now()
        );

    CREATE POLICY tenant_isolation_portal_links ON fsma.tenant_portal_links
        FOR ALL TO regengine, regengine_sysadmin
        USING (
            tenant_id = (SELECT public.get_tenant_context())
            OR (
                (SELECT current_setting('regengine.is_sysadmin', true)) = 'true'
                AND current_user = 'regengine_sysadmin'
            )
        )
        WITH CHECK (
            tenant_id = (SELECT public.get_tenant_context())
            OR (
                (SELECT current_setting('regengine.is_sysadmin', true)) = 'true'
                AND current_user = 'regengine_sysadmin'
            )
        );
END
$sel314_rb_portal$;

COMMIT;
