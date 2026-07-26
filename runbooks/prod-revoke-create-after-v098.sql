-- =============================================================================
-- Revoke schema CREATE from the app role after alembic v098
-- Tracking: regengine/RegEngine#2461 (follow-up documented in
--           runbooks/prod-least-privilege-db-role.sql, SAFETY note)
-- =============================================================================
--
-- WHY:
--   The #2461 cutover had to leave two workarounds in place because four code
--   paths still ran CREATE TABLE/INDEX at runtime:
--     1. GRANT CREATE ON SCHEMA public/fsma/dlq/audit TO regengine, and
--     2. ownership of public.scheduler_seen_items / public.scheduler_job_runs
--        transferred to regengine (2026-07-26) so scheduler boot DDL worked.
--   Alembic v098 (8b2f4e6a9c31) moved all of that DDL into migrations and the
--   runtime DDL code paths were deleted. This script removes both workarounds.
--
-- WHEN TO RUN (ordering matters):
--   AFTER the deploy that contains v098 is live in prod — i.e. migrations have
--   run and no deployed code issues DDL anymore. Running it while pre-v098
--   code is still live breaks scheduler boot (its old init DDL needs table
--   ownership) and the incident/exchange first-use paths.
--
-- HOW TO RUN (as the superuser/migration role, e.g. `postgres`):
--   psql "$ADMIN_DATABASE_URL" -f runbooks/prod-revoke-create-after-v098.sql
--
-- SAFETY:
--   - Idempotent: ALTER OWNER / GRANT / REVOKE all converge on re-run.
--   - Does not touch regengine_sysadmin: it never held schema CREATE from the
--     #2461 runbook, and migrations run as the postgres owner role via
--     MIGRATIONS_DATABASE_URL.
-- =============================================================================

\set ON_ERROR_STOP on

-- 1. Return the scheduler tables to the migration owner role.
ALTER TABLE public.scheduler_seen_items OWNER TO postgres;
ALTER TABLE public.scheduler_job_runs OWNER TO postgres;

-- 2. Re-assert app-role DML: while regengine owned the tables its access was
--    implicit; after the ownership flip it needs explicit grants (v098 also
--    applies these, but re-assert here so this script is safe standalone).
GRANT SELECT, INSERT, UPDATE, DELETE ON public.scheduler_seen_items TO regengine;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.scheduler_job_runs TO regengine;

-- 3. Revoke schema CREATE from the app role — the reason runtime DDL had to
--    be tolerated in the first place.
DO $$
DECLARE
    sch text;
BEGIN
    FOREACH sch IN ARRAY ARRAY['fsma', 'public', 'dlq', 'audit'] LOOP
        IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = sch) THEN
            EXECUTE format('REVOKE CREATE ON SCHEMA %I FROM regengine', sch);
            RAISE NOTICE 'revoked CREATE on schema % from regengine', sch;
        END IF;
    END LOOP;
END
$$;

-- =============================================================================
-- VERIFICATION
-- =============================================================================

-- Expect create=f on every row.
SELECT nspname AS schema,
       has_schema_privilege('regengine', oid, 'CREATE') AS create
FROM pg_namespace
WHERE nspname IN ('public', 'fsma', 'dlq', 'audit')
ORDER BY nspname;

-- Expect owner=postgres for both scheduler tables.
SELECT c.relname AS "table", pg_get_userbyid(c.relowner) AS owner
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN ('scheduler_seen_items', 'scheduler_job_runs')
ORDER BY c.relname;

-- Expect t/t — the app role can still read and write scheduler state.
SELECT has_table_privilege('regengine', 'public.scheduler_seen_items', 'SELECT, INSERT, UPDATE, DELETE') AS seen_items_dml,
       has_table_privilege('regengine', 'public.scheduler_job_runs', 'SELECT, INSERT, UPDATE, DELETE') AS job_runs_dml;

-- Afterwards: restart the scheduler service and confirm a clean boot
-- (`railway logs` — expect state_manager_initialized, no permission errors).
