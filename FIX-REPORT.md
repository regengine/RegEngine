# FIX-REPORT: suspended tenants' API keys still authenticate (Blocker 1)

Worktree: re-fx-suspended-tenant (own branch off origin/main e854dadc).
Finding confirmed by code read: `get_current_tenant` in
`services/admin/app/dependencies.py:780` holds the only suspended-tenant
deny, and no production route calls it. Live auth `require_api_key` in
`services/shared/auth.py` never read `tenants.status`, and the 3242 cached
idempotency replay lookup in `services/shared/idempotency.py` never read it
either. A suspended tenant with a still-valid key authenticated and replayed.

## Findings

| # | Source report | Severity | Status | Reason |
|---|---|---|---|---|
| 1 | re-rv-3238-security (Critical), re-rv-3238-correct (High), re-rv-3238-tenant (High), re-rv-area-auth, re-rv-lead-security, re-rv-int-auth-kernel: suspended-tenant deny on dead dependency, live `require_api_key` never reads `tenants.status` | Blocker | FIXED AND TESTED | Status read added inside `require_api_key` after key validation, before principal storage and rate limiting. Suspended, archived, or missing tenant denies with 403; lookup errors deny with 503; only `api_key.tenant_id` is bound. |
| 2 | re-rv-int-auth-kernel (HIGH): 3242 idempotency `_lookup_api_key_context` never reads tenant status, serves cached 2xx before route dependencies | High (part of this blocker) | FIXED AND TESTED | Same status read added to the replay lookup in the same session. Suspended, archived, missing, or unreadable status resolves no tenant, so the request falls through to the route, whose own auth denies. |

Out of scope for this blocker (named in the same reports, owned elsewhere):
role-name rank gaps (`permissions.py`/`user_routes.py`), MFA strict-boot env
gates, 3252 naive-expiry in the DB store, tool-cookie expiry. None touched.

## Changes

- `services/shared/api_key_store.py`: new `DatabaseAPIKeyStore.get_tenant_status`.
  Binds the key tenant (FORCE RLS needs `app.tenant_id`), then one indexed
  primary-key `SELECT status FROM tenants`, no writes. Returns None when the
  row is missing; raises on lookup failure so callers fail closed.
- `services/shared/auth.py` (`require_api_key`): after key validation and
  the workload-key rejection, before rate limiting and principal storage,
  read the status for DB-store keys. Non active/trial denies 403 with the
  invalid-key body; lookup errors deny 503. In-memory store path unchanged
  (no tenants table; local dev and test only; strict runtimes use the DB
  store). Test-bypass branch unchanged (dev/test only, blocked in prod).
- `services/shared/idempotency.py` (`_lookup_api_key_context`): after the
  enabled/revoked/expiry checks, bind the key-row tenant and read its
  status in the same session. Anything but active/trial, or any lookup
  error, resolves nothing, so no cached body replays for suspended tenants.
- Tests: new `services/shared/tests/test_auth_suspended_tenant.py` (calls
  `require_api_key` directly: suspended/archived/missing deny 403, principal
  never stored, rate limiter untouched, status binds only the key tenant,
  lookup error gives 503, active/trial pass); new
  `services/shared/tests/test_api_key_store_tenant_status.py` (reader SQL,
  binding, missing row, error propagation, empty tenant); extended
  `tests/shared/test_idempotency_revocation_replay.py` (suspended replay
  blocked end to end, error fails closed); updated stubs in
  `services/shared/tests/test_auth_1338.py`,
  `services/shared/tests/test_api_key_store_rate_limit_minute_rollover.py`,
  and `tests/shared/test_idempotency_middleware_1338.py` to answer the new
  status read the same way they already stubbed key validation.

## Test commands and results

- New plus updated suites (fix applied):
  `pytest services/shared/tests/test_auth_suspended_tenant.py
  services/shared/tests/test_api_key_store_tenant_status.py
  services/shared/tests/test_auth_1338.py
  services/shared/tests/test_api_key_store_rate_limit_minute_rollover.py
  tests/shared/test_idempotency_revocation_replay.py
  tests/shared/test_shared_auth_contract_qa4.py`
  result: `156 passed in 0.90s`
- Fail-without-fix check: HEAD versions of `auth.py` and `idempotency.py`
  temporarily restored (fix backed up to /tmp and restored after, verified
  byte-identical with diff): `10 failed, 7 passed` (every suspension and
  503 test failed; only the active/trial happy paths passed). Fix restored.
- Real-database check of the new SQL (`/tmp/verify_tenant_status_pg.py`,
  throwaway local database `fleet_suspended`, created and dropped in the
  script): `suspended row -> 'suspended'`, `trial row -> 'trial'`,
  `missing row -> None`, `POSTGRES-VERIFY: OK`.
- Full `tests/shared`: `1346 passed, 43 skipped` (skips are Docker and live
  Postgres unavailability).
- Full `services/shared/tests`: passes except one pre-existing failure,
  `test_extract_document_script.py::test_verbose_sends_wrapper_log_lines_to_stderr_only`,
  which fails identically on the untouched base (verified by running the
  full directory with all touched files at HEAD versions) and passes in
  isolation. Unrelated to this change.
- Ingestion auth files (`test_routes_ingest_auth_tenant`,
  `test_authz_ratelimit_fallback_2847`, `test_routes_discovery_tenant_key_2921`,
  `test_authz_1342`): `123 passed, 1 xfailed` (xfail pre-existing).
- Admin tenant/api_key/auth selection: `503 passed, 1 skipped`.
- `ruff check` on all 9 touched test and source files: `All checks passed!`.
  `ruff format --check`: clean.
- `scripts/security/scan_tenant_scope.py`: still fails, but only on
  pre-existing graph findings owned by other blockers
  (`traceability_linker.py:31`, `:112`, stale `chain_integrity`/`tenant_nodes`
  baselines). No finding references any file changed here.

## Needs C.Lee's decision

None for this blocker. Notes, no action needed:

1. The 401 (invalid key) versus 403 (suspended key) status difference lets a
   caller distinguish a suspended tenant from a bad key. This matches the
   existing `get_current_tenant` convention and the task order (403 or 503),
   so it was kept. Say the word if all key denials should be one code.
2. Suspension is read live on every request (one indexed SELECT, no cache),
   so suspension takes effect immediately. A cache would be cheaper under
   load but would delay enforcement; none added.
3. The scanner failure above belongs to findings assigned to other workers
   (PRs 3220, 3227, 3246); left untouched per lane rules.
