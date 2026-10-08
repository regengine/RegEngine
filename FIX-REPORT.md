# FIX-REPORT for PR #3252: shared auth kernel tests plus naive key-expiry crash fix

Merge commit e854dadc. Reports read: all six re-rv-3252 angles (blast, correct
REPORT and SUMMARY, ops, security, tenant, tests) plus the angle leads and
area/int leads that mention #3252 (lead-blast, lead-correct, lead-ops,
lead-tests, lead-security, lead-tenant, area-auth, int-auth-kernel,
int-ci-workflows, and the other int leads via grep).

## Findings table

| # | Source report | Severity | Status | Reason |
|---|---|---|---|---|
| 1 | correct REPORT medium; lead-correct HIGH; lead-ops high; lead-tests medium; area-auth medium: naive expires_at still 500s on DatabaseAPIKeyStore path (api_key_store.py:785) | High | FIXED AND TESTED | Same naive-as-UTC guard as the in-memory store, plus 2 regression tests |
| 2 | tests SUMMARY medium 1; lead-tests high pattern: four qa4 files run only in non-required test-suite-check, not in blocking backend-ci job | Medium | FIXED AND TESTED | Added all four files to the blocking Offline invariants step in backend-ci.yml; YAML validated; all four files pass |
| 3 | tests SUMMARY medium 3; lead-tests medium: secrets_manager localhost test runs with production env cleared, deleting the production raise stays green | Medium | FIXED AND TESTED | Added 3 production-env tests (missing host raises, missing password raises, set host never localhost) |
| 4 | tests SUMMARY low 4: test_missing_secret_only_warns_outside_strict does not clear GITHUB_ACTIONS or CI | Low | FIXED AND TESTED | Trivial: clear both markers in the test |
| 5 | correct REPORT low; tests SUMMARY low 5: naive test instants built from local datetime.now, do not pin treat-as-UTC | Low | FIXED AND TESTED | Trivial: build naive instants from UTC and add sub-hour cases |
| 6 | blast low; tenant low: naive expiry labeled UTC instead of rejected on the memory store | Low | NOT FIXED, listed | Rejecting would change the intended behavior of PR #3252; needs a product decision (see below) |
| - | Out of scope: suspended-tenant deny on live auth | - | NOT TOUCHED | Owned by re-fx-suspended-tenant |
| - | Out of scope: tenant-scope gate failure | - | NOT TOUCHED | Owned by re-fx-tenant-gate |
| - | Out of scope: 7 xfail cross-tenant leaks | - | NOT TOUCHED | Owned by re-fx-xfail-leaks |

No CONCERN or BLOCKER finding was skipped for lack of confirmation. Every
critical, high and medium finding above was confirmed by reading the code, and
finding 1 was additionally reproduced at runtime before the fix.

## What changed

- services/shared/api_key_store.py: DatabaseAPIKeyStore.validate_key now treats
  a naive expires_at as UTC before comparing, matching the in-memory
  APIKeyStore.validate_key guard from PR #3252. Past naive expiries return None,
  future ones validate, nothing raises TypeError.
- tests/shared/test_api_key_store.py: two new regression tests on the DB store
  with mocked sessions (naive past rejected, naive future accepted).
- tests/shared/test_shared_auth_contract_qa4.py: naive instants derived from
  UTC; new sub-hour (30 minute) past and future cases; CI markers cleared in
  the non-strict warning test.
- tests/shared/test_secrets_manager_qa4.py: three new production-env tests.
- .github/workflows/backend-ci.yml: the four qa4 files added to the blocking
  Offline invariants (no DB) pytest step in repo-root-suite.

No migration added. No query touched, so scripts/security/scan_tenant_scope.py
was not re-run (nothing in this change alters a query predicate).

## Test commands and results

All commands prefixed with ~/metacode/fleet/heavy and run with
PYTHONPATH="$(pwd):$(pwd)/services".

1. Repro script /tmp/repro_3252_naive_db.py (mocked DB session, naive past
   expiry through DatabaseAPIKeyStore.validate_key):
   - Before fix: `REPRODUCED TypeError: can't compare offset-naive and
     offset-aware datetimes`
   - After fix: `no raise, result=None` (plus the expected api_key_expired
     warning log line)
2. New DB tests against unfixed code (fix temporarily edited away by hand, then
   re-applied):
   - `pytest tests/shared/test_api_key_store.py -k naive` on old code:
     `FAILED test_validate_naive_past_expiry_rejected_not_raised` and
     `FAILED test_validate_naive_future_expiry_accepted`, both with
     `TypeError` at services/shared/api_key_store.py:785
   - Same selection with the fix: pass (covered in run 4)
3. New secrets tests against neutered guard (raise temporarily disabled by hand,
   then restored; git diff confirms services/shared/secrets_manager.py is back
   to pristine):
   - With guard disabled: `FAILED
     test_database_missing_host_raises_in_production` and `FAILED
     test_database_missing_password_raises_in_production`
   - With guard intact: pass (covered in run 4)
4. Full touched-area run with all fixes:
   `pytest tests/shared/test_api_key_store.py
   tests/shared/test_shared_auth_contract_qa4.py
   tests/shared/test_secrets_manager_qa4.py
   tests/shared/test_brute_force_limiter_qa4.py
   tests/shared/test_tenant_context_qa4.py
   tests/shared/test_auth_in_memory_keystore.py --no-cov`:
   `182 passed in 2.57s`
5. `ruff check` on the four changed Python files: `All checks passed!`
6. `ruff format --check`: 3 files clean; tests/shared/test_shared_auth_contract_qa4.py
   would reformat only in hunks at lines 286, 318 and 337, which are
   pre-existing code untouched by this change, so left alone.
7. `backend-ci.yml` parses as valid YAML after the edit.

## Needs Chris decision

1. Naive-as-UTC vs fail closed: the memory store (and now the DB store) labels
   a naive expires_at as UTC. On a host east of UTC a naive local wall-clock
   expiry that already passed locally can still validate. The alternative is to
   reject naive expires_at in APIKeyStore.create_key (fail closed) or document
   that callers must pass aware datetimes. This change keeps the PR #3252
   behavior; switching to reject is a product call.
2. Pre-existing format drift in tests/shared/test_shared_auth_contract_qa4.py
   (3 hunks, lines 286 and later) predates this change and was left as is.
