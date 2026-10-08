# FIX-REPORT: PR #3229 (webhook HMAC fail closed in production)

Merge reviewed: edfc61dba6ce4844c5627d56d83e3898ad08a011, on origin/main e854dadc.
Reports read: all six re-rv-3229 angles (correct, security, tenant, tests, ops, blast,
each SUMMARY.md plus REPORT.md where present), and the lead/area/integration mentions of
#3229 in re-rv-lead-blast, re-rv-lead-ops, re-rv-lead-security, re-rv-lead-tests,
re-rv-area-webhooks, re-rv-int-deploy-readiness, and re-rv-int-env-docs.

## Findings

| # | Source report | Severity | Finding | Status |
|---|---------------|----------|---------|--------|
| 1 | 3229-security Medium; area-webhooks High finding 2; lead-security item 22 | Medium (raised High by area lead) | Fail-closed gate used `is_production()` only, so a cloud deploy named `staging` (the value this repo writes for Railway staging) with no secret still accepted unsigned ingest bodies | FIXED AND TESTED |
| 2 | 3229-correct Low; 3229-security Low; 3229-ops Medium; 3229-blast Medium; area-webhooks Medium finding 8 | Medium | Production 401 path called `_record_hmac_skip()` first, so the fail-open skip counter and skip WARN counted rejected requests as accepted unsigned traffic | FIXED AND TESTED |
| 3 | 3229-ops High/Medium; 3229-blast Medium; area-webhooks High finding 3 | Medium | `/health` stayed `healthy` with the secret unset while ingest was fully 401, and `/readiness` does not check the secret either | FIXED AND TESTED (`/health` degrades; `/readiness` left alone, see notes) |
| 4 | 3229-blast Medium; area-webhooks High finding 3 | Medium | Next ingestion proxy did not forward `X-Webhook-Signature`, so browser-relayed signed posts arrived unsigned | FIXED AND TESTED |
| 5 | 3229-ops Low; int-env-docs Critical finding 2 | Critical (per int-env-docs) | `WEBHOOK_HMAC_SECRET` absent from `.env.example`, `scripts/validate_env.py`, and deploy docs, so a deploy wired only from templates silently stops all webhook ingest | FIXED AND TESTED |
| 6 | 3229-blast Low; lead-blast low list | Low | `services/ingestion/app/email_ingest/auth.py` comment still said the HMAC gate fails open when unset | FIXED (comment only, trivial) |
| 7 | 3229-ops Low | Low | `routes.py` comment said the HMAC check applies when the secret is configured (now also rejects when unset on a closed gate) | FIXED (comment only, trivial) |
| 8 | 3229-blast High; 3229-ops High; lead-blast High; lead-ops item 6 | High | Unsigned callers (FieldCapture, receiving, label scanner, offline sync, seed scripts) now get 401 in production when the secret is unset; whether Railway production has the secret and whether live partners sign is not in the repo | BLOCKED (ops action, needs Christopher; no repo code can set the Railway value or confirm partner behavior) |
| 9 | 3229-blast Medium | Medium | Suggestion to gate the 401 on an explicit `REGENGINE_ENV=production` instead of the Supabase pooler URL heuristic in `is_production()` | NOT APPLIED (deliberate; the heuristic fails closed more often, which is the safe direction, and changing shared env detection is out of scope) |
| 10 | Out of scope for this task | n/a | Suspended-tenant deny on live auth; tenant-scope gate failure (scanner exit 1 on main); 7 xfail cross-tenant leaks | NOTED ONLY, owned by other tasks |

## What was changed

* `services/ingestion/app/webhook_router_v2/security.py`: new `_requires_closed_hmac_gate()` (production OR `requires_strict_auth_runtime()`, fail closed on import error); the unset-secret branch uses it; the 401 path now calls `_record_hmac_reject()` and no longer touches the skip counter or skip warning; docstrings updated.
* `services/ingestion/app/webhook_router_v2/metrics.py`: new `WEBHOOK_HMAC_REJECTED` counter (`webhook_hmac_verification_rejected_total`) and `_record_hmac_reject()`.
* `services/ingestion/app/webhook_router_v2/__init__.py`: export the two new names.
* `services/ingestion/app/routes_health_metrics.py`: `/health` returns `degraded` (with `ingestion_health_hmac_secret_missing` warning) when the secret is unset on a closed gate; healthy otherwise.
* `frontend/src/app/api/ingestion/[...path]/route.ts`: proxy forwards `x-webhook-signature`.
* `services/ingestion/app/email_ingest/auth.py`, `services/ingestion/app/webhook_router_v2/routes.py`: comments corrected.
* `.env.example`, `scripts/validate_env.py`: `WEBHOOK_HMAC_SECRET` documented as required and added to `_PRODUCTION_REQUIRED`.
* Tests: rewrote the production counter test (reject counter up, skip counter unchanged); added staging-cloud 401, local-dev ramp, and explicit-production 401 tests that drive the real env predicate without stubbing; added three `/health` posture tests; added one proxy forwarding test; added the new var to `tests/shared/test_secret_validation.py` base env.

## Test commands and results

All backend runs used the shared venv through the slot queue. Every line below is quoted from actual output.

1. `~/metacode/fleet/heavy .venv/bin/pytest services/ingestion/tests/test_webhook_hmac_fail_closed.py --no-cov -p no:cacheprovider`
   Result: `10 passed in 1.29s`
2. Fail-without-fix check (sources temporarily restored to HEAD via read-only `git show`, tests untouched):
   `~/metacode/fleet/heavy .venv/bin/pytest services/ingestion/tests/test_webhook_hmac_fail_closed.py services/ingestion/tests/test_routes_health_metrics_1342.py --no-cov -p no:cacheprovider`
   Result: `3 failed, 23 passed in 2.35s`, failures exactly:
   `TestProductionWithoutSecretRejects::test_production_reject_increments_reject_counter_not_skip_counter`,
   `TestClosedGateUsesRealEnvironmentPredicate::test_staging_cloud_deploy_rejects_without_secret`,
   `TestHealthHmacPosture::test_missing_secret_degrades_in_production`.
   Fixes were then restored byte-identical (verified with `diff`).
3. Full webhook surface (20 backend files: all webhook, HMAC, replay, health-metrics, compat, idempotency, rate-limit, funnel, envelope, auth-tenant, plus secret validation):
   Result: `335 passed, 1 xfailed in 29.38s` (the xfail is the pre-existing `manual://direct` source_url bug in `test_routes_ingest_auth_tenant.py`, untouched by this change).
   This covers Christopher's extra scrutiny: valid signatures accepted (`TestValidHmacAccepted`, both production flags, real `hmac.compare_digest`), missing and bad signatures rejected, and no endpoint fails open (closed gate now covers production plus strict/cloud runtimes; only local dev/test keeps the ramp).
4. Post-restore re-run of the three touched backend files:
   Result: `34 passed in 0.89s`.
5. Frontend: `npx vitest run src/__tests__/api/ingestion-proxy-auth.test.ts`
   Result with fix: `Test Files 1 passed (1)`, `Tests 12 passed (12)`.
   Against pre-fix `route.ts`: `1 failed | 11 passed (12)`, the failure being the new forwarding test. File restored byte-identical (verified with `diff`), re-run green.
6. Lint: repo CI gate `ruff check --select E9,F63,F7,F82 --line-length 120` on all 10 changed Python files:
   Result: `All checks passed!`
   (Full `ruff check` reports 3 I001 import-sort notes in `webhook_router_v2/__init__.py`, byte-identical on HEAD, so pre-existing and not from this change. `ruff format --check` disagrees with repo style on lines never touched, so no reformatting was applied.)
   Frontend `eslint` on both changed files: exit 0, no output.
7. Full ingestion suite `services/ingestion/tests` (5694 tests collected): the only failures were the same 3 on the fixed tree and on the untouched HEAD tree (verified by full run on both):
   `test_fetcher_ssrf_size_cap.py::test_generic_rss_downloads_feed_through_safe_helper` (passes alone; suite-ordering interaction in scraper state, PR #3232 area, no file I touched is imported by that path),
   `test_fsma_readiness_compat_2893.py` TestOperatorGate x2 (subprocess boot fails with `MFA_ENCRYPTION_KEY is required for strict authentication`, a PR #3238 env gap, no secret value available in this sandbox).
   No failures involve webhook, HMAC, health, proxy, or env-validation code.
8. `scripts/security/scan_tenant_scope.py`: not run. I touched no queries (only the HMAC gate, counters, health status, proxy headers, env template, and comments), and the scanner's exit-1 state on main is explicitly out of scope for this task.

## Needs Christopher's decision

1. Set `WEBHOOK_HMAC_SECRET` on the Railway production service (and strict staging) before this behavior takes traffic, and confirm live partners send `X-Webhook-Signature: sha256=<hex>` over the raw body. Until then, production ingest is fully 401 by design. I cannot verify the Railway value from the repo.
2. Field capture, receiving, label scanner, and offline sync post unsigned through the browser proxy and hold no secret (by design). If they must work against a closed gate, the signing has to happen server side (for example, the Next proxy signs cookie-authenticated posts to `api/v1/webhooks/ingest` with a server-only secret). That is a new feature, not part of this fix; this change only makes the proxy forward a signature when the caller provides one.
3. Optional hardening not taken: fail `/readiness` in production when the secret is unset so a bad deploy rolls back under the Railway restart policy. I left `/readiness` alone because turning a missing secret into restart loops is an ops call.
