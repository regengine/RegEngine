# FIX-REPORT: PR #3220 (merge a587084b, scope obligation lookups by tenant)

Sources read: all six re-rv-3220-<angle> SUMMARY.md files (correct, security,
tenant, tests, ops, blast, plus blast REPORT.md), and every lead, area and
integration report mentioning #3220 (lead-blast, lead-ops, lead-security,
lead-tenant, lead-tests, area-tenant, int-backend-suite, int-perf,
int-rollback, int-semgrep-gates).

## Findings

| Source report | Severity | Status | Reason |
|---|---|---|---|
| re-rv-3220-security Medium: null tenant_id still matches every obligation (traceability_linker.py:31), carried as lead-security #19 | Medium | BLOCKED | Code fact confirmed, but the suggested fix (strict `o.tenant_id = $tenant_id`) contradicts the documented design and later locked tests; needs C.Lee decision, see below |
| re-rv-3220-security Low: `get_governing_regulations` and `get_impacted_lots` do not scope the joined TraceEvent (traceability_linker.py:112-132) | Low | Not fixed (low) | Overlaps the out of scope BUG-002/BUG-003 xfails owned by another task; adding the predicate would flip those strict xfails to XPASS failures |
| re-rv-3220-tests Medium: cross-tenant test pre-seeds its own empty row (test file lines 161-168), carried by lead-tests | Medium | FIXED AND TESTED | Test now also asserts the exact captured Cypher predicate, so a predicate revert fails it |
| re-rv-3220-tests Medium: substring checks pass wrong booleans such as OR true (test file lines 129-204), carried by lead-tests | Medium | FIXED AND TESTED | All four query tests now assert the exact WHERE clause through a literal helper, plus a new OR-true mutation test |
| Out of scope per task brief: tenant-scope gate failure (int-backend-suite High, int-semgrep-gates BLOCKER on linker :31 and :112) | n/a | Noted only | Owned by another task |
| Out of scope per task brief: 7 xfail cross-tenant leaks, including BUG-002/BUG-003 on these queries | n/a | Noted only | Owned by another task |
| Out of scope per task brief: suspended-tenant deny on live auth | n/a | Noted only | No 3220 report raised it against these routes; tenant angle verified key-bound tenant resolution |
| int-rollback High: reverting 3220 while keeping 3237/3246 breaks them | n/a | Noted only | Informational revert-ordering note, no code change needed |
| re-rv-3220-correct, tenant, ops, blast: no findings | n/a | n/a | Nothing to fix |

## Why the security Medium is BLOCKED, not fixed

Three facts from the code, all verified by reading:

1. Obligation nodes are a shared global catalog by design. The only in-repo
   writers (`services/ingestion/app/regulation_loader.py:132`,
   `services/admin/app/supplier_graph_sync.py:157`) MERGE without any
   `tenant_id`, and neither sets an `id` property. Strict equality would make
   every catalog read return nothing, breaking the feature the PR protects.
2. PR #3237 (commit 90dc0551, merged later) locks the exact
   `(o.tenant_id IS NULL OR o.tenant_id = $tenant_id)` predicate into passing
   non-xfail scan tests (`test_cypher_tenant_scope_scan.py` lines 808-858).
   Switching to strict equality breaks those tests.
3. The sibling strict-equality reads (`mapping_engine.py:78-79`,
   `compliance.py:977`) match different node shapes
   (`{text: $id}` via REQUIRES, `{tenant_id: $tenant_id}` property match),
   so they are not proof this linker can do the same on catalog nodes.

The report itself calls exploitability "a gap, not a closed hole" and guesses
about hand-loaded nodes with `id` set and no `tenant_id`, which no in-repo
evidence confirms. The honest fix is a catalog redesign (private obligations
on a separate label, strict equality on `:Obligation`), which is beyond the
smallest correct change. Decision needed from C.Lee, listed below.

## Code change

`services/graph/tests/test_traceability_linker_tenant_scope.py` only; no
production code touched:

- Added `_EXPECTED_OBLIGATION_PREDICATE` literal, `_OBLIGATION_WHERE_RE`
  regex and `_assert_obligation_scoped` helper (literal expectation, never
  imports the product constant).
- All four query tests assert the exact WHERE clause before MATCH/RETURN/MERGE
  with `$tenant_id` bound and no interpolation, replacing substring checks.
- Cross-tenant test now asserts the captured Cypher carries the exact
  predicate, so deleting the predicate fails the test.
- New `test_obligation_predicate_rejects_or_true_mutation` proves an
  OR-true-weakened predicate is rejected.

## Test commands and results

1. `~/metacode/fleet/heavy .venv/bin/python -m pytest services/graph/tests/test_traceability_linker_tenant_scope.py -q --no-cov`
   Result: `......... [100%]`, 9 passed.
2. Fail-without-fix probe `/tmp/probe_3220.py` (monkeypatches the predicate to
   the pre-PR empty shape and to an OR-true variant containing all old
   substring tokens, then runs the new assertions):
   Result: `pre-PR (empty predicate): both queries REJECTED by new assertions`,
   `OR-true mutation: REJECTED by new assertions (old substring checks passed it)`,
   `PROBE OK`.
3. `~/metacode/fleet/heavy .venv/bin/python -m pytest services/graph/tests/test_cypher_tenant_scope_scan.py -q --no-cov -k "obligation or governing or impacted or linker"`
   Result: 7 passed, 2 xfailed (BUG-002 and BUG-003, the out of scope xfails).
4. `~/metacode/fleet/heavy .venv/bin/ruff check services/graph/tests/test_traceability_linker_tenant_scope.py services/graph/app/traceability_linker.py`
   Result: `All checks passed!`
5. `scripts/security/scan_tenant_scope.py` was not run: no queries were
   touched (test-only change), and the gate failure is out of scope.

## Needs C.Lee's decision

1. Null-tenant obligation readability: keep the shared-catalog
   `IS NULL OR` predicate (current, locked by PR 3237 tests), or redesign so
   tenant-private obligations live on a separate label with strict equality
   on `:Obligation`? The security reviewers want the latter; it changes
   product behavior for the global catalog.
2. TraceEvent scoping (BUG-002/BUG-003) and the red tenant-scope gate are
   owned by other tasks; confirm they stay out of this lane.
