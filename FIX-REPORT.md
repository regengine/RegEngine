# FIX-REPORT: PR #3230 follow-up fixes

Merge commit 5aef33529e3e65c714cec0c44fb2efe92c69fd9c, worktree off origin/main e854dadc.
Sources read: all six re-rv-3230-<angle> SUMMARY.md files, plus the lead blast, ops,
security, tenant and tests summaries and the infra area and env-docs and secret-scan
integration notes that mention #3230.

## Findings

| # | Source report | Severity | Finding | Status | Reason |
|---|---|---|---|---|---|
| 1 | re-rv-3230-blast High, re-rv-3230-ops 3230a, re-rv-lead-ops 4 | High | Production audit export raises RuntimeError (HTTP 500) when AUDIT_PII_HASH_SALT is unset; var absent from validate_env and .env.example | FIXED AND TESTED | Export now answers 503 with the same message; var added to _PRODUCTION_REQUIRED and .env.example; new 503 regression test passes, fails with guard backed out |
| 2 | re-rv-3230-ops 3230b, re-rv-lead-ops 5 | High | WEBAUTHN_EXPECTED_ORIGIN unset 503s passkey verify but nothing checks it at deploy time | FIXED AND TESTED | Var added to _PRODUCTION_REQUIRED and .env.example; new route test pins 503 passthrough, fails with 401 when passthrough removed |
| 3 | re-rv-3230-blast Medium, re-rv-3230-ops 3230c, re-rv-lead-blast 3230 Medium | Medium | Non-production salt is per-process random, so staging workers disagree on masked values | FIXED AND TESTED | validate_env now errors on missing AUDIT_PII_HASH_SALT when REGENGINE_ENV is staging; new staging tests pass; old HEAD module returns ok without the salt |
| 4 | re-rv-3230-security Medium, re-rv-3230-tests notes | Medium | tests/scripts/test_security_lows_scripts.py exec_module runs the e2e .env loader at import, leaking secrets into the pytest process | FIXED AND TESTED | .env loading moved into _load_dotenv called only from run(); test uses lazy import plus an AST test pinning no top-level os.environ write; AST check fails on HEAD script |
| 5 | re-rv-3230-tests Medium | Medium | Hardening tests do not prove the salt is inside the hash | FIXED AND TESTED | Added digest-changes-with-salt test and retired-default-salt test; both fail against the pre-3230 constant-salt behavior confirmed in 5aef3352^ |
| 6 | re-rv-3230-tests High | High | tests/scripts/test_security_lows_scripts.py not in required backend-ci gate | FIXED AND TESTED | Added to the operator tooling pytest list in backend-ci.yml; the file itself passes standalone (see commands); the workflow cannot run headless |
| 7 | re-rv-3230-tests Low | Low | webauthn tests never call the verify routes, so the HTTPException passthrough is unpinned | FIXED AND TESTED | Added registration verify 503 test; trivial, fails with 401 without the passthrough |
| 8 | re-rv-3230-security Low | Low | .gitleaks.toml still allowlists deleted fix_password.sql | FIXED AND TESTED | Removed the dead path entry; verified the file is absent and nothing references it; gitleaks binary not run here |
| 9 | re-rv-3230-ops 3230 finding 4, re-rv-3230-blast Low | Low | docs/GOLDEN_PATH.md runs the brutal scenario with no env setup | FIXED AND TESTED | Doc now exports REGENGINE_INTERNAL_SECRET first; docs only, no behavior change |
| 10 | re-rv-3230 correct/ops notes | Low | .env.example documents neither new variable | FIXED AND TESTED | Added both with generate commands and write-once note; covered by finding 1 and 2 tests |
| 11 | re-rv-3230-correct Low, re-rv-lead-blast 3230 low | Low | Passkey verify on unset deploys changes from 401 to 503; local request-URL fallback now fails closed | Listed, not fixed | Intended fail-closed behavior of PR #3230, confirmed by code reading; no change needed |
| 12 | re-rv-3230-security Low | Low | Deleted argon2id hash still in git history; ^scripts/ gitleaks allowlist still broad | Listed, partly fixed | Dead path entry removed (finding 8). History purge and narrowing ^scripts/ need Chris decision below |
| 13 | re-rv-3230-ops finding 5 | Low | New salt will not match older masked exports | Listed, not fixed | Operational guidance, addressed with the write-once comment in .env.example; rotating to chase old hashes would restore a public salt |
| 14 | Task brief | Out of scope | Suspended-tenant deny on live auth, tenant-scope gate failure, 7 xfail cross-tenant leaks | Noted only | Owned by other tasks; untouched here |

## Test commands and results

1. `~/metacode/fleet/heavy .venv/bin/python -m pytest services/admin/tests/test_admin_service_hardening.py services/admin/tests/test_webauthn_router.py services/admin/tests/test_audit_export_self_log_2522.py tests/shared/test_secret_validation.py tests/scripts/test_security_lows_scripts.py --no-cov -p no:cacheprovider`
   Result: `66 passed, 1 skipped, 2 warnings in 3.22s`. The skip is pre-existing (SQLite no-op listener in test_admin_service_hardening.py:82).
2. Fail-without-fix, export guard: guard edited away by hand, ran `TestExportMissingSaltFailsClosed503`, result `1 failed ... Failed: DID NOT RAISE HTTPException`. Guard restored, test passes.
3. Fail-without-fix, webauthn passthrough: inner `except HTTPException: raise` removed by hand, ran the new 503 test, result `1 failed ... AssertionError: assert 401 == 503`. Lines restored, test passes.
4. Fail-without-fix, old-code probes (`/tmp/probe_3230_oldcode.py`, uses read-only `git show` of HEAD files): old validate_env returns ok with salt missing, HEAD e2e script has a top-level os.environ write, old constant-salt mask equals the retired digest. All three probes confirm the new tests fail on pre-fix code.
5. `ruff check` on all nine changed Python files: `All checks passed!`. `ruff format --check` clean on every file I touched (two pre-existing deviations in test_admin_service_hardening.py:622 and test_webauthn_router.py:180 left alone).
6. `scripts/security/scan_tenant_scope.py`: not run. I changed no queries (the export diff adds only a salt check before the existing query), so the scanner gate is unaffected.

## Needs Chris decision

1. Set AUDIT_PII_HASH_SALT to a new long random value (write-once, keep it) on Railway production and staging, and WEBAUTHN_EXPECTED_ORIGIN to the public app origin on production, before the next deploy. Neither value is in the repo and I cannot set them.
2. Require WEBAUTHN_EXPECTED_ORIGIN for staging too? I required only the salt for staging; passkey verify on staging without the origin still 503s at ceremony time.
3. Narrow or remove the `^scripts/` gitleaks allowlist, and decide whether to purge the deleted argon2id hash from git history. Also confirm whether that admin@example.com password was ever applied to a real database; if so rotate it.
4. Confirm no out-of-repo client joins two audit exports on masked emails across the salt change; old and new masked values will not match.
