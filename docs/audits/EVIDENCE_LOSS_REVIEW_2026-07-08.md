# Production review — silent webhook evidence loss (funnel-insert transaction poisoning)

Date: 2026-07-08
Related fix: PR #2563 (`emit_funnel_event` savepoint + webhook v2 fallback savepoints)

## The defect being audited

From 2026-06-13 (commit `4c7ce21`, which introduced `emit_funnel_event` on the
webhook ingest path) until PR #2563, any failure of the `first_ingest`
funnel-telemetry INSERT aborted the shared ingest transaction on Postgres. The
route's final `commit()` then succeeded silently on the aborted transaction and
every evidence row from that request — `fsma.cte_events`, `fsma.cte_kdes`,
`fsma.hash_chain`, `fsma.traceability_events`, canonical rows — was discarded,
while the endpoint returned HTTP 200 "accepted" with event hashes. The
practical trigger is `funnel_events_tenant_id_fkey`: the ingesting tenant has
no `public.tenants` row.

## What the production database shows (read-only, 2026-07-08)

- `public.tenants` has 5 rows; `public.api_keys` has keys for 3 tenant IDs.
- Both real ingest tenants — `5946c58f…` (RegEngine) and `8904e67d…`
  (RegEngine Ingest Arena) — have `tenants` rows **and** backfilled
  `first_ingest` rows in `public.funnel_events` (the backfill is visible:
  the funnel row's `created_at` equals the tenant's earliest
  `cte_events.ingested_at` to the microsecond). For them the funnel INSERT
  resolves via `ON CONFLICT DO NOTHING` and cannot poison the transaction.
- One API key (created 2026-01-25) references tenant `40e74bc9-4087-4612-8d94-215347138a68`,
  which has **no `tenants` row and no funnel row**. Any accepted webhook batch
  sent with this key after 2026-06-13 would have been silently discarded.
- `fsma.cte_events` contains **no rows ingested after 2026-05-08** (274 rows
  total, all from known test/demo/CSV sources). `public.audit_logs` records
  only `session.create` / `tenant.create`, nothing after 2026-05-09.

## Conclusion

**No evidence of real-tenant data loss.** Both provisioned tenants were
structurally immune (existing funnel rows). No persisted webhook traffic
exists in the exposure window at all, which is consistent with there having
been no production webhook traffic since 2026-05-08.

**Residual uncertainty:** a discarded batch leaves no database trace by
definition. The two paths that could have lost data are (a) the orphan
`40e74bc9…` API key, and (b) master-key ingests with an `X-Tenant-ID` for a
tenant not in `public.tenants`. Ruling these out requires the application
logs, not the database.

## Follow-ups

1. Search Railway application logs (full retention window since 2026-06-13)
   for `funnel_event_emit_failed`. Every hit is a discarded batch; the
   adjacent request log line carries tenant and idempotency key.
2. If any hits involve a real sender: Inflow Lab persists per-event delivery
   records (`delivery_response`, `idempotency_key`, full event payload) and
   has a delivery-retry endpoint, so lost batches are replayable.
3. Delete or re-provision the orphan API key for tenant `40e74bc9…` — either
   create its `tenants` row or revoke the key.
4. Supabase flags RLS disabled on 21 tables including `fsma.cte_events`,
   `fsma.cte_kdes`, `fsma.hash_chain`, `fsma.fda_export_log`,
   `public.funnel_events` (critical advisory, separate from this incident):
   they are exposed to the `anon`/`authenticated` Supabase client roles.
   Needs its own remediation decision — enabling RLS without policies would
   block the app's own access if the app role is subject to RLS.
