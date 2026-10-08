# FIX-REPORT: PR #3245 vacuous QA tests

Merge commit 063ebc8d. Sources read: all six re-rv-3245 angle reports
(correct, security, tenant, tests, ops, blast), plus the lead-correct,
lead-tests, lead-tenant, lead-security, lead-ops, lead-blast, and
area-qa-ci summaries where they mention #3245. Production code is
unchanged by this fix; only tests, one load script, and CI wiring were
touched. No migrations added.

## Findings table

| # | Source report | Severity | Finding | Status |
|---|---|---|---|---|
| 1 | correct, lead-correct | High | k6 rls_isolation check result discarded, no checks threshold, cross-tenant page exits 0 | FIXED AND TESTED |
| 2 | tests (#10), area-qa-ci (#6) | High | tests/contract/test_service_contracts.py runs in no blocking job | FIXED AND TESTED |
| 3 | tests (#10) | High | Schema tests construct NormalizedEvent in-test, never call the producer, so a hand-built-dict revert stays green | FIXED AND TESTED |
| 4 | tests (#11), area-qa-ci (#6) | High | test_e2e_package_manifest, test_request_workflow_unit, test_compliance_control_plane_e2e run in no blocking job | FIXED AND TESTED |
| 5 | correct | Medium | k6 mixed marked/unmarked page passes on the marked subset | FIXED AND TESTED |
| 6 | correct, tests (medium) | Medium | RLS probe pytest.skips on SET ROLE failure after rolling back the caller transaction | FIXED AND TESTED |
| 7 | tests (medium) | Medium | Unit hash tests only call compute_manifest_hash, never assemble_response_package | FIXED AND TESTED |
| 8 | tests (medium), correct (low) | Medium | Compliance step2 ignores error/skip, ignores non-kde critical fails, deferred minority check passes with 13 of 14 deferred | FIXED AND TESTED |
| 9 | security (low #2) | Low | Same RLS probe skip as #6 | FIXED AND TESTED (same fix) |
| 10 | correct (low) | Low | Seeded preservation pass reported as skip on v089 leg | FIXED AND TESTED |
| 11 | correct (low) | Low | k6 rls_enforced returns true for any array | FIXED AND TESTED |
| 12 | tests (open question) | Low | Negative schema test docstring says neither S3 pointer while raw_s3_path remains | FIXED AND TESTED (wording) |
| 13 | security (low #1), correct (low) | Low | k6 empty export page returns true | Not fixed, see notes |
| 14 | tenant lead | OK | Manifest hash move keeps tenant in hash, no tenant effect | No change needed |

Fail-without-fix proof per finding is under Tests below. Finding 13 was
deliberately kept: an empty page shows no leak, and failing it would make
the load script flaky. The behavior is now documented in the script
comment.

## Out of scope (other tasks own these, noted only)

1. Suspended-tenant deny lives only in get_current_tenant, which no route
calls; live auth in services/shared/auth.py never reads tenants.status
(tenant lead H4, security lead critical). Not touched.
2. Tenant-scope SAST gate red on the merged tree
(scan_tenant_scope.py exit 1 on traceability_linker findings; scanner
owned by PR #3246 work). scripts/security/scan_tenant_scope.py was not
run because this fix touches no product queries.
3. The 7 xfail cross-tenant leaks (cypher scope scan, route isolation
matrix; PR #3237/#3240 work). Not touched.
4. actions startup_failure run 37841634345 and the RegEngine-Prod
deployment failure on 063ebc8d (ops open questions). No causal link to
this PR was found; nothing here changes container boot.

## Changes

1. tests/load/k6-admin-test.js: isolation check result captured into
errorRate, checks threshold rate==1 added, non-empty pages require every
item marked with the VU tenant (mixed pages fail), status-phase check
fails items carrying another tenant marker.
2. tests/test_e2e_tenant_isolation.py: SET ROLE failure now does a
defensive RESET ROLE, no rollback of the caller transaction, and
pytest.fail instead of pytest.skip.
3. tests/test_rls_probe_helper.py (new): 4 offline regression tests for
the probe helper with a fake session.
4. tests/test_request_workflow_unit.py: new TestAssembledPackageHashLinkage
(3 tests) assembling through the real method with a fake DB and asserting
the stored hash equals compute_manifest_hash of the stored contents.
5. tests/test_e2e_package_manifest.py: both inline hashlib copies replaced
with compute_manifest_hash; unused import removed.
6. tests/test_compliance_control_plane_e2e.py: step2 now fails on
error/skip results, fails any critical failure in any category, pins the
deferred set exactly to the relational-typed rules, keeps the minority
bound; docstring corrected.
7. tests/contract/test_ingest_nlp_schema_contract.py (new): offline
TestIngestionToNLPContract moved here plus TestProducerEmissionContract,
which calls the real _process_and_emit with mocked storage/parser/
settings/transport and validates the returned event and the published
Kafka payload against the NLP schema.
8. tests/contract/test_service_contracts.py: moved class replaced with a
pointer comment; live tests untouched.
9. tests/migrations/test_seeded_mid_chain_upgrade.py: preservation check
split into test_seeded_users_preserved_to_head (verdict on every leg).
10. .github/workflows/backend-ci.yml: 4 offline files added to the
blocking in-process suite; test_e2e_package_manifest.py added to the
request-workflow e2e step (covered by its skip hardening).

## Tests

All test commands were prefixed with ~/metacode/fleet/heavy. Local live
DB work used throwaway databases fleet_fx3245 and fleet_fx3245_seed on
localhost:5432 (superuser sellers), both dropped afterwards. No
background processes left running.

1. New offline batch:
~/metacode/fleet/heavy .venv/bin/python -m pytest
tests/test_request_workflow_unit.py
tests/test_compliance_control_plane_e2e.py
tests/test_rls_probe_helper.py
tests/contract/test_ingest_nlp_schema_contract.py -o "testpaths=tests"
-p no:cacheprovider --no-cov
Result: 61 passed in 1.22s

2. RLS helper fail-without-fix: helper temporarily restored to
rollback plus skip, new tests run.
Result on old code: 2 FAILED
(test_probe_fails_without_rolling_back_when_role_switch_fails,
test_probe_failure_is_a_failure_not_a_skip), 2 passed.
Result with fix: 4 passed. Fix restored (grep confirms pytest.fail
present, no skip path).

3. Assembler linkage mutation: call site temporarily set to "0" * 64.
Result on mutated code: 2 FAILED
(test_assembled_hash_matches_helper_digest,
test_insert_receives_helper_digest); pre-existing isolated-hash tests
stayed green, proving the reported hole. Restored; line 269 confirmed.

4. Compliance error-result probe (scratch file in /tmp, since removed):
first stateless evaluator patched to return result error.
Result: step2 FAILED at the new pass/fail assertion. Old code ignored
any result other than fail (only fail entered the critical branch) and
the deferred count check still held, so the old test passed this probe
by code reading.

5. Producer hand-built-dict mutation: Kafka send payload temporarily
replaced with dict(event_id, document_id).
Result on mutated code: 1 FAILED
(test_producer_emission_validates_against_nlp_schema). Restored; grep
confirms zero mutation markers.

6. Manifest e2e on throwaway DB at alembic head
(REGENGINE_MIGRATION_TEST_DB plus REGENGINE_REQUIRE_DB=1):
Result: 12 passed in 0.59s, zero skipped.

7. Full tenant isolation module on the same throwaway DB:
Result: 11 passed in 0.61s, zero skipped, so the SET ROLE regengine
probe executed rather than skipping.

8. Seeded split on the v089 leg (fresh empty throwaway DB, full
mid-chain rehearsal):
Result: 1 passed, 1 skipped in 2.14s
(test_seeded_users_preserved_to_head passed where the old shape
reported a skip; the v079-only email test still skips on this leg by
design).

9. Lint and syntax:
~/metacode/fleet/heavy .venv/bin/ruff check <8 changed test files>
Result: All checks passed!
~/metacode/fleet/heavy .venv/bin/ruff format (2 files reformatted,
tests re-run green).
node --check tests/load/k6-admin-test.js: k6 syntax OK.
YAML safe_load of backend-ci.yml: YAML OK.
Collect-only: test_service_contracts.py 22 tests, manifest 12 tests,
seeded file 7 tests (includes the new split test).

Not run: the full k6 load run (needs a live stack with 50 VUs), the
seeded rehearsal v079 leg (matrix leg, same code path as the verified
v089 leg), and the blocking CI jobs themselves (no push from this
worktree).

## Notes for Christopher

1. The remaining live-service contract file
(tests/contract/test_service_contracts.py, 22 tests) still runs in no
blocking job; qa-health.yml runs it continue-on-error. Gating it needs a
stack in CI, which is a bigger decision.
2. The checks threshold rate==1 in the k6 script now fails the whole run
on any failed check, including the pre-existing phase checks. That is
stricter than before; if load runs go red on flaky phase checks, scope
the threshold or mark the script non-gating.
3. Empty k6 export pages still pass isolation. If product wants fail-closed
on empty pages, say so and it is a one-line change.
4. The compliance step2 still dispatches through the evaluator registries
directly rather than RulesEngine._evaluate_single_rule. Wiring the engine
needs a DB session for the relational rules, so it belongs in the
live-DB rules-engine suite, not this offline test.
