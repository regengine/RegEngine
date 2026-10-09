-- OKR weekly read — pilots ingesting CTE events in the past 7 days
--
-- Source-of-truth query for the single OKR documented in
-- docs/decisions/2026-05-13-okr.md:
--
--   "N pilot operators with ≥1 real CTE event ingested in the past 7 days."
--
-- Run against the production PostgreSQL each Monday morning.
-- Counts distinct tenants by `event_entry_timestamp` (when the event entered
-- the system), not `event_timestamp` (when the supply-chain event occurred).
-- Backfilled historical events count as ingestion activity in the week they
-- arrive, which is the right behavior for the OKR.
--
-- Usage (read-only reporting session only):
--   psql "${OKR_READONLY_DATABASE_URL:?set OKR_READONLY_DATABASE_URL to a read-only reporting URL}" \
--     -X -v ON_ERROR_STOP=1 -f scripts/okr_pilots_ingesting_weekly.sql
--
-- The script refuses to run as a write-capable login (see the guard below),
-- so a write-capable URL pasted here stops with an error instead of running
-- the report in a session that a later statement could change rows through.
-- Provisioning the read-only reporting login is a production config step
-- outside this file. Local trial runs without that login can add
-- PGOPTIONS="-c default_transaction_read_only=on" in front of psql.
--
-- Guard: confirm a read-only role before use.
DO $okr_guard$
BEGIN
    -- An explicit read-only posture counts as read-only: with
    -- default_transaction_read_only on, the session cannot change rows
    -- whatever the login could otherwise do.
    IF current_setting('default_transaction_read_only', true) IS DISTINCT FROM 'on'
       AND EXISTS (
           SELECT 1
             FROM pg_catalog.pg_roles
            WHERE rolname = current_user
              AND (rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole
                   OR rolname IN ('regengine', 'regengine_sysadmin', 'postgres'))
       )
    THEN
        RAISE EXCEPTION
            'refusing to run as write-capable role %: rerun with a read-only reporting role (OKR_READONLY_DATABASE_URL), or with PGOPTIONS="-c default_transaction_read_only=on" for a local trial run',
            current_user;
    END IF;
END
$okr_guard$;

-- One read-only transaction for the whole report: a consistent snapshot
-- across the headline number and the breakdowns, and the database itself
-- rejects any change through this session.
BEGIN TRANSACTION READ ONLY;
SET LOCAL search_path = pg_catalog, pg_temp;

\echo '=== OKR: pilots ingesting weekly (past 7 days) ==='
\echo ''

-- Headline number (the OKR).
SELECT
    COUNT(DISTINCT t.id) AS active_pilots_past_7d
FROM fsma.cte_events e
JOIN public.tenants t ON t.id = e.tenant_id
WHERE e.event_entry_timestamp >= NOW() - INTERVAL '7 days'
  AND t.status = 'active'
  -- Exclude demo / test / internal fixtures from the OKR count.
  -- Update the regex if new internal-tenant naming patterns appear.
  AND t.name !~* '^(demo|test|internal|fixture|seed|sample)';

-- Per-pilot breakdown (for the Monday context note).
\echo ''
\echo '--- Per-pilot breakdown ---'
SELECT
    t.name              AS tenant_name,
    t.slug              AS tenant_slug,
    COUNT(e.id)         AS events_past_7d,
    MIN(e.event_entry_timestamp) AS first_event_in_window,
    MAX(e.event_entry_timestamp) AS most_recent_event
FROM fsma.cte_events e
JOIN public.tenants t ON t.id = e.tenant_id
WHERE e.event_entry_timestamp >= NOW() - INTERVAL '7 days'
  AND t.status = 'active'
  AND t.name !~* '^(demo|test|internal|fixture|seed|sample)'
GROUP BY t.id, t.name, t.slug
ORDER BY events_past_7d DESC;

-- All-time context: how many pilots have EVER ingested?
\echo ''
\echo '--- All-time context ---'
SELECT
    COUNT(DISTINCT e.tenant_id) AS pilots_with_any_ingest_ever
FROM fsma.cte_events e
JOIN public.tenants t ON t.id = e.tenant_id
WHERE t.status = 'active'
  AND t.name !~* '^(demo|test|internal|fixture|seed|sample)';

-- Nothing to keep: the report ran read-only.
ROLLBACK;
