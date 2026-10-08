# FIX-REPORT: tenant-scope SAST gate red on merged main (Blocker 2)

Done criteria: `python3 scripts/security/scan_tenant_scope.py` exits 0 and
`tests/security/test_tenant_scope_scan.py` passes, without loosening any rule.

## Findings

| # | Source report | Severity | Status | Reason |
|---|---------------|----------|--------|--------|
| 1 | re-rv-3246-correct, re-rv-int-semgrep-gates, re-rv-int-tenant-gate, re-rv-lead-ops: `traceability_linker.py:112` false positive, f-string map stripped by `PLACEHOLDER_RE` | High | FIXED AND TESTED | `QueryResolver` no longer strips literal `{...}` spans in f-strings; interpolations are still blanked, so unknown builder variables still fail closed. Regression test added. |
| 2 | re-rv-int-tenant-gate High 3, re-rv-3220-tenant: `get_governing_regulations` joins `(e:TraceEvent)` with no tenant predicate (BUG-002) | High | FIXED AND TESTED | Added `WHERE e.tenant_id = $tenant_id` to the Lot to event read. Former strict xfail now passes and the mark was removed. |
| 3 | re-rv-3220-tenant, re-rv-int-tenant-gate High 3: `get_impacted_lots` joins `(e:TraceEvent)` with no tenant predicate (BUG-003) | High | FIXED AND TESTED | Added `AND e.tenant_id = $tenant_id` alongside the existing Lot predicate. Former strict xfail now passes and the mark was removed. Operator precedence is safe: the shared predicate carries its own parens, giving `(A OR B) AND C`. |
| 4 | re-rv-3246-correct, re-rv-lead-ops: `_OBLIGATION_TENANT_PREDICATE` (`:31`) flagged as `tenant-failopen-shim` | High | FIXED AND TESTED | One baseline entry added with a written reason: Obligation nodes are a global catalog by design (regulation_loader and supplier_graph_sync MERGE them with no tenant_id), the equality arm confines private obligations, and `_require_tenant_id` rejects empty tenants so a null parameter cannot match every row. Product predicate unchanged, as pinned by existing linker tests. |
| 5 | re-rv-3246-correct Low, re-rv-int-semgrep-gates High 2-3, re-rv-int-tenant-gate High 2: two stale baseline entries | Medium | FIXED AND TESTED | Deleted `chain_integrity.find_gaps` (now raises on empty tenant and queries `e.tenant_id = $tenant_id`) and `tenant_nodes.RegulationOverride.merge_cypher` (now merges on `{override_id, tenant_id}`). Gate reports 0 stale entries. |

Skipped findings: none. Every cited violation above was confirmed by running
the scanner (exit 1 with the exact two fresh findings and two stale warnings
before the fix). Broader scanner hardening ideas in the reports (per-label
predicate checks, failing on stale baselines, reworking baseline keys) were
deliberately left out as beyond this blocker and its done criteria.

## Test commands and results

- `python3 scripts/security/scan_tenant_scope.py` -> `Tenant-scope query gate passed (0 stale baseline entries).`, exit 0. Before the fix: exit 1 with the `:31` shim and `:112` match findings plus the two stale warnings.
- `~/metacode/fleet/heavy .venv/bin/python -m pytest tests/security/test_tenant_scope_scan.py services/graph/tests/test_cypher_tenant_scope_scan.py services/graph/tests/test_traceability_linker_tenant_scope.py --no-cov -p no:cacheprovider` -> `84 passed, 4 skipped, 5 xfailed in 11.10s`. The 4 skips are catalog-allowlist reads (pre-existing). The 5 xfails are unrelated known gaps BUG-001/004/005/006/007 (separate owners).
- `~/metacode/fleet/heavy .venv/bin/ruff check` on all four touched Python files -> `All checks passed!`
- Fail-without-fix proof: with the scanner fix hand-reverted, new test `test_fstring_cypher_map_with_tenant_passes` FAILS (assertion at line 100); with the fix restored it passes. With the two product predicate lines hand-removed, `test_get_governing_regulations_composed_traceevent_scoped` and `test_get_impacted_lots_composed_traceevent_scoped` FAIL with QueryScopeError; with the fix they pass.
- One intermediate failure worth noting: the first version of the impacted-lots fix placed `AND e.tenant_id` directly after the shared predicate, which broke `test_get_impacted_lots_composed_obligation_predicate` (it requires `WHERE (predicate)` immediately before MATCH/RETURN/MERGE). The predicate was moved to the Lot WHERE clause instead; all tests pass.

## Notes needing C.Lee's decision

- BUG-001, BUG-004, BUG-005, BUG-006, BUG-007 remain open strict xfails owned by other teams; this task did not touch them.
- The scanner still resolves f-string interpolations opaquely (an unresolvable `{name}` is blanked, never inlined), so a tenant predicate that lives only inside a module constant interpolated into a query does not count toward scoping. Changing that would surface new shim findings at each use site; current behavior is pinned by a new test (`test_fstring_interpolation_alone_does_not_scope`). Say the word if you want inlining as follow-up work.

## Decision applied: Decision 3, Obligation quarantine (Oct 8, 2026)

Status: FIXED AND TESTED

C.Lee chose quarantine: an Obligation is shared across tenants only when
explicitly marked as the official regulation catalog. `_OBLIGATION_TENANT_PREDICATE`
in services/graph/app/traceability_linker.py changed from
`(o.tenant_id IS NULL OR o.tenant_id = $tenant_id)` to
`(o.tenant_id = $tenant_id OR o.catalog = true)`, used at all four read
sites (link fetch, GOVERNS write, get_governing_regulations,
get_impacted_lots). Both catalog writers now stamp the marker ON CREATE:
regulation_loader MERGEs `ON CREATE SET o.catalog = true`, and
supplier_graph_sync CTE_EVENT_QUERY MERGEs
`ON CREATE SET obligation.catalog = true`. Create-only anchoring means a
MERGE that matches a tenant-private row with the same key can never
promote it to the shared catalog. The gate baseline shim entry was
deleted as fixed (the shim text no longer exists) and the Obligation
catalog-label reason now names the marker. New one-time backfill script
scripts/backfill_obligation_catalog.py marks existing catalog-shaped
null-tenant rows; it was written but never run (no Neo4j in this
environment, and the task forbids running it here).

Test commands and results (all through ~/metacode/fleet/heavy):

- `python3 scripts/security/scan_tenant_scope.py` -> `Tenant-scope query gate passed (0 stale baseline entries).`, exit 0.
- `.venv/bin/python -m pytest services/graph/tests/test_traceability_linker_tenant_scope.py services/graph/tests/test_cypher_tenant_scope_scan.py tests/security/test_tenant_scope_scan.py -p no:cacheprovider --no-cov` -> `89 passed, 4 skipped, 5 xfailed in 6.95s`. The 4 skips are catalog-allowlist reads (pre-existing). The 5 xfails are the unrelated known gaps BUG-001/004/005/006/007.
- `.venv/bin/python -m pytest services/ingestion/tests/test_regulation_loader_hardening.py services/admin/tests/test_supplier_graph_sync_tenant_scoping.py -p no:cacheprovider --no-cov` -> `22 passed in 0.96s`.
- `.venv/bin/ruff check` on all eight touched Python files -> `All checks passed!`
- Fail-without-fix proof: with product code untouched, the updated tests failed as intended (8 failed in the linker test file, 3 obligation predicate failures in the cypher scan file, and both new writer marker tests failed); after the fix all pass. New guard `test_obligation_predicate_old_null_shim_rejected` goes red if the old IS NULL shape ever returns.

What must happen before a deploy:

- Run the backfill before this deploys, or regulation lookups go empty: `python3 scripts/backfill_obligation_catalog.py --dry-run` first to review counts, then `python3 scripts/backfill_obligation_catalog.py --apply`. Rows it leaves unmarked stay hidden from every tenant by design; review the printed quarantined sample ids.
- Note: mapping_engine and compliance Obligation reads use strict `o.tenant_id = $tenant_id` and never matched null-tenant catalog rows, so they are unchanged by this work and still cannot see catalog rows. If those paths need catalog access, that is a separate decision.
