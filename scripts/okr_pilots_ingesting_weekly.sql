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
-- Usage:
--   psql "$DATABASE_URL" -f scripts/okr_pilots_ingesting_weekly.sql
--
-- Or one-line:
--   psql "$DATABASE_URL" -c "$(cat scripts/okr_pilots_ingesting_weekly.sql)"

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
