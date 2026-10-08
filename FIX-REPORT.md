# FIX-REPORT: cross-tenant leaks marked xfail in the Cypher tenant-scope proof (PR 3237)

Worktree branch off origin/main e854dadc. All 7 xfail markers removed; each is now an enforcing test.

## Findings (one row per leak)

| # | Source report | Severity | Finding | Status | Reason / evidence |
|---|---|---|---|---|---|
| 1 | re-rv-int-tenant-gate BUG-001, re-rv-3237-tenant finding 4 | High | chain_integrity find_gaps: inner Lot in two NOT EXISTS subqueries had no tenant predicate, so another tenant's Lot suppressed the caller's genuine missing_lot gap | FIXED AND TESTED | Added WHERE l.tenant_id = $tenant_id at both sites (lines 53, 63). Static case now passes instead of xfail. |
| 2 | re-rv-int-tenant-gate BUG-002, re-rv-3237-tenant finding 5 | High | traceability_linker get_governing_regulations joined unscoped (e:TraceEvent), so a cross-tenant UNDERWENT edge leaked another tenant's governing obligations | FIXED AND TESTED | Scoped the event inline ({tenant_id: $tenant_id}). Runtime capture test now passes. OVERLAP: this file is also touched by the tenant-gate fix branch (gate violations at lines 31 and 112); my edit narrows to the two TraceEvent patterns only. |
| 3 | re-rv-int-tenant-gate BUG-003, re-rv-3237-tenant finding 5 | High | traceability_linker get_impacted_lots joined unscoped (e:TraceEvent) from the global Obligation, letting another tenant's event pull lots into the caller's impact list | FIXED AND TESTED | Scoped the event at first binding ({tenant_id: $tenant_id}). Runtime capture test now passes. Same file overlap as row 2. |
| 4 | re-rv-int-tenant-gate BUG-004, re-rv-3237-tenant finding 1 | High | lineage LINEAGE_BY_TLC_QUERY returned prev.tlc from unscoped OPTIONAL MATCH, and the Python invariant checked only the anchor fact, leaking another tenant's TLC | FIXED AND TESTED | Added WHERE prev.tenant_id = $tenant_id, so a foreign predecessor yields null instead of its TLC. Static case now passes. |
| 5 | re-rv-int-tenant-gate BUG-005, re-rv-3237-tenant finding 4 | High | data_quality analyze_kde_completeness counted a cross-tenant Lot as satisfying lot linkage, undercounting missing_lot | FIXED AND TESTED | Added WHERE l.tenant_id = $tenant_id inside the NOT EXISTS. Static case now passes. |
| 6 | re-rv-int-tenant-gate BUG-006, re-rv-3237-tenant finding 2 | High | overlay get_regulatory_requirements OPTIONAL MATCH into TenantControl had no predicate and returned dict(control) whole, exposing another tenant's control properties | FIXED AND TESTED | Matched (control:TenantControl {tenant_id: $tenant_id}). Static case now passes. |
| 7 | re-rv-int-tenant-gate BUG-007, re-rv-3237-tenant finding 3 | High | regulations get_requirement_mappings scoped o1/o2 but not joined s1/s2 Sections, leaking the other tenant's regulation name over a cross-tenant REQUIRES edge | FIXED AND TESTED | Added s1.tenant_id and s2.tenant_id strict predicates, matching the sibling section reads and the adjacent o1/o2 predicates. Runtime test now passes. First tried null-or-own, reverted because the blocking gate scanner rejects that shape as a shim; see decision note 1. |
| 8 | re-rv-int-tenant-gate (supplier_portal.py:342) | High | _db_update_portal_link_status updated fsma.tenant_portal_links by link_token alone, so a leaked token meant a cross-tenant write | FIXED AND TESTED | UPDATE now narrows by AND tenant_id = CAST(:tenant_id AS uuid) whenever the caller knows the tenant (both production callers pass the link's tenant). New regression tests fail on old code, pass on new. |

No finding was skipped: all 7 BUG-00x entries plus the portal update were confirmed in code and fixed. No other BUG-00x numbers exist in the proof file.

## Test commands and pass/fail lines

Baseline before any edit (proves the tests fail without the fix):

- `~/metacode/fleet/heavy .venv/bin/pytest services/graph/tests/test_cypher_tenant_scope_scan.py -q --no-cov -p no:cacheprovider` showed all 7 cases XFAIL (BUG-001 through BUG-007).
- New portal test `TestDbUpdateStatus::test_update_scopes_by_tenant_id` run against unmodified supplier_portal.py: FAILED with `assert 'tenant_id' in 'UPDATE fsma.tenant_portal_links SET status = :status WHERE link_token = :link_token'`.

After the fix (all through ~/metacode/fleet/heavy, single -q from pyproject so summaries print):

- `pytest services/graph/tests/test_cypher_tenant_scope_scan.py --no-cov -p no:cacheprovider --tb=short` => `52 passed, 5 skipped in 1.40s` (4 skips are by-design global catalog reads, 1 skip is the vacuous fixed-shape check over the now-empty gap list; 0 xfailed, 0 failed).
- `pytest services/ingestion/tests/test_supplier_portal_1342.py --no-cov -p no:cacheprovider --tb=short` => `65 passed in 1.80s` (includes the 2 new tests).
- `pytest services/graph/tests --no-cov -p no:cacheprovider --tb=no --ignore=test_neo4j_integration_testcontainers.py --ignore=test_recall_drill_queue_isolation.py` => `510 passed, 5 skipped in 79.17s`.
- `pytest tests/security/test_tenant_scope_scan.py --no-cov -p no:cacheprovider --tb=no` => `1 failed, 21 passed in 4.79s`. The single failure is the pre-existing `test_repo_gate_has_no_new_violations`, failing only on the 2 traceability_linker violations owned by the tenant-gate branch (line 31 null-or-own shim, line 112 gate-blind inline map). My changes add zero new gate violations.
- `python scripts/security/scan_tenant_scope.py` (touched queries, as ordered): output lists exactly the same 2 pre-existing linker violations, nothing new.
- `ruff check` on all 9 changed files: `All checks passed!`. `ruff format --check` on the 5 reformatted files: `5 files already formatted`.

Not run: test_neo4j_integration_testcontainers.py (needs Docker/Neo4j, unavailable), test_recall_drill_queue_isolation.py (blocked on missing ADMIN_DATABASE_URL env at import; fails identically with or without this change, unrelated files). No Postgres needed: all tests use fake sessions.

## Notes needing Christopher's decision

1. Section/Obligation catalog model is still unsettled globally (area finding B). I used strict equality for s1/s2 because the blocking gate rejects null-or-own and the query already uses strict o1/o2. But no in-repo writer stamps tenant_id on Section nodes (loader MERGEs them tenantless), so get_requirement_mappings returns empty for loader data until either the loader stamps tenant_id or the model moves to null-or-own with a gate baseline. Same question already covers mapping_engine.py Sections, which I left untouched as out of scope (no xfail covers it).
2. Overlap with the tenant-gate branch: it owns traceability_linker.py lines 31 and 112 (gate still red on those). My linker edits touch only the two TraceEvent patterns; expect a small merge intersection, no semantic conflict.
3. The supplier_portal baseline entry in .semgrep/tenant-scope-allowlist.yml now describes a fixed site (UPDATE text carries tenant_id when known). I left the allowlist for the gate owners; they may want to remove that entry. The token-only fallback path for tenant_id=None is intentionally preserved and locked by test.
