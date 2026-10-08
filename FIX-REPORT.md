# FIX-REPORT: PR #3222 SafetyCulture webhook follow-up

Merge commit f1dabbb73027940173481e21ebca14f40b217e78.
Scope: confirmed CONCERN and BLOCKER findings from the six re-rv-3222
reports plus the lead and area reports that mention #3222. Critical,
high and medium findings were fixed where confirmable. Lows were fixed
only when trivial and safe, otherwise listed.

## Findings table

| # | Source report | Severity | Finding | Status | Reason |
|---|---|---|---|---|---|
| 1 | re-rv-3222-correct HIGH; re-rv-area-webhooks H1; re-rv-int-deploy-readiness 3; re-rv-int-env-docs 8 | High | Live SafetyCulture posts may be unsigned, so fail-closed 401s could drop legitimate inspection deliveries with retries | BLOCKED | Code confirms fail-closed 401 on missing signature. Whether the live provider signs, and with which header, cannot be verified from this box: fleet rules forbid network calls and the provider docs are external. Loosening the check would reopen the leak, so no code change was made. Needs Chris decision (see below). |
| 2 | re-rv-3222-correct Medium; re-rv-area-webhooks M7 | Medium | Signed payloads in the documented nested shape (event.event_types, resource.id) matched neither top level check, so they returned 200 with accepted: 0 and the inspection was silently discarded | FIXED AND TESTED | Parser now accepts both the top level shape and the nested shape, additive only. New tests use nested fixtures and assert the fetch runs with the nested id. |
| 3 | re-rv-3222-tests Low 1; confirmed by re-rv-lead-tests | Low | Reject tests did not assert _fetch_audit_detail was never called, so a fetch-then-raise reorder would stay green | FIXED AND TESTED | Added assert_not_awaited to all three reject tests. |
| 4 | re-rv-3222-tests Low 2 | Low | x-safetyculture-signature header branch had no test | FIXED AND TESTED | Added valid and invalid header tests. |
| 5 | re-rv-3222-tenant Low (rotation); re-rv-area-webhooks M13 part | Low | get_or_create_connector keeps the first instance, so a reconfigure with a rotated webhook secret never took effect | FIXED AND TESTED | configure endpoint now removes the cached instance before creating the replacement. New router test configures twice and asserts the second secret wins. |
| 6 | re-rv-3222-ops Low; re-rv-3222-blast Low; re-rv-area-webhooks M12 part | Low | RateLimitExceeded handler registered only on the standalone ingestion app, so a breached 60/minute limit on the consolidated app would return 500 instead of 429 if integration is ever allowlisted | FIXED AND TESTED | Registered the standard slowapi 429 handler on server.main beside add_rate_limiting. No behavior change today because integration is not in PRODUCTION_ENABLED_ROUTERS. Verified by compile check, slowapi import check, ruff, and the suites below. No dedicated 61-request test was added (limit driving is slow and flaky; the handler is the slowapi standard one). |
| 7 | re-rv-3222-tenant Low (oracle); re-rv-lead-tenant confirmed low; re-rv-area-webhooks M13 part | Low | Distinct 404 vs 401 bodies reveal per tenant whether a connector and secret exist | BLOCKED | Fix would change the public status contract (404 becomes 401) for unknown connectors. Needs Chris decision. Responses carry no inspection data, so this stays low. |
| 8 | re-rv-3222-correct Low; re-rv-3222-blast Low | Low | 60/minute limit keyed by client IP, not tenant, on the shared webhook route | BLOCKED | Re-keying changes throttling semantics for all tenants behind one egress address. Needs a design decision, so listed without change. |
| 9 | re-rv-int-rollback High (interaction) | Info | Reverting #3222 while keeping #3239 breaks the semgrep CI gate, which flags the exact fail-open pattern #3222 deleted | BLOCKED | Informational only. No code change needed. Revert order if ever required: revert #3239 first, then #3222. |
| 10 | Out of scope for this task | n/a | Suspended-tenant deny on live auth, tenant-scope gate failure, 7 xfail cross-tenant leaks | BLOCKED | Owned by other tasks, noted only. |

## Test commands and results

All commands were run through the slot queue (`~/metacode/fleet/heavy`).

1. `~/metacode/fleet/heavy .venv/bin/pytest services/ingestion/tests/test_safetyculture_webhook_auth.py -p no:cacheprovider -q`
   Result: 17 passed (all green after the fix).
2. Old-code check: the parser fix and the configure fix were temporarily
   reverted by hand edit (backups in /tmp/fx3222, no git commands used),
   then the new tests were run with
   `-k "nested or reconfigure or without_id or without_fetch or non_completion"`.
   Result: 4 failed as expected
   (test_nested_completion_shape_accepted_with_resource_id,
   test_nested_completion_shape_accepted_with_details_id,
   test_router_nested_shape_returns_count_only,
   test_reconfigure_rotates_webhook_secret),
   proving the new tests fail without the fix. The two no-fetch
   ignore-shape tests pass on old code too and serve as regression locks.
   Fixes were then restored from backup and verified present by grep.
3. `~/metacode/fleet/heavy .venv/bin/pytest services/ingestion/tests/test_safetyculture_webhook_auth.py services/ingestion/tests/test_integration_router_1342.py -p no:cacheprovider -q`
   Result: 56 passed, no failures.
4. `~/metacode/fleet/heavy .venv/bin/pytest services/shared/tests/test_external_connectors_defaults.py services/shared/tests/test_connector_safe_http.py -p no:cacheprovider -q`
   Result: 30 passed, no failures.
5. `~/metacode/fleet/heavy .venv/bin/ruff check services/shared/external_connectors/safetyculture.py services/ingestion/app/integration_router.py server/main.py services/ingestion/tests/test_safetyculture_webhook_auth.py`
   Result: All checks passed.
6. `py_compile` on the three changed source files plus a slowapi import
   check (`_rate_limit_exceeded_handler`, `RateLimitExceeded`).
   Result: COMPILE-OK, slowapi imports OK.
7. `scripts/security/scan_tenant_scope.py` was not run because no queries
   were touched (no SQL or Cypher changed).

No test still fails. No fix was backed out.

## What changed (files)

- services/shared/external_connectors/safetyculture.py: added
  _COMPLETION_EVENT_TYPES, _is_completion_event and
  _nested_inspection_id helpers; handle_webhook accepts the nested
  provider shape and logs top level keys when a signed completion has
  no usable id.
- services/ingestion/app/integration_router.py: configure endpoint
  removes the cached connector before creating the replacement.
- server/main.py: registered the slowapi RateLimitExceeded 429 handler
  beside add_rate_limiting.
- services/ingestion/tests/test_safetyculture_webhook_auth.py: no-fetch
  asserts, x-safetyculture-signature tests, nested shape tests, router
  nested test, reconfigure rotation test.

## Needs Chris decision

1. Capture one live SafetyCulture webhook request and confirm the real
   signature header and MAC input, then backfill per-tenant webhook
   secrets for every active SafetyCulture tenant. Until then, tenants
   without a configured secret get 401s instead of ingested data.
   (Finding 1, high.)
2. Whether the webhook route should return the same 401 body for an
   unknown connector and a bad signature, hiding connector presence.
   (Finding 7, low.)
3. Whether the webhook rate limit should be keyed by tenant_id instead
   of client IP. (Finding 8, low.)

## Decision applied: Decision 1 (Oct 8, 2026, 3:03 PM PT call)

Status: FIXED AND TESTED

Chris decided that SafetyCulture webhooks must reject every unsigned
post with 401, with no unsigned or compatibility path, while valid
signed deliveries in both payload shapes keep working.

Code audit result: PR 3222 had already removed the only unsigned path
(the old `if secret and signature` skip). The current
`SafetyCultureConnector.handle_webhook` fails closed on all three
inputs: missing configured secret raises ValueError, missing signature
header raises ValueError, and bad signature raises ValueError, all
mapped to 401 by `receive_webhook` in
services/ingestion/app/integration_router.py, and no fetch runs before
verification. The only other receiver at the same URL prefix
(`services/ingestion/app/integration_webhook.py`) is intentionally not
wired and raises NotImplementedError, so it cannot accept unsigned
SafetyCulture posts. No unsigned or compatibility path was found to
remove. One gap was fixed: a whitespace only webhook secret
(for example `"   "`) passed the old truthiness check and fell through
to an "Invalid signature" error instead of "not configured".
`services/shared/external_connectors/safetyculture.py` now treats a
blank secret the same as a missing one, so it is rejected before any
signature check or fetch.

New tests in
services/ingestion/tests/test_safetyculture_webhook_auth.py (all assert
the fetch is never awaited on reject):
- test_blank_secret_rejected_as_not_configured (fails on old code)
- test_nested_shape_missing_signature_rejected (regression lock)
- test_nested_shape_bad_signature_rejected (regression lock)
- test_router_nested_shape_missing_signature_returns_401 (regression lock)

Test commands and results (all run through ~/metacode/fleet/heavy):
1. `.venv/bin/pytest services/ingestion/tests/test_safetyculture_webhook_auth.py -p no:cacheprovider`
   Result: 21 passed in 1.00s.
2. Old-code check: the one line fix was temporarily reverted, then the
   four new tests were run with
   `-k "blank_secret or nested_shape_missing or nested_shape_bad or router_nested_shape_missing"`.
   Result: 1 failed as expected
   (test_blank_secret_rejected_as_not_configured, old code raised
   "Invalid SafetyCulture webhook signature" instead of "not
   configured"), 3 passed, 17 deselected. The three nested reject tests
   pass on old code too and serve as regression locks proving both
   payload shapes require HMAC. The fix was then restored.
3. `.venv/bin/pytest services/ingestion/tests/test_safetyculture_webhook_auth.py services/ingestion/tests/test_integration_router_1342.py -p no:cacheprovider`
   Result: 60 passed in 1.90s.
4. `.venv/bin/pytest services/shared/tests/test_external_connectors_defaults.py services/shared/tests/test_connector_safe_http.py -p no:cacheprovider`
   Result: 30 passed in 0.52s.
5. `.venv/bin/ruff check services/shared/external_connectors/safetyculture.py services/ingestion/tests/test_safetyculture_webhook_auth.py`
   Result: All checks passed.

What ops must confirm before deploy (no env was changed by this task):
1. The webhook secret must be configured in the SafetyCulture dashboard
   for every tenant that delivers inspections by webhook.
2. The same secret value must be configured in the service env for each
   of those tenants (the per-tenant `webhook_secret` on the connector
   config).
3. Until both sides match, those tenants will get 401s and their
   inspection deliveries will not be ingested, with retries from the
   provider. Confirm 401 rates return to normal after the secrets land.
