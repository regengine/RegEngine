# FIX-REPORT: PR #3227 re-review findings (merge a20cf21d)

Scope: confirmed CONCERN and BLOCKER findings for PR #3227 from the six
re-rv-3227-<angle> reports plus the angle and area leads that mention #3227.
Out of scope per task order (noted, not fixed): suspended-tenant deny on live
auth (PR 3238 H4), tenant-scope gate failure (PR 3246 H7/H8), 7 xfail
cross-tenant leaks (PR 3237 BUG-001 and siblings).

| # | Finding (source report) | Severity | Status | Reason |
|---|-------------------------|----------|--------|--------|
| 1 | /dashboard skips reconcile, honors internal-secret header tenant (tenant lead M1; security medium) | Medium | FIXED AND TESTED | `fsma_dashboard` now calls `reconcile_tenant_scope(api_key, tenant_id)` before the try block, same as sibling gaps routes |
| 2 | /harmonize skips reconcile, honors internal-secret header tenant (tenant lead M1; security medium) | Medium | FIXED AND TESTED | `harmonize_requirement` now reconciles and passes the scoped tenant to the engine |
| 3 | Harmonize reads/writes outside tenant database (tenant lead M2; security medium) | Medium | FIXED AND TESTED | `MappingEngine` accepts `database`, opens sessions on it; harmonize passes the tenant db name in Enterprise mode, None on Community |
| 4 | Harmonize mapping reads leave `Section` unscoped (tenant lead M2 second half; security medium) | Medium | BLOCKED | Needs catalog model decision: loader MERGEs `Section`/`Obligation` with no `tenant_id`, so a section predicate returns zero rows today. Same decision as finding 6 |
| 5 | `map_requirement` strict equality misses loader catalog obligations with null `tenant_id` (correct HIGH) | High | BLOCKED | Directly contradicts #3220 null-or-own model; area report defers this to Christopher ("pick one and fix the loader, the mapping reads, and the gate"). Changing the predicate here would also break the committed #3227 test asserting `IS NULL` is absent |
| 6 | `find_gaps` inner `Lot` in `NOT EXISTS` unscoped, cross-tenant edge hides gap flag (correct medium; security medium; BUG-001) | Medium | BLOCKED | Fixing the query trips the strict xfail in `test_cypher_tenant_scope_scan.py` (KNOWN_GAPS BUG-001, owned by the xfail task, out of scope). Runtime fix and xfail removal must ship together there |
| 7 | `merge_cypher` `ON MATCH SET r += $properties` can retag `tenant_id` (security low) | Low | FIXED AND TESTED | Trivial: ON MATCH now sets only `rule_id`, `parameter`, `value`; key fields stay in the MERGE pattern. No production caller exists, fail closed |
| 8 | Whitespace-only `tenant_id` passes `if not tenant_id` guards (correct low; area item 19) | Low | FIXED AND TESTED | Trivial: all four guards (`find_gaps`, `find_broken_chains`, `find_all_gaps`, `map_requirement`) also reject whitespace-only strings |
| 9 | Dormant override MERGE key duplication for pre-existing nodes (blast low) | Low | Not fixed | No in-repo writer or caller; needs a production data check first |
| 10 | Harmonize POST checks key presence, not a write scope (security low) | Low | Not fixed | No graph router checks scopes; needs a product decision on scope enforcement |
| 11 | Out-of-scope items owned by other tasks | n/a | Noted only | Suspended-tenant deny (3238 H4), scanner substring/stale-baseline gate (3246 H7/H8), 7 xfail leaks incl. BUG-001/002/003 (3237) |

## Test commands and results

New tests: `services/graph/tests/test_pr3227_followup_fixes.py` (10 tests:
whitespace guards x4, merge retag x1, engine database routing x3, route
reconcile pins x2).

1. `~/metacode/fleet/heavy .venv/bin/python -m pytest services/graph/tests/test_pr3227_followup_fixes.py services/graph/tests/test_tenant_required_graph_queries.py -q --no-cov -p no:cacheprovider`
   Result: 19 passed (10 new plus 9 existing #3227 tests, unbroken).
2. `~/metacode/fleet/heavy .venv/bin/python -m pytest services/graph/tests/test_chain_integrity_tenant_scope.py services/graph/tests/test_fsma_metrics.py -q --no-cov -p no:cacheprovider`
   Result: 33 passed.
3. `.venv/bin/python -m ruff check` on the five changed source files plus the
   new test file. Result: All checks passed.
4. `~/metacode/fleet/heavy .venv/bin/python scripts/security/scan_tenant_scope.py`
   Result: exit 1, pre-existing and out of scope. Failing sites are all in
   `services/graph/app/traceability_linker.py` (PR 3220 file, untouched here).
   The two STALE BASELINE notices (find_gaps shim, merge key) reference #3227-era
   snippets and are stale since #3227 itself, not since this fix.

## How old-code failure was confirmed

Each new test was checked against HEAD file content: HEAD routers contain no
`reconcile_tenant_scope(api_key, tenant_id` call; HEAD `merge_cypher` ON MATCH
clause is `t += $properties` with no pinned rule fields; HEAD `mapping_engine.py`
has no `_open_session` and no `database` init param (new engine tests raise
`AttributeError` there); HEAD chain_integrity has 3x bare `if not tenant_id:`
and whitespace strings are truthy in Python, so the old guards run the query
instead of raising.

## Needs Christopher's decision

1. Catalog model fight (#3220 null-or-own vs #3227 strict equality): whether
   `Obligation`/`Section` nodes are shared catalog (loader stamps no tenant)
   or per-tenant. This decides findings 4 and 5 plus the loader write path.
2. Whether harmonize POST should require a write scope (finding 10).
3. Whether any production Neo4j data has pre-existing `RegulationOverride`
   nodes merged on `override_id` alone or cross-tenant `UNDERWENT` edges
   (code review cannot answer; findings 6 and 9 depend on it).
