# FIX-REPORT: PR #3244 ingestion route tests

Merge commit 33d2f2487054dbf53d5eca305a7861ffcdc58a81. Sources read: all six
re-rv-3244-<angle> reports (correct SUMMARY and REPORT, tests SUMMARY and
REPORT, security, tenant, ops, blast), plus the angle leads, area leads, and
integration checks that mention #3244 (lead-blast, lead-correct, lead-ops,
lead-security, lead-tenant, lead-tests, area-webhooks, int-rollback,
int-frontend-build, chief REPORT).

## Findings table

| # | Source report | Severity | Finding | Status | Reason |
|---|---------------|----------|---------|--------|--------|
| 1 | re-rv-3244-tests (medium 1), lead-tests, area-webhooks item 9, chief | Medium | 401 test overrode get_ingestion_principal to raise, so the real missing-key branch (authz.py:262) was untested | FIXED AND TESTED | Test now sends a keyless request through the real dependency with REGENGINE_ENV=production and asserts 401 |
| 2 | re-rv-3244-tests (medium 2), lead-tests, area-webhooks item 9, chief | Medium | 404 test injected the raise instead of letting service.get_run_meta raise (service.py:797) | FIXED AND TESTED | Test now uses the real get_run_meta with a fake DB returning no row |
| 3 | re-rv-3244-tests (medium 3), lead-tests, area-webhooks item 9, chief | Medium | 409 test only covered empty allowed_fields (early return at router.py:190), never the disallowed-status path at router.py:254; worse, the status check ran after token revoke and mint, so a disallowed status still revoked live tokens and minted a fresh one before the 409 | FIXED AND TESTED | Added closed-status 409 test asserting zero token calls; moved the status gate in create_link above revoke and mint. New test fails on the old router order (verified by round trip) |
| 4 | re-rv-3244-tests (medium 4), lead-tests, area-webhooks item 9, lead-blast low, lead-ops (dropped as ops) | Medium | test_ingest_direct_default_source_url_validates was xfail(strict=True), never called the handler, hardcoded manual://direct, so a changed handler default would stay green | FIXED AND TESTED | Replaced with a real POST without source_url that captures url_str reaching _process_and_emit and asserts the real 500 through the NormalizedEvent model; xfail removed |
| 5 | re-rv-3244-tests (low 5), lead-tests low list | Low | test_ingest_direct_with_tenant_passes_the_guard asserted the response tenant but the stub ignored kwargs, so it never proved ingest_direct forwarded api_key.tenant_id | FIXED AND TESTED | Trivial fix in the same edit: stub now captures kwargs and the test asserts tenant_id was forwarded |

No critical or high findings were filed against #3244 by any angle. No finding
was skipped for lack of confirmation; every medium and the one test-quality low
above was confirmed by reading the cited code and fixed.

Out of scope (owned by other tasks, noted only): the suspended-tenant deny on
live auth, the tenant-scope gate failure, and the 7 xfail cross-tenant leaks.

## Test commands and results

Baseline before changes:
`.venv/bin/python -m pytest services/ingestion/tests/test_remediation_router_auth_tenant.py services/ingestion/tests/test_routes_ingest_auth_tenant.py -q --no-cov -p no:cacheprovider`
-> 22 passed, 1 xfailed (the strict xfail).

After changes, same command:
-> 24 passed, 0 xfailed. Exact tail line: `........................  [100%]`
(no failures; full summary line printed by the non -q rerun as part of the
remediation suite run below).

Regression neighbors:
`.venv/bin/python -m pytest services/ingestion/tests/remediation/ services/ingestion/tests/test_remediation_router_auth_tenant.py services/ingestion/tests/test_routes_ingest_auth_tenant.py --no-cov -p no:cacheprovider`
-> 31 passed, 50 skipped in 4.19s (skips require local Postgres, unavailable here).
`.venv/bin/python -m pytest services/ingestion/tests/test_supplier_portal_1342.py services/ingestion/tests/remediation/test_remediation_corrections_evidence.py services/ingestion/tests/remediation/test_remediation_outbox_delivery.py --no-cov -p no:cacheprovider`
-> 63 passed, 23 skipped in 1.99s (same Postgres-gated skips).

Sensitivity (new tests fail without their fix):
- Scratch probes in /tmp/sens_3244/test_sensitivity.py (not committed):
  `pytest /tmp/sens_3244/test_sensitivity.py -q --no-cov -p no:cacheprovider --rootdir=/tmp/sens_3244`
  -> 4 failed as designed (S1 dev-open fallback instead of 401; S2 row found
  instead of 404; S4 fixed handler default breaks old expectations; S5 swapped
  tenant caught by kwarg capture while the response echo stays green).
- Production round trip for finding 3: swapped the HEAD version of
  services/ingestion/app/remediation/router.py into the tree, ran the new
  closed-status test -> FAILED at the zero-calls assertion (token was minted
  before the 409). Restored the fixed file byte-identical (diff confirmed) and
  the test passes.
- Lint: `.venv/bin/ruff check` on all three touched files -> All checks passed.
  (`ruff format --check` flags both test files, but their HEAD versions were
  already unformatted, so no reformatting was applied to keep the diff minimal.
  CI only gates `ruff check --select E9,F63,F7,F82`.)
- Tenant-scope scan: `scripts/security/scan_tenant_scope.py` -> exit 1 from
  pre-existing services/graph hits (out of scope for this task); 0 hits mention
  any of the three touched files. No query text was changed.

## Needs Christopher's decision

1. POST /v1/ingest with no source_url returns 500 today because the handler
   default "manual://direct" fails NormalizedEvent HttpUrl validation. The new
   test pins this behavior (url_str manual://direct, status 500). If the
   intended behavior is success, the default in routes_ingest.py:603 or the
   model field type needs a product decision, then the test expectation changes
   with it. No production behavior was changed in this fix.
2. Moving the create_link status gate above revoke means a disallowed-status
   case no longer revokes its live tokens as a side effect of a rejected
   request. This is strictly safer, but confirm no operator workflow depended on
   the old revoke-on-reject behavior.
3. Remaining risk: neighboring suites that need local Postgres were skipped
   here (73 skips total); CI should confirm them.
