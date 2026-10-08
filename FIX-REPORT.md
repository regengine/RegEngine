# FIX-REPORT: PR #3237 Cypher tenant-scope proof findings

Worktree branch off origin/main e854dadc. PR #3237 merge commit 90dc0551.
Scope per order: confirmed CONCERN and BLOCKER findings for #3237 at
critical, high and medium severity. Out of scope and only noted here:
the suspended-tenant deny on live auth (PR #3237 does not touch auth;
the finding belongs to #3238), the tenant-scope gate failure
(scripts/security/scan_tenant_scope.py, belongs to #3246), and the 7
xfail cross-tenant leaks BUG-001 through BUG-007 (production query
fixes owned by other tasks).

## Finding table

| # | Source report | Severity | Finding | Status |
|---|---|---|---|---|
| 1 | correct-3237 H1, security-3237 High, tenant lead H1/H2, area-tenant H2/H4, int-tenant-gate High | High | 4 live reads xfailed green: chain_integrity NOT EXISTS Lot (BUG-001), data_quality Lot (BUG-005), overlay TenantControl (BUG-006), lineage prev TLC (BUG-004) | Noted, out of scope (one of the 7 xfail leaks, other task owns the query fix) |
| 2 | correct-3237 H2, tenant lead H3 | High | Section reads pass via CATALOG_LABELS while BUG-007 flags them; mapping_engine returns s fields on o predicate only | FIXED AND TESTED (see A below; BUG-007 query itself out of scope) |
| 3 | correct-3237 H3, tenant lead M8, security Low | Medium | Linker TraceEvent joins unscoped in get_governing_regulations (BUG-002) and get_impacted_lots (BUG-003) | Noted, out of scope (2 of the 7 xfail leaks) |
| 4 | correct-3237 M4, tenant lead low 8, security-3237 Med | Medium | Checker accepts substring alias.tenant_id, inline {id: $tenant_id}, comment tricks | FIXED AND TESTED (see B) |
| 5 | correct-3237 M4/M6, tenant lead low 6, security-3237 Med | Medium | One ALL() guard exempts every path; allowlist skips whole queries incl. unscoped Document | FIXED AND TESTED (see C, D) |
| 6 | correct-3237 M5 | Medium | list_regulations unlabeled (s) node unchecked, count may be catalog size | FIXED AND TESTED (see E) |
| 7 | tests-3237 High | High | Xfail covers whole literal, reverting the anchor predicate stays green | FIXED AND TESTED (see F) |
| 8 | tests-3237 Med | Medium | Section/Regulation treated as catalog though router filters them by tenant; deleting that filter stays green | FIXED AND TESTED (see A) |
| 9 | tests-3237 Low | Low | Dynamic inventory compares counts only, disposition never read | FIXED AND TESTED (trivial, see G) |
| 10 | tests-3237 Low, correct lead Med list | Low | BUG-007 xfail has no raises, setup error stays green | FIXED AND TESTED (trivial, see G) |
| 11 | correct-3237 Low 7 | Low | Scan root covers app only, not scripts | Not fixed (see Lows) |
| 12 | correct-3237 Low 8, tenant lead low 7 | Low | MERGE/CREATE literals dropped from scan entirely | Not fixed (see Lows) |
| 13 | tenant lead M8 (second half) | Medium | TraceabilityLinker opens its own driver session with no database name | Not fixed, noted (belongs with BUG-002/003 query fix) |
| 14 | tenant/security/area leads | Blocker-adjacent | Tenant-scope gate red on main; suspended-tenant auth deny | Noted, out of scope (owned by #3246 and #3238 tasks) |

## What was changed and why

A. Reclassified Obligation, Section, Regulation, Citation from
CATALOG_LABELS to REQUIRING_LABELS in
services/graph/tests/test_cypher_tenant_scope_scan.py. The loader
writes these with no tenant_id, but reads return their fields and no
writer prevents a future tenant-private row, so the checker now
requires a predicate on every read. Behavior-preserving null-or-own
predicates were added where a predicate was missing:
services/graph/app/mapping_engine.py (2 reads, s.tenant_id null-or-own),
services/graph/app/routers/regulations.py get_regulation_citations
(c.tenant_id null-or-own) and list_regulations (s.tenant_id
null-or-own). Verified no writer stamps tenant_id on Section or
Citation nodes (only services/ingestion/app/regulation_loader.py
MERGEs them, without tenant), so every current row has null tenant_id
and matches exactly as before.

B. Strict checker: alias predicates must now be
alias.tenant_id = $tenant_id equality (IS NOT NULL, <>, bare mention
rejected); inline maps must be tenant_id: $tenant_id ({id: $tenant_id}
and substring tricks rejected); /* */ block comments stripped in
addition to // comments.

C. Path guards must name their path variable and carry = $tenant_id,
and cover only that path's assignment region. Also fixed an off-by-one
the old exemption carried: the region started after the opening paren,
so the path's first node was never actually covered.

D. CATALOG_ALLOWLIST is now per label, not per query: each entry names
its waived labels, snippets were pinned so each matches exactly one
query, and the scan passes the waived labels into the checker instead
of skipping the whole literal.

E. Labeled the two anonymous (s) nodes (s:Section) in list_regulations
and get_regulation_citations and gave both a predicate (see A). Zero
behavior change on current data.

F. New non-xfailed test_known_gap_anchors_still_scoped locks the four
KNOWN_GAPS anchor predicates, so reverting one fails even though the
gap xfail remains.

G. New test_dynamic_inventory_runtime_covered (every disposition:runtime
site names a live test via RUNTIME_COVERAGE); raises=QueryScopeError
added to the four static xfail marks; raises=AssertionError added to
the BUG-007 mark so non-assertion setup errors go red.

## Test commands and results

1. Focused (scan file plus sibling tenant-required file):
`~/metacode/fleet/heavy .venv/bin/python -m pytest services/graph/tests/test_cypher_tenant_scope_scan.py services/graph/tests/test_tenant_required_graph_queries.py --no-cov -p no:cacheprovider -q`
Result: `71 passed, 4 skipped, 7 xfailed in 1.33s`
Baseline before the fix (scan file alone): `49 passed, 4 skipped, 7 xfailed`.

2. Full graph suite:
`~/metacode/fleet/heavy .venv/bin/python -m pytest services/graph/tests --no-cov -p no:cacheprovider --ignore services/graph/tests/test_recall_drill_queue_isolation.py`
Result: `520 passed, 7 skipped, 7 xfailed in 78.70s`
test_recall_drill_queue_isolation.py was excluded: 2 tests fail with
`RuntimeError: ADMIN_DATABASE_URL is required` from
services/admin/app/database.py at setup. That file imports only
server.workers.task_processor and fsma_recall modules, none of the 4
files changed here, so the failure is environmental and unrelated.

3. Lint: `ruff check` on the 4 changed files: `All checks passed!`.
`ruff format` applied to test_cypher_tenant_scope_scan.py (HEAD was
format-clean, the drift was mine).

4. Gate (touched queries, per order):
`~/metacode/fleet/heavy .venv/bin/python scripts/security/scan_tenant_scope.py`
Result: exit 1 both before and after this change (already red on main,
owned by the #3246 task). Delta from this change: 3 new
tenant-failopen-shim flags on mapping_engine.py:77,
regulations.py list_regulations and get_regulation_citations, because
the gate SHIM_RE matches property null-or-own
(x.tenant_id IS NULL OR ...) the same as the fail-open parameter shim
($tenant_id IS NULL OR ...). Strict equality would avoid the flags but
would filter out every loader-written catalog row, which is a certain
behavior break. The gate needs to learn the property-vs-parameter
distinction; flagged for Christopher below.

## How the new tests were proven to fail without the fix

The old checker was extracted read-only
(git show HEAD:... to /tmp) and all 7 weak shapes in
test_checker_rejects_weak_predicate_shapes were run through both
checkers. Shapes is-not-null, not-equal, wrong-inline-key,
substring-inline and block-comment: OLD checker passes them silently
(proof of the hole), NEW checker raises QueryScopeError. Shapes
second-unguarded-path and weak-guard raise on both, but on the old
checker only because its path exemption was dead code (the off-by-one
in C); they lock the new bound-guard semantics. The sibling test's new
Section assertions fail without the fix: HEAD mapping_engine contains
0 occurrences of "s.tenant_id IS NULL".

## Lows listed without fixing

* Scan root covers app only (correct-3237 low 7): scripts
  (inventory_tenant_collisions, load_frameworks) intentionally run
  unscoped MATCH reads and are covered by scan_tenant_scope.py, which
  scans scripts. The module docstring already states the app root.
* MERGE/CREATE literals skipped (correct-3237 low 8): documented
  out-of-scope-by-design in the file, covered by per-module regression
  tests. Scanning MATCH clauses inside write templates needs
  clause-level parsing, disproportionate here.
* Fulltext search_regulations yields an unlabeled `node`: checker-blind
  by design (unlabeled non-path nodes). The query does filter
  node.tenant_id = $tenant_id. Flagging all unlabeled nodes would need
  the data decision in (2) below first.

## Needs Christopher's decision

1. Null-or-own vs strict equality for mixed catalog reads. This change
uses null-or-own for Section/Citation (matching the linker's
documented Obligation design). The #3246 gate treats that shape as a
shim, and the BUG-007 xfail text prescribes strict s1/s2 equality,
which would hide every loader-written global section. Somebody must
pick one rule for all four labels before the BUG-007 and gate tasks land.
2. get_regulation_sections (regulations.py:69-70) already filters
s.tenant_id = $tenant_id strictly, which matches zero loader-written
rows today (dead filter, endpoint returns no sections on catalog
data). Change it to null-or-own as well, or confirm sections are
meant to be tenant-private and fix the loader to stamp them.
3. Document waiver residual: on default Community Neo4j both clients
share one database, so a tenant Document behind an IN_DOCUMENT edge
would be returned unscoped. No in-repo writer creates that edge.
Confirm tenant Documents can never sit behind it, or scope the read.
4. If any writer ever stamps tenant_id on Section, Regulation, Citation
or Obligation rows, null-or-own keeps working, but say so explicitly
so the proof stays honest.
