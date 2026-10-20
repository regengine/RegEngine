-- SEL-314: remove duplicate permissive RLS policies (Supabase advisor
-- "multiple_permissive_policies", 46 warnings across 12 tables).
--
-- 1) Eleven public.* tables each carried two PERMISSIVE policies for the
--    `authenticated` role: the Alembic-managed tenant policy (TO PUBLIC,
--    public.get_tenant_context(), fail-closed) and an out-of-band
--    `authenticated`-only policy that fell back to the placeholder tenant
--    00000000-0000-0000-0000-000000000001 when app.tenant_id was unset.
--    That tenant does not exist and no row carries it, and no client code
--    queries these tables through the Supabase client (only the
--    submit_assessment_lead RPC is called). Dropping the out-of-band policy
--    changes nothing for the backend (`regengine` role) and leaves the
--    `authenticated` role fail-closed through get_tenant_context().
-- 2) fsma.tenant_portal_links had an ALL policy (tenant isolation) and a
--    SELECT policy (portal-link token lookup) that both reach `regengine`.
--    They are replaced by one SELECT policy carrying both conditions and
--    per-command INSERT/UPDATE/DELETE policies with the tenant condition.
--    Effective access is unchanged. Predicates use the v096 CASE form:
--    public.get_tenant_context() raises when app.tenant_id is unset and
--    Postgres does not order OR operands, so the token and sysadmin arms
--    are tested first. The tenant policy is dropped under its v074 name
--    (live in production) and its v090 name (Alembic-built databases).
--
-- Idempotent. One transaction. 10s lock_timeout per table, as v126/v128.

BEGIN;

-- ---------------------------------------------------------------- 1
DO $sel314$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT * FROM (VALUES
            ('api_keys',                 'tenant_isolation_policy'),
            ('compliance_alerts',        'compliance_alerts_tenant_isolation'),
            ('compliance_status_log',    'compliance_status_log_tenant_isolation'),
            ('invites',                  'invites_tenant_isolation'),
            ('memberships',              'memberships_tenant_isolation'),
            ('review_items',             'tenant_isolation_policy'),
            ('roles',                    'roles_tenant_isolation'),
            ('sessions',                 'sessions_user_owns'),
            ('tenant_compliance_status', 'tenant_compliance_status_isolation'),
            ('tenant_product_profile',   'tenant_product_profile_isolation'),
            ('users',                    'users_own_data')
        ) AS t(tbl, pol)
    LOOP
        IF to_regclass('public.' || r.tbl) IS NULL THEN
            CONTINUE;
        END IF;
        EXECUTE 'SET LOCAL lock_timeout = ''10s''';
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', r.pol, r.tbl);
    END LOOP;
END
$sel314$;

-- ---------------------------------------------------------------- 2
DO $sel314_portal$
BEGIN
    IF to_regclass('fsma.tenant_portal_links') IS NULL THEN
        RETURN;
    END IF;
    EXECUTE 'SET LOCAL lock_timeout = ''10s''';

    DROP POLICY IF EXISTS portal_links_token_lookup             ON fsma.tenant_portal_links;
    DROP POLICY IF EXISTS tenant_isolation_portal_links         ON fsma.tenant_portal_links;
    DROP POLICY IF EXISTS tenant_isolation_tenant_portal_links  ON fsma.tenant_portal_links;
    DROP POLICY IF EXISTS portal_links_select                   ON fsma.tenant_portal_links;
    DROP POLICY IF EXISTS portal_links_insert                   ON fsma.tenant_portal_links;
    DROP POLICY IF EXISTS portal_links_update                   ON fsma.tenant_portal_links;
    DROP POLICY IF EXISTS portal_links_delete                   ON fsma.tenant_portal_links;

    -- SELECT: active portal token, else armed sysadmin, else tenant isolation.
    -- A portal-token session (token set, tenant unset, as inside
    -- fsma.get_active_portal_link_by_token) sees only the matching row: the
    -- third arm hides every other row instead of reaching the raising tenant
    -- arm. Tenant sessions carry an empty token (begin-hook baseline), skip
    -- that arm, and stay fail-hard. The tenant arm is reserved for the app
    -- roles, as the replaced ALL policy was; any other role gets only the
    -- token arm, which is what portal_links_token_lookup (TO PUBLIC) granted.
    CREATE POLICY portal_links_select ON fsma.tenant_portal_links
        FOR SELECT
        USING (
            CASE
                WHEN link_token = NULLIF((SELECT current_setting('app.portal_link_token', true)), '')
                     AND status = 'active'
                     AND expires_at > now()
                    THEN true
                WHEN (SELECT current_setting('regengine.is_sysadmin', true)) = 'true'
                     AND current_user = 'regengine_sysadmin'
                    THEN true
                WHEN NULLIF((SELECT current_setting('app.portal_link_token', true)), '') IS NOT NULL
                    THEN false
                WHEN current_user NOT IN ('regengine', 'regengine_sysadmin')
                    THEN false
                ELSE tenant_id = (SELECT public.get_tenant_context())
            END
        );

    CREATE POLICY portal_links_insert ON fsma.tenant_portal_links
        FOR INSERT TO regengine, regengine_sysadmin
        WITH CHECK (
            CASE
                WHEN (SELECT current_setting('regengine.is_sysadmin', true)) = 'true'
                     AND current_user = 'regengine_sysadmin'
                    THEN true
                ELSE tenant_id = (SELECT public.get_tenant_context())
            END
        );

    CREATE POLICY portal_links_update ON fsma.tenant_portal_links
        FOR UPDATE TO regengine, regengine_sysadmin
        USING (
            CASE
                WHEN (SELECT current_setting('regengine.is_sysadmin', true)) = 'true'
                     AND current_user = 'regengine_sysadmin'
                    THEN true
                ELSE tenant_id = (SELECT public.get_tenant_context())
            END
        )
        WITH CHECK (
            CASE
                WHEN (SELECT current_setting('regengine.is_sysadmin', true)) = 'true'
                     AND current_user = 'regengine_sysadmin'
                    THEN true
                ELSE tenant_id = (SELECT public.get_tenant_context())
            END
        );

    CREATE POLICY portal_links_delete ON fsma.tenant_portal_links
        FOR DELETE TO regengine, regengine_sysadmin
        USING (
            CASE
                WHEN (SELECT current_setting('regengine.is_sysadmin', true)) = 'true'
                     AND current_user = 'regengine_sysadmin'
                    THEN true
                ELSE tenant_id = (SELECT public.get_tenant_context())
            END
        );
END
$sel314_portal$;

COMMIT;
