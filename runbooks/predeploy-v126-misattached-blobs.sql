-- =============================================================================
-- READ-ONLY pre-deploy check for Alembic v126 (c51d4898e0a2):
-- fsma.manifest_blobs rows that are not attached to an ingestion run of their
-- own tenant.
-- =============================================================================
--
-- WHY: v126 replaces the single-column run foreign key on fsma.manifest_blobs
--   with (ingestion_run_id, tenant_id) -> fsma.ingestion_runs(id, tenant_id).
--   If any existing blob points at a missing run or at another tenant's run,
--   the migration refuses with the row count and changes nothing. This lists
--   those rows (identifiers only, never raw_bytes) so they can be reviewed
--   before the deploy. Expected on production: no rows, because every CSV
--   upload failed before v126 (#3122).
--
-- WHICH SESSION: a provider superuser or BYPASSRLS session. Both tables are
--   FORCE ROW LEVEL SECURITY, so the NOBYPASSRLS schema owner is NOT a valid
--   reviewer by default: without app.tenant_id it errors, and with a tenant
--   set it sees no fsma.ingestion_runs rows at all (those policies are TO
--   regengine / regengine_sysadmin) and would report EVERY blob of that
--   tenant as misattached. Never delete evidence on the basis of such a run.
--   The guard below stops any session that cannot see every row.
--
--   Schema-owner alternative (takes ACCESS EXCLUSIVE locks on both tables
--   until the ROLLBACK, so run it only in a quiet window):
--
--     BEGIN;
--     SET LOCAL lock_timeout = '10s';
--     ALTER TABLE fsma.ingestion_runs NO FORCE ROW LEVEL SECURITY;
--     ALTER TABLE fsma.manifest_blobs NO FORCE ROW LEVEL SECURITY;
--     -- the SELECT from the section below
--     ROLLBACK;   -- restores FORCE ROW LEVEL SECURITY
--
-- HOW TO RUN:
--   psql "$PROVIDER_ADMIN_DATABASE_URL" -X -f runbooks/predeploy-v126-misattached-blobs.sql
--
-- EXPECTED: zero rows -> deploy. Any row -> v126 will refuse; investigate
--   each blob with its tenant before changing anything. After the deploy,
--   runbooks/verify-v126-runtime-grants.sql confirms the resulting posture.
--
-- SAFETY: one READ ONLY transaction, rolled back at the end.
-- =============================================================================

BEGIN TRANSACTION READ ONLY;
SET LOCAL search_path = pg_catalog, pg_temp;

DO $guard$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_roles
         WHERE rolname = current_user
           AND (rolsuper OR rolbypassrls)
    ) THEN
        RAISE EXCEPTION
            'run this as a provider superuser or BYPASSRLS session; role % cannot see every fsma.manifest_blobs / fsma.ingestion_runs row under FORCE RLS (schema-owner alternative: see the header of runbooks/predeploy-v126-misattached-blobs.sql)',
            current_user;
    END IF;
END
$guard$;

SELECT blob.ingestion_run_id,
       blob.tenant_id AS blob_tenant_id,
       run.tenant_id AS run_tenant_id  -- NULL: the run does not exist
  FROM fsma.manifest_blobs AS blob
  LEFT JOIN fsma.ingestion_runs AS run
    ON run.id = blob.ingestion_run_id
 WHERE run.id IS NULL
    OR run.tenant_id <> blob.tenant_id
 ORDER BY blob.tenant_id, blob.ingestion_run_id;

ROLLBACK;
