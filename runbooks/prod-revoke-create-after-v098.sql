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
--   run and no deployed code issues DDL anymore — and only once you do NOT
--   anticipate rolling the app back to a pre-v098 image. Pre-v098 code cannot
--   run after this script: Postgres checks schema CREATE privilege BEFORE the
--   IF NOT EXISTS short-circuit, so the old scheduler boot DDL crash-loops
--   with "permission denied for schema public" even though the tables exist,
--   and the old incident/exchange endpoints (which ran ensure-table DDL on
--   every request) 500. To roll back past v098 anyway, run the ROLLBACK
--   section at the bottom first.
--
-- HOW TO RUN (as the superuser/migration role, e.g. `postgres`):
--   psql "$ADMIN_DATABASE_URL" -f runbooks/prod-revoke-create-after-v098.sql
--
-- SAFETY:
--   - Steps 1-3 run in ONE transaction: ALTER OWNER strips regengine's
--     owner-implicit privileges the moment it commits, so the re-GRANT must
--     land atomically with it — the scheduler is live and writing to these
--     tables while this runs. A mid-script failure rolls everything back.
--   - Idempotent: ALTER OWNER / GRANT / REVOKE all converge on re-run.
--   - Does not touch regengine_sysadmin: it never held schema CREATE from the
--     #2461 runbook, and migrations run as the postgres owner role via
--     MIGRATIONS_DATABASE_URL.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

-- 1. Return the scheduler tables to the migration owner role.
ALTER TABLE public.scheduler_seen_items OWNER TO postgres;
ALTER TABLE public.scheduler_job_runs OWNER TO postgres;

-- 2. Re-assert app-role DML in the same transaction: ALTER OWNER rewrites the
--    table ACL, replacing every reference to the old owner (as grantee AND
--    grantor) with the new one, which strips regengine's access entirely.
--    v098 also applies these grants, but its run predates the ownership flip.
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

COMMIT;

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

-- Expect t in every column for both rows. Checked per privilege:
-- has_table_privilege with a comma-separated list has ANY (OR) semantics
-- and would print t even if only SELECT survived.
SELECT t.tbl,
       has_table_privilege('regengine', t.tbl, 'SELECT') AS sel,
       has_table_privilege('regengine', t.tbl, 'INSERT') AS ins,
       has_table_privilege('regengine', t.tbl, 'UPDATE') AS upd,
       has_table_privilege('regengine', t.tbl, 'DELETE') AS del
FROM (VALUES ('public.scheduler_seen_items'), ('public.scheduler_job_runs')) AS t(tbl);

-- Afterwards: restart the scheduler service and confirm a clean boot
-- (`railway logs` — expect state_manager_initialized, no permission errors).

-- =============================================================================
-- ROLLBACK (only if the app must be rolled back to a PRE-v098 image)
-- =============================================================================
-- Reverses this script so the old runtime-DDL code paths work again.
-- Uncomment and run as the superuser, BEFORE deploying the pre-v098 image:
--
-- BEGIN;
-- DO $$
-- DECLARE
--     sch text;
-- BEGIN
--     FOREACH sch IN ARRAY ARRAY['fsma', 'public', 'dlq', 'audit'] LOOP
--         IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = sch) THEN
--             EXECUTE format('GRANT CREATE ON SCHEMA %I TO regengine', sch);
--         END IF;
--     END LOOP;
-- END
-- $$;
-- ALTER TABLE public.scheduler_seen_items OWNER TO regengine;
-- ALTER TABLE public.scheduler_job_runs OWNER TO regengine;
-- COMMIT;
