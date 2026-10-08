# FIX-REPORT for PR #3248 ([qa] Backend suite baseline, frontend green, previously ungated suites wired into CI)

Merge commit 712d2dd37b47fea4c880eed1f12f50512116bed3. All six specialist
reports (correct, security, tenant, tests, ops, blast including REPORT.md)
were present at start, so no waiting was needed. Angle leads (blast, correct,
ops, security, tenant, tests), area lead qa-ci, and int leads ci-workflows
and frontend-build were read for #3248 mentions. No chief report existed.

## Finding dispositions

| # | Source report | Severity | Finding | Status | Reason |
|---|---|---|---|---|---|
| 1 | tests Medium 1, ops Low, area 17, lead-tests list | Medium | `tests/audit` on the required pytest argv collects nothing (only `audit_trace_back.py`, `verify_chain.py`; `python_files = "test_*.py"`) | FIXED AND TESTED | Removed `tests/audit` from the blocking argv; comment now says hash-chain integrity is gated by `tests/security/test_audit_integrity.py`. Proved empty collection (exit 5) before the fix. |
| 2 | security High, tests Medium 2, area 7, lead-security Critical 13, lead-tests list | High | BE-011 strict xfail inside the required job: the redacted FDA CSV still embeds the portal link token, but the gate exits 0 over the expected failure | FIXED AND TESTED | Added `--ignore=tests/qa_sweep_20261002/test_portal_export_disclosure.py` to the blocking argv with a comment. The leak itself (finding 3) is untouched. New gate test pins this invariant both ways. |
| 3 | security High / lead-security Critical 13 (product half) | Critical | Redacted FDA export still carries `portal_id` and `supplier-portal:{token}` via leftover KDEs (`supplier_portal.py` ~513/519, `fda_export_service.py` ~274) | BLOCKED | Out of scope for this task: the order assigns the xfail cross-tenant leaks to other tasks. The CI masking is fixed (finding 2). Needs Christopher's decision on owner and on the suggested fix (non-secret submission id, strip both keys, delete the xfail). |
| 4 | security Low, lead-security medium list | Low | New blocking step does not fail on skipped modules: `pytest.importorskip("fastapi"/"httpx")` in `tests/ingestion/test_ingest_url.py` (covers SSRF cases) and two `tests/compliance` modules | FIXED AND TESTED | Removed all six `importorskip` calls. Each file already does `from fastapi.testclient import TestClient`, which raises at import time when the deps are missing (verified in the installed starlette), so a missing dep now fails collection instead of skipping. |
| 5 | blast Medium 1, lead-blast Medium | Medium | `tests/contract/conftest.py` autouse fixture deletes `privileged_auth:*` keys on the shared Redis later steps use | BLOCKED | Could not confirm as a defect, so no change. Read the fixture: it deletes only brute-force throttle counters plus in-memory throttle state, and no later step asserts on those counters. The area qa-ci lead independently checked and rejected this claim (finding 30). |
| 6 | blast Medium 2, area 18, lead-blast Medium | Medium | OpenAPI contract gate never runs on frontend-only changes: backend-ci path filters omit `frontend/**` while the test reads `frontend/src/lib/public-openapi.ts` | FIXED AND TESTED | Added `frontend/src/lib/public-openapi.ts` and `frontend/package-lock.json` to both push and pull_request paths. Rest of `frontend/**` stays out so frontend-only merges do not wait on the backend gate. |
| 7 | blast Medium 3 (marked as a guess by its own author) | Medium | `tests/compliance` and `tests/ingestion` import `services/*/main.py` in the same pytest process; unconfirmed `DATABASE_URL` fallback risk | BLOCKED | Could not confirm a failure, so no change. Confirmed the imports are fully qualified (`services.compliance.main`, `services.ingestion.main`), the merge is green on main, and all three modules pass locally with no `DATABASE_URL` set (39 passed, see below). |
| 8 | ops Medium, area 19, lead-ops 10 | Medium | `repo-root-suite` absorbed `npm ci`, ten new test dirs, and a 300s OpenAPI child with the timeout still at 15 minutes; a timeout fails the gate and blocks deploy | FIXED AND TESTED | Mitigation: raised `timeout-minutes` 15 to 25 with a comment. Whether the job exceeded 15 minutes was never measured (CI logs unreadable), so the larger split into a separate OpenAPI job suggested by reviewers was not attempted. |
| 9 | tests Low 3, area 29 | Low | Stale docstring in `services/ingestion/tests/test_qa_sweep_20261002_contract.py` still claims known defects are expected failures | FIXED AND TESTED | Docstring now says only BE-001 remains xfail (verified: single xfail at line 121). Trivial text fix, covered by the existing suite run. |
| 10 | security and tests open questions | Low | FE-002: `parseDigitalLink` calls `decodeURIComponent`, which throws on `%`, `%ZZ`, `%E0%A4`; green frontend job does not prove those scans are handled | BLOCKED | Listed without fixing per the low-severity rule. Needs Christopher's decision on whether a thrown URIError on the public scanner is acceptable. |
| 11 | security open question | Low | BE-001: naive timestamps are now treated as UTC (`webhook_models.py:205`) while the xfail still expects HTTP 422 | BLOCKED | Out of scope (naive-timestamp behavior belongs to the #3249/#3252 area). Listed only. |
| 12 | blast Low 4 | Low | Fast shard no longer ignores the two shared test files, so they run in two jobs | BLOCKED | Duplication, not a defect; the other workflow is not a required check. No change. |

Not run: `scripts/security/scan_tenant_scope.py` was not run because no queries were touched. The full `repo-root-suite` step was not run locally because it needs the CI Postgres and Redis services; the workflow YAML was validated by parsing, and the new gate test pins the argv shape instead.

## Exact test commands and results

All suite runs below went through the slot queue (`~/metacode/fleet/heavy`).

1. `~/metacode/fleet/heavy .venv/bin/pytest tests/test_ci_qa_gates_3248.py -q --no-cov -o testpaths=tests`
   Result: `....  [100%]`, 4 passed.
2. Fail-without-fix proof: the new test file was copied into a scratch dir
   populated with HEAD versions of `backend-ci.yml`, the three gated modules,
   and the disclosure test (via read-only `git show`, worktree untouched).
   Result: `4 failed in 0.31s`, one per finding (BE-011 ignore, audit argv,
   importorskip, spec path filter). Scratch dir removed afterwards.
3. Pre-fix collection proof: `.venv/bin/pytest tests/audit --collect-only -o testpaths=tests`
   Result: `no tests collected in 0.06s`, exit code 5.
4. `~/metacode/fleet/heavy .venv/bin/pytest tests/ingestion/test_ingest_url.py tests/compliance/test_api_endpoints.py tests/compliance/test_validate_rules_engine_golden.py -q --no-cov -o testpaths=tests`
   Result: 39 passed, 0 skipped (proves findings 4 and 7: no skips, imports fine with no `DATABASE_URL`).
5. `~/metacode/fleet/heavy .venv/bin/pytest services/ingestion/tests/test_qa_sweep_20261002_contract.py tests/qa_sweep_20261002 tests/test_ci_qa_gates_3248.py -q --no-cov -o testpaths=tests`
   Result: all passed; expected xfails only (3 BE-001 params, 1 BE-011).
6. `.venv/bin/ruff check` on the five changed Python files: `All checks passed!`
   `.venv/bin/ruff format --check` on the new test: clean after one reformat,
   test rerun green.
7. `.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/backend-ci.yml'))"`: ok.

## Needs Christopher's decision

1. Owner and approach for the BE-011 product fix (finding 3): persist a non-secret submission id and strip `portal_id` plus `supplier-portal:{token}` from export KDEs, then delete the xfail and the `--ignore` (the new gate test enforces the second half automatically).
2. Whether the FE-002 `decodeURIComponent` throw on malformed scans (finding 10) is accepted client behavior.
3. Optional: split the Node/OpenAPI contract work into its own gated job (reviewers' suggestion) instead of the 25-minute timeout headroom applied here.
