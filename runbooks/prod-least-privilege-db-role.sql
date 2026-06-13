-- =============================================================================
-- Production least-privilege application DB role (RLS enforcement)
-- Tracking: regengine/RegEngine#2461
-- =============================================================================
--
-- WHY:
--   Production currently connects as Postgres role `postgres`, which is
--   SUPERUSER + BYPASSRLS. Postgres unconditionally bypasses Row-Level Security
--   for such roles, so EVERY `fsma.*` tenant-isolation policy — and the
--   `set_tenant_guc_if_uuid` backstop — is INERT in prod. Cross-tenant
--   isolation currently rests solely on application `WHERE tenant_id` filters.
--
--   The RLS policies are written `FOR ALL TO regengine`, so the fix is to make
--   the application connect as a dedicated role named `regengine` that is
--   NOSUPERUSER + NOBYPASSRLS. Then the existing policies apply and the live
--   RLS test (services/shared/tests/test_rls_enforcement_live.py) will pass
--   against prod.
--
-- HOW TO RUN (do NOT commit secrets; run as a superuser, e.g. `postgres`):
--   1. Set the app password as a psql variable from your secret store:
--        psql "$ADMIN_DATABASE_URL" \
--          -v app_pw="$(railway variables -s Postgres --kv | grep ...)" \   # or paste
--          -f runbooks/prod-least-privilege-db-role.sql
--      (Or run interactively and `\set app_pw 'value'` before \i.)
--   2. Repoint each service's DATABASE_URL to connect as `regengine`
--      (same host/db, user=regengine, the password set below). Keep `postgres`
--      for migrations/DDL only.
--   3. Re-run the live RLS test against prod with the regengine DATABASE_URL.
--
-- SAFETY:
--   - Idempotent: safe to re-run. Creates the role if absent, otherwise ALTERs
--     its attributes; grants are additive.
--   - Grants are intentionally broad (SELECT/INSERT/UPDATE/DELETE) to preserve
--     current behavior and avoid breaking prod. TIGHTEN AFTER AUDIT — e.g. the
--     evidence tables are append-only (DB triggers block UPDATE/DELETE on
--     fsma.cte_events); DELETE can likely be revoked on most fsma tables.
--   - CREATE on schemas is granted because several endpoints do runtime DDL
--     (`CREATE TABLE IF NOT EXISTS` in exchange_api/incident_router/scheduler).
--     FOLLOW-UP: move that DDL into migrations, then REVOKE CREATE here.
-- =============================================================================

\set ON_ERROR_STOP on

-- 1. The application role: login-capable, but NOT superuser and NOT bypassrls.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
        ALTER ROLE regengine WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE INHERIT;
        RAISE NOTICE 'altered existing role regengine -> NOSUPERUSER NOBYPASSRLS';
    ELSE
        CREATE ROLE regengine WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE INHERIT;
        RAISE NOTICE 'created role regengine';
    END IF;
END
$$;

-- 2. Password — supplied via the :app_pw psql variable, never hard-coded here.
--    Comment this out if you manage the password by another mechanism.
ALTER ROLE regengine WITH PASSWORD :'app_pw';

-- 3. Database connect (resolved dynamically — no -v needed).
DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO regengine', current_database());
END
$$;

-- 4. Per-schema privileges. `public` holds get_tenant_context() + scheduler_*;
--    `fsma` is the main evidence schema; `dlq`/`audit` are used by a few paths.
DO $$
DECLARE
    sch text;
BEGIN
    FOREACH sch IN ARRAY ARRAY['fsma', 'public', 'dlq', 'audit'] LOOP
        IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = sch) THEN
            -- USAGE to reference; CREATE for runtime CREATE TABLE IF NOT EXISTS
            -- (see SAFETY note — revoke CREATE once runtime DDL is migrated out).
            EXECUTE format('GRANT USAGE, CREATE ON SCHEMA %I TO regengine', sch);
            EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO regengine', sch);
            EXECUTE format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA %I TO regengine', sch);
            EXECUTE format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA %I TO regengine', sch);
            -- Auto-grant on FUTURE objects created by the migration role (postgres).
            EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA %I GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO regengine', sch);
            EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA %I GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO regengine', sch);
            EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA %I GRANT EXECUTE ON FUNCTIONS TO regengine', sch);
            RAISE NOTICE 'granted privileges on schema %', sch;
        END IF;
    END LOOP;
END
$$;

-- 5. The RLS policies call public.get_tenant_context(); ensure EXECUTE
--    (covered by the loop above for schema public, but assert explicitly).
GRANT EXECUTE ON FUNCTION public.get_tenant_context() TO regengine;

-- =============================================================================
-- VERIFICATION (expect: super=f bypassrls=f, and the app can read its schema)
-- =============================================================================
SELECT rolname, rolsuper, rolbypassrls, rolcanlogin
FROM pg_roles WHERE rolname = 'regengine';

-- After repointing DATABASE_URL to regengine, prove enforcement from the app's
-- own role by running the integration test against prod:
--   DATABASE_URL=<regengine url> \
--     venv/bin/python -m pytest services/shared/tests/test_rls_enforcement_live.py -v
-- It should pass connecting directly as `regengine` (no transient probe role
-- needed once the app role is itself non-bypassrls).
