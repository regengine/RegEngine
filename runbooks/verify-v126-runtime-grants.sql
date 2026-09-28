-- =============================================================================
-- READ-ONLY verification: runtime grants for CSV ingest + the agent worker
-- Alembic v126 (c51d4898e0a2) and the v111 inventory it extends.
-- =============================================================================
--
-- WHAT IT CHECKS (for the runtime role `regengine`, from the catalog only):
--   * POST /api/v1/ingest/csv can retain the upload: INSERT on exactly the
--     seven columns the route writes (not storage_url/created_at), nothing
--     else on fsma.manifest_blobs, and a validated (ingestion_run_id,
--     tenant_id) foreign key so a blob can only attach to its own tenant's run.
--   * The agent-artifact worker can write fsma.agent_artifacts and its
--     ingestion-run receipt: the narrow column SELECTs (including the
--     tenant-scoped ON CONFLICT arbiter), EXECUTE on the four pure helpers,
--     and the parent-run lock in the receipt trigger (so no UPDATE on the
--     append-only ledger is needed or present).
--   * The three digest() helpers are SECURITY DEFINER with search_path pinned
--     to pg_catalog, pg_temp, read no table, are owned by a NOSUPERUSER,
--     NOBYPASSRLS role that can reach pgcrypto, and are not executable by
--     PUBLIC. The runtime role needs no USAGE on pgcrypto's schema.
--   * RLS is still enabled + forced on all four tables, the role is still
--     NOSUPERUSER/NOBYPASSRLS, and the trigger functions are not SECURITY
--     DEFINER.
--   It reads no tenant rows.
--
-- HOW TO RUN (migration owner or postgres; any role that can read pg_catalog):
--   psql "$MIGRATIONS_DATABASE_URL" -X -f runbooks/verify-v126-runtime-grants.sql
--
-- EXPECTED:
--   BEFORE the deploy: the final `== READY` row has `ok = f`; the failing
--     rows name what is missing (manifest_blobs column INSERT and foreign key,
--     the column SELECTs, EXECUTE, the definer helpers, qualified digest,
--     parent-run lock).
--   AFTER the deploy (migrations + runtime-role cutover): every row, and the
--     `== READY` row, has `ok = t`. Run it again after the NEXT deploy too:
--     the cutover rebuilds grants and helpers on every deploy and must leave
--     them.
--
-- SAFETY: one READ ONLY transaction, rolled back at the end.
-- =============================================================================

BEGIN TRANSACTION READ ONLY;

SELECT version_num AS alembic_version FROM public.alembic_version;

WITH pgcrypto AS (
    SELECT n.nspname AS schema_name
      FROM pg_catalog.pg_extension AS e
      JOIN pg_catalog.pg_namespace AS n ON n.oid = e.extnamespace
     WHERE e.extname = 'pgcrypto'
),
fn AS (
    SELECT to_regprocedure('fsma.compute_agent_artifact_hash(jsonb)') AS artifact_hash,
           to_regprocedure('fsma.sha256_text_array_is_valid(text[])') AS sha_array,
           to_regprocedure('fsma.compute_ingestion_run_receipt_payload_hash(jsonb)') AS payload_hash,
           to_regprocedure(
               'fsma.compute_ingestion_run_receipt_hash(uuid,uuid,bigint,text,timestamptz,'
               'text,text,uuid,uuid,uuid,uuid,text,text)'
           ) AS receipt_hash,
           to_regprocedure('fsma.prepare_ingestion_run_receipt()') AS receipt_trigger,
           to_regprocedure('fsma.prepare_agent_artifact()') AS artifact_trigger
),
checks(sort_key, check_name, expected, actual) AS (
    SELECT 1, 'regengine is NOSUPERUSER', false, rolsuper FROM pg_roles WHERE rolname = 'regengine'
    UNION ALL SELECT 2, 'regengine is NOBYPASSRLS', false, rolbypassrls FROM pg_roles WHERE rolname = 'regengine'

    -- CSV upload retention (#3122)
    UNION ALL SELECT 10, 'manifest_blobs INSERT on the 7 columns the route writes', true,
        has_column_privilege('regengine', to_regclass('fsma.manifest_blobs'), 'ingestion_run_id', 'INSERT')
        AND has_column_privilege('regengine', to_regclass('fsma.manifest_blobs'), 'tenant_id', 'INSERT')
        AND has_column_privilege('regengine', to_regclass('fsma.manifest_blobs'), 'raw_bytes', 'INSERT')
        AND has_column_privilege('regengine', to_regclass('fsma.manifest_blobs'), 'sha256', 'INSERT')
        AND has_column_privilege('regengine', to_regclass('fsma.manifest_blobs'), 'original_filename', 'INSERT')
        AND has_column_privilege('regengine', to_regclass('fsma.manifest_blobs'), 'content_type', 'INSERT')
        AND has_column_privilege('regengine', to_regclass('fsma.manifest_blobs'), 'uploaded_by', 'INSERT')
    UNION ALL SELECT 11, 'manifest_blobs SELECT (any column) stays denied', false,
        has_any_column_privilege('regengine', to_regclass('fsma.manifest_blobs'), 'SELECT')
    UNION ALL SELECT 12, 'manifest_blobs UPDATE (any column) stays denied', false,
        has_any_column_privilege('regengine', to_regclass('fsma.manifest_blobs'), 'UPDATE')
    UNION ALL SELECT 13, 'manifest_blobs DELETE stays denied', false,
        has_table_privilege('regengine', to_regclass('fsma.manifest_blobs'), 'DELETE')
    UNION ALL SELECT 14, 'ingestion_runs INSERT + UPDATE (run open/close, receipt lock)', true,
        has_table_privilege('regengine', to_regclass('fsma.ingestion_runs'), 'INSERT')
        AND has_table_privilege('regengine', to_regclass('fsma.ingestion_runs'), 'UPDATE')
    UNION ALL SELECT 15, 'manifest_blobs table-wide INSERT stays denied', false,
        has_table_privilege('regengine', to_regclass('fsma.manifest_blobs'), 'INSERT')
    UNION ALL SELECT 16, 'manifest_blobs storage_url/created_at not insertable', false,
        has_column_privilege('regengine', to_regclass('fsma.manifest_blobs'), 'storage_url', 'INSERT')
        OR has_column_privilege('regengine', to_regclass('fsma.manifest_blobs'), 'created_at', 'INSERT')
    UNION ALL SELECT 17, 'manifest_blobs FK is (ingestion_run_id, tenant_id) -> ingestion_runs', true,
        EXISTS (
            SELECT 1 FROM pg_constraint
             WHERE conrelid = to_regclass('fsma.manifest_blobs') AND contype = 'f' AND convalidated
               AND confrelid = to_regclass('fsma.ingestion_runs')
               AND pg_get_constraintdef(oid) LIKE 'FOREIGN KEY (ingestion_run_id, tenant_id) REFERENCES fsma.ingestion_runs(id, tenant_id)%'
        )
        AND NOT EXISTS (
            SELECT 1 FROM pg_constraint
             WHERE conrelid = to_regclass('fsma.manifest_blobs') AND contype = 'f'
               AND pg_get_constraintdef(oid) LIKE 'FOREIGN KEY (ingestion_run_id) REFERENCES%'
        )

    -- Agent-artifact worker: fsma.agent_artifacts
    UNION ALL SELECT 20, 'agent_artifacts INSERT', true,
        has_table_privilege('regengine', to_regclass('fsma.agent_artifacts'), 'INSERT')
    UNION ALL SELECT 21, 'agent_artifacts SELECT (artifact_id, tenant_id) for ON CONFLICT', true,
        has_column_privilege('regengine', to_regclass('fsma.agent_artifacts'), 'artifact_id', 'SELECT')
        AND has_column_privilege('regengine', to_regclass('fsma.agent_artifacts'), 'tenant_id', 'SELECT')
    UNION ALL SELECT 22, 'agent_artifacts SELECT (artifact payload) stays denied', false,
        has_column_privilege('regengine', to_regclass('fsma.agent_artifacts'), 'artifact', 'SELECT')
    UNION ALL SELECT 23, 'agent_artifacts UPDATE/DELETE stay denied', false,
        has_any_column_privilege('regengine', to_regclass('fsma.agent_artifacts'), 'UPDATE')
        OR has_table_privilege('regengine', to_regclass('fsma.agent_artifacts'), 'DELETE')

    -- Agent-artifact worker: fsma.ingestion_run_receipts
    UNION ALL SELECT 30, 'receipts INSERT', true,
        has_table_privilege('regengine', to_regclass('fsma.ingestion_run_receipts'), 'INSERT')
    UNION ALL SELECT 31, 'receipts SELECT on trigger/RETURNING columns', true,
        has_column_privilege('regengine', to_regclass('fsma.ingestion_run_receipts'), 'receipt_id', 'SELECT')
        AND has_column_privilege('regengine', to_regclass('fsma.ingestion_run_receipts'), 'tenant_id', 'SELECT')
        AND has_column_privilege('regengine', to_regclass('fsma.ingestion_run_receipts'), 'ingestion_run_id', 'SELECT')
        AND has_column_privilege('regengine', to_regclass('fsma.ingestion_run_receipts'), 'sequence_num', 'SELECT')
        AND has_column_privilege('regengine', to_regclass('fsma.ingestion_run_receipts'), 'receipt_hash', 'SELECT')
    UNION ALL SELECT 32, 'receipts SELECT (metadata) stays denied', false,
        has_column_privilege('regengine', to_regclass('fsma.ingestion_run_receipts'), 'metadata', 'SELECT')
    UNION ALL SELECT 33, 'receipts UPDATE/DELETE stay denied (append-only)', false,
        has_any_column_privilege('regengine', to_regclass('fsma.ingestion_run_receipts'), 'UPDATE')
        OR has_table_privilege('regengine', to_regclass('fsma.ingestion_run_receipts'), 'DELETE')

    -- Helpers the invoker-rights triggers / CHECK evaluate as regengine
    UNION ALL SELECT 40, 'EXECUTE compute_agent_artifact_hash', true,
        has_function_privilege('regengine', (SELECT artifact_hash FROM fn), 'EXECUTE')
    UNION ALL SELECT 41, 'EXECUTE sha256_text_array_is_valid', true,
        has_function_privilege('regengine', (SELECT sha_array FROM fn), 'EXECUTE')
    UNION ALL SELECT 42, 'EXECUTE compute_ingestion_run_receipt_payload_hash', true,
        has_function_privilege('regengine', (SELECT payload_hash FROM fn), 'EXECUTE')
    UNION ALL SELECT 43, 'EXECUTE compute_ingestion_run_receipt_hash', true,
        has_function_privilege('regengine', (SELECT receipt_hash FROM fn), 'EXECUTE')
    -- The runtime role needs no USAGE on pgcrypto's schema: the three digest()
    -- helpers run as their owner. That owner must reach digest() instead.
    UNION ALL SELECT 44, 'digest() helpers are SECURITY DEFINER, search_path pg_catalog, pg_temp', true,
        (SELECT bool_and(prosecdef AND proconfig = ARRAY['search_path=pg_catalog, pg_temp'])
           FROM pg_proc
          WHERE oid IN ((SELECT artifact_hash FROM fn), (SELECT payload_hash FROM fn), (SELECT receipt_hash FROM fn)))
    UNION ALL SELECT 45, 'digest() helper owner has USAGE + EXECUTE on <pgcrypto>.digest(text,text)', true,
        (SELECT bool_and(
                    has_schema_privilege(proowner, (SELECT schema_name FROM pgcrypto), 'USAGE')
                    AND has_function_privilege(
                        proowner,
                        to_regprocedure(format('%I.digest(text,text)', (SELECT schema_name FROM pgcrypto))),
                        'EXECUTE'
                    ))
           FROM pg_proc
          WHERE oid IN ((SELECT artifact_hash FROM fn), (SELECT payload_hash FROM fn), (SELECT receipt_hash FROM fn)))
    UNION ALL SELECT 46, 'digest() helpers are owned by a NOSUPERUSER, NOBYPASSRLS role', true,
        (SELECT bool_and(NOT r.rolsuper AND NOT r.rolbypassrls)
           FROM pg_proc AS p JOIN pg_roles AS r ON r.oid = p.proowner
          WHERE p.oid IN ((SELECT artifact_hash FROM fn), (SELECT payload_hash FROM fn), (SELECT receipt_hash FROM fn)))
    UNION ALL SELECT 47, 'digest() helpers read no table (no FROM in their bodies)', true,
        (SELECT bool_and(prosrc !~* '\mfrom\M')
           FROM pg_proc
          WHERE oid IN ((SELECT artifact_hash FROM fn), (SELECT payload_hash FROM fn), (SELECT receipt_hash FROM fn)))
    UNION ALL SELECT 48, 'PUBLIC cannot EXECUTE the digest() helpers', false,
        EXISTS (
            SELECT 1
              FROM pg_proc AS p, aclexplode(p.proacl) AS acl
             WHERE p.oid IN ((SELECT artifact_hash FROM fn), (SELECT payload_hash FROM fn), (SELECT receipt_hash FROM fn))
               AND acl.grantee = 0
        )

    -- Function bodies (search_path independence, no ledger UPDATE, no definer)
    UNION ALL SELECT 50, 'receipt payload hash calls schema-qualified digest()', true,
        position(format('%I.digest(', (SELECT schema_name FROM pgcrypto))
                 IN pg_get_functiondef((SELECT payload_hash FROM fn))) > 0
    UNION ALL SELECT 51, 'receipt hash calls schema-qualified digest()', true,
        position(format('%I.digest(', (SELECT schema_name FROM pgcrypto))
                 IN pg_get_functiondef((SELECT receipt_hash FROM fn))) > 0
    UNION ALL SELECT 52, 'artifact hash calls schema-qualified digest() (v111)', true,
        position(format('%I.digest(', (SELECT schema_name FROM pgcrypto))
                 IN pg_get_functiondef((SELECT artifact_hash FROM fn))) > 0
    UNION ALL SELECT 53, 'receipt trigger locks the parent run (FOR NO KEY UPDATE)', true,
        position('FOR NO KEY UPDATE' IN pg_get_functiondef((SELECT receipt_trigger FROM fn))) > 0
    UNION ALL SELECT 54, 'receipt trigger is SECURITY INVOKER', false,
        (SELECT prosecdef FROM pg_proc WHERE oid = (SELECT receipt_trigger FROM fn))
    UNION ALL SELECT 55, 'artifact trigger is SECURITY INVOKER', false,
        (SELECT prosecdef FROM pg_proc WHERE oid = (SELECT artifact_trigger FROM fn))

    -- RLS posture unchanged
    UNION ALL SELECT 60 + row_number() OVER (ORDER BY c.relname),
        'RLS enabled + forced on fsma.' || c.relname, true,
        c.relrowsecurity AND c.relforcerowsecurity
      FROM pg_class AS c
      JOIN pg_namespace AS n ON n.oid = c.relnamespace
     WHERE n.nspname = 'fsma'
       AND c.relname IN ('manifest_blobs', 'agent_artifacts', 'ingestion_run_receipts', 'ingestion_runs')
    UNION ALL SELECT 70, 'regengine has tenant policies on all four tables', true,
        (SELECT count(DISTINCT tablename) = 4
           FROM pg_policies
          WHERE schemaname = 'fsma'
            AND tablename IN ('manifest_blobs', 'agent_artifacts', 'ingestion_run_receipts', 'ingestion_runs')
            AND (roles @> ARRAY['regengine']::name[] OR roles @> ARRAY['public']::name[])
            AND qual LIKE '%get_tenant_context()%')
),
evaluated AS (
    SELECT sort_key, check_name, expected, actual, actual IS NOT DISTINCT FROM expected AS ok
      FROM checks
)
SELECT check_name, expected, actual, ok
  FROM (
      SELECT sort_key, check_name, expected, actual, ok FROM evaluated
      UNION ALL
      SELECT 999, '== READY: every check ok (failing: ' || count(*) FILTER (WHERE NOT ok) || ')',
             true, bool_and(ok), bool_and(ok)
        FROM evaluated
  ) AS report
 ORDER BY sort_key;

-- Informational (not part of `ready`): where pgcrypto lives, whether the
-- runtime role could reach it directly (not required any more), and the
-- runtime role's configured search_path (NULL = server default).
SELECT (SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
         WHERE e.extname = 'pgcrypto') AS pgcrypto_schema,
       has_schema_privilege(
           'regengine',
           (SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
             WHERE e.extname = 'pgcrypto'),
           'USAGE'
       ) AS regengine_usage_on_pgcrypto_schema,
       (SELECT array_to_string(setconfig, ', ')
          FROM pg_db_role_setting AS s
         WHERE s.setrole = (SELECT oid FROM pg_roles WHERE rolname = 'regengine')
           AND s.setdatabase IN (0, (SELECT oid FROM pg_database WHERE datname = current_database()))
         LIMIT 1) AS regengine_role_settings;

ROLLBACK;

-- OPTIONAL, BEFORE the deploy, only from a session that bypasses RLS (for
-- example a provider superuser; under FORCE RLS the tenant policy raises for
-- anyone else): blobs the new (ingestion_run_id, tenant_id) foreign key would
-- reject. v126 aborts with this count rather than deleting anything.
--
--   BEGIN TRANSACTION READ ONLY;
--   SELECT count(*) AS blobs_off_their_tenant_run
--     FROM fsma.manifest_blobs AS blob
--    WHERE NOT EXISTS (SELECT 1 FROM fsma.ingestion_runs AS run
--                       WHERE run.id = blob.ingestion_run_id
--                         AND run.tenant_id = blob.tenant_id);
--   ROLLBACK;
