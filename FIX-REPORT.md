# FIX-REPORT for PR #3243 (merge a93ebdff)

Scope: confirmed CONCERN and BLOCKER findings from the six re-rv-3243 specialist
reports plus the angle leads, area leads, and integration checks that mention
#3243. Out of scope items (untouched, owned by other tasks): the
suspended-tenant deny on live auth, the tenant-scope gate failure, and the 7
xfail cross-tenant leaks.

No em dashes or en dashes are used in this file. "Fail-closed" and similar
hyphenated terms are plain hyphens.

## Findings

| # | Source report | Severity | Finding | Status | Reason |
|---|---------------|----------|---------|--------|--------|
| 1 | re-rv-3243-correct HIGH, re-rv-3243-ops HIGH, re-rv-3243-blast medium, lead-ops, int-prod-boot | High | `startswith` placeholder match in `validate_production_secrets` aborts boot for real secrets that merely start with `test`, `secret`, `neo4j`, etc., even though Neo4j and storage are optional subsystems | FIXED AND TESTED | Comparison is now exact and case-insensitive over the whole value. New tests: prefixed-but-real values boot, case variants still rejected |
| 2 | re-rv-3243-correct medium | Medium | Startup gate and credential getters enforce different contracts, and the `server/main.py` comment claims the gate disables the getter localhost fallbacks, which it does not | FIXED AND TESTED | Rewrote the `server/main.py` comment to state the real rule (DATABASE_URL always, Kafka only when enabled, unset optionals stay unset, getters keep their own fail-closed-on-use contract). No behavior change needed: the validator already implemented that rule |
| 3 | re-rv-3243-correct low | Low | `supplier_graph_sync.py` comment says startup validated Neo4j credentials, which it does not | FIXED AND TESTED | Comment rewritten while adding the log below (row 9). Trivial, touched the same lines |
| 4 | re-rv-3243-security medium 1, lead-security item 32 | Medium | Any non-empty `DATABASE_URL` counts as secure, so an explicit loopback URL boots in production | BLOCKED | Needs C.Lee decision. Rejecting loopback or sqlite URLs contradicts three committed tests that expect them to boot (FSMA child uses `postgresql://localhost`, OpenAPI child uses `sqlite:///:memory:`, route-contract child uses localhost). See decision D1 |
| 5 | re-rv-3243-security medium 2a, lead-security item 33 | Medium | Production boots with `NEO4J_URI` set and `NEO4J_PASSWORD` unset | FIXED AND TESTED | Validator now requires `NEO4J_PASSWORD` whenever `NEO4J_URI` or `NEO4J_URL` is set. New tests for both directions |
| 6 | re-rv-3243-security medium 2b | Medium | `erasure_routes.py` opens the Neo4j driver with an empty password and fails open to `accepted` | FIXED AND TESTED | Returns early with an `erasure_neo4j_skip` warning when the password is empty, before any driver is built. HTTP outcome unchanged by design. New test asserts the driver is never built |
| 7 | re-rv-3243-security low 3 | Low | Explicit `environment=` argument beats production detection, so a later caller could sidestep the fail-closed getter | BLOCKED | Deferred low. The committed test `test_explicit_environment_argument_wins_over_env` locks the current behavior, so changing it needs C.Lee decision D2 |
| 8 | re-rv-3243-security low 4 | Low | Kafka branch accepts plaintext loopback brokers with no password | BLOCKED | Deferred low per task rules (lows fixed only if trivial). No non-test caller uses `get_kafka_credentials` |
| 9 | re-rv-3243-tests medium, lead-tests | Medium | Only proof that `server/main.py` refuses to boot is a source regex, which passes even if the calls are swallowed in try/except | FIXED AND TESTED | Added subprocess tests that import the real `server.main`: one proves the child boots with the seeded env, one proves `REGENGINE_SKIP_SECRET_CHECK=true` refuses with the gate event in the output. Proven to fail with the calls removed |
| 10 | re-rv-3243-tests low | Low | `test_each_required_credential_is_checked` walks only `REQUIRED_PRODUCTION_CREDENTIALS`, so an empty tuple passes vacuously and Kafka is never covered | FIXED AND TESTED | Test now builds the same list the validator builds (always-on plus Kafka when `EVENT_BACKBONE=kafka`) and asserts it is non-empty. Trivial test-only change |
| 11 | re-rv-3243-ops medium (skip flag) | Medium | `REGENGINE_SKIP_SECRET_CHECK=true` aborts production import, and the error hint says to set `REGENGINE_ENV=development`, which cloud detection forces back to production | FIXED AND TESTED | Both error hints now say local development only and tell the operator to fix the credential or flag value instead. Abort behavior itself is intended and covered by existing tests |
| 12 | re-rv-3243-blast medium (route contract env leak) | Medium | `tests/sdk/test_route_contract.py` production child inherits placeholder Neo4j and storage values from sibling conftests and refuses to boot | FIXED AND TESTED | Production posture now pops the five Neo4j and storage vars and pins `EVENT_BACKBONE=pg`, mirroring the two tests PR #3243 already patched. Verified with a leak simulation run |
| 13 | re-rv-int-error-semantics medium | Medium | `SupplierGraphSync._get_driver` catches `RuntimeError` and no-ops with no log line, so a skipped graph mirror is invisible | FIXED AND TESTED | Handler now logs `supplier_graph_sync_missing_neo4j_credentials` at error level (names variables, never values). Existing admin test still passes |
| 14 | re-rv-int-env-docs medium 5 | Medium | `get_database_credentials` requires `POSTGRES_HOST` in production but `.env.example` never documents it | FIXED AND TESTED | Added `POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_PORT`, `POSTGRES_DB` to `.env.example` with a note that the monolith boots from `DATABASE_URL`. Template-only change, verified by inspection |
| 15 | re-rv-int-prod-boot high (FSMA operator gate) | High | `TestOperatorGate` prod child dies at `auth_runtime.py:99` because no `MFA_ENCRYPTION_KEY` is set (requirement added by PR #3238, not #3243) | FIXED AND TESTED | Seeded a runtime-generated Fernet key in the prod child env of the FSMA test, the OpenAPI contract child, the route-contract child, and the new fail-closed children. No key material stored in files. The strict requirement itself is untouched and belongs to the #3238 task |

## Test commands and results

All test commands were prefixed with `~/metacode/fleet/heavy` per fleet rules.
The shared `.venv` symlink was used read-only. No Postgres, no migrations, no
network calls beyond the queue wrapper.

1. `~/metacode/fleet/heavy .venv/bin/python -m pytest services/shared/tests/test_secrets_production_credentials.py services/shared/tests/test_secrets_fail_closed.py --no-cov -p no:cacheprovider`
   Result: `44 passed` (includes 9 new tests: prefixed values boot, 4 placeholder case variants, URI without password fails, URI with password passes, server.main boots, server.main refuses the skip flag, plus the strengthened kafka branch test).
2. Final combined run over every touched area:
   `~/metacode/fleet/heavy .venv/bin/python -m pytest services/shared/tests/test_secrets_production_credentials.py services/shared/tests/test_secrets_fail_closed.py services/admin/tests/test_gdpr_neo4j_erasure_1412.py services/admin/tests/test_supplier_graph_sync_prod_creds_fail_closed.py services/ingestion/tests/test_fsma_readiness_compat_2893.py tests/sdk/test_route_contract.py tests/contract/test_openapi_production_surface_2861.py::test_production_route_table_is_non_trivial --no-cov -p no:cacheprovider`
   Result: `66 passed, 60 warnings in 21.14s`. Warnings are pre-existing SQLAlchemy and rate-limiter notices.
3. `services/ingestion/tests/test_fsma_readiness_compat_2893.py` alone: before the MFA seed, `2 failed, 1 passed` in `TestOperatorGate` with `AuthRuntimeConfigurationError: MFA_ENCRYPTION_KEY is required for strict authentication`. After: `10 passed in 8.18s`.
4. Leak simulation for the route-contract scrub: `env OBJECT_STORAGE_ACCESS_KEY_ID=test NEO4J_PASSWORD=test KAFKA_BOOTSTRAP_SERVERS=localhost:9092 ... test_experimental_declaration_matches_production_route_table` Result: `1 passed`.
5. Fail-without-fix proofs (each fix temporarily edited away by hand, test run, fix restored, `grep TEMP-` verified clean after):
   - `test_server_main_refuses_skip_flag_in_production` with the two wiring calls removed from `server/main.py`: FAILED (server booted with checks disabled).
   - `test_prefixed_but_real_values_pass` with the old prefix comparison restored: FAILED with `NEO4J_PASSWORD is using an insecure default value` and both storage key errors.
   - `test_neo4j_uri_without_password_fails` with the URI rule disabled: FAILED (validation passed instead of raising).
   - `test_neo4j_skipped_when_password_not_set` with the erasure guard removed: `1 failed`.
6. Lint: `.venv/bin/ruff check` on all 10 touched Python files: `All checks passed!`. `ruff format` applied to 9 files (all HEAD-clean, so only new lines changed). `services/admin/app/erasure_routes.py` was already format-dirty at HEAD in unrelated hunks, so it was left unformatted; the new hunk there is format-clean.
7. Secrets scan: `gitleaks detect --no-git --config .gitleaks.toml` on both touched secrets test files: clean. (A bare run without the repo config flags synthetic test values that are also flagged at HEAD; the repo config allowlists them via the `pragma: allowlist secret` markers.)
8. `scripts/security/scan_tenant_scope.py`: not run, no queries were touched. Full test suite: not run (shared Mac, targeted files only per fleet rules).

## Operator checks before the next production deploy (cannot verify from the repo)

Railway dashboard values are not visible from this checkout, so C.Lee or the
release operator must confirm: `NEO4J_PASSWORD` and both object-storage keys
are either unset or real values (exact placeholders such as `neo4j` or `test`
still refuse boot); `REGENGINE_SKIP_SECRET_CHECK` is unset or `false`;
`EVENT_BACKBONE` is unset or `pg`, or `KAFKA_BOOTSTRAP_SERVERS` is set.

## Decisions needed from C.Lee

- D1: Should production reject loopback or sqlite `DATABASE_URL` values, or only a missing one? Rejecting them is the safer gate but breaks three committed tests that expect localhost and sqlite URLs to boot. Current fix keeps the repo contract (explicit URL boots, missing URL refuses).
- D2: Should an explicit non-production `environment=` argument stop overriding production detection in the credential getters? Changing it breaks the committed test that locks the override in.
- D3: The erasure path with `NEO4J_URI` set and no password now skips the graph delete with a warning while the HTTP response still reports the Postgres erasure as accepted. Flag if a half-wired Neo4j must instead fail the erasure response.
