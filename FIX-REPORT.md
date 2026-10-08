# FIX-REPORT: PR #3246 tenant-scope query gate

Merge commit 242420eb. Scanner: scripts/security/scan_tenant_scope.py.
Gate status after this fix: exit 1, 0 stale baseline rows, 60 fresh
findings for owning-team triage (grouped below). No product code changed.

## Finding table

| # | Source report | Severity | Status | Reason |
|---|---|---|---|---|
| F1 | correct-H1, security-H1, tenant-H7, lead-security-3246a: any mention of tenant_id/org_id/tid counts as predicate | High | FIXED AND TESTED | Real comparisons required per label and per table. Comments, string literals, select lists, SET targets, join conditions, and bare :tid values no longer count. MERGE needs tenant_id in the merge map. |
| F2 | correct-H2, security-H2, tenant-H8, lead-security-3246b: one key hides all queries in a function, stale rows exit 0 | High | FIXED AND TESTED | Baseline rows pin the reviewed query text with qhash. Stale rows fail the run (exit 1). 9 multi-query keys expanded into per-query rows. |
| F3 | correct-H3, security-H2, tenant-H8: two shipped baseline rows match nothing | High | FIXED AND TESTED | Deleted find_gaps shim row and merge_cypher row. Both sites verified fixed in product code first. |
| F4 | correct-H4: assignment resolution uses empty map, first wins, includes nested functions | High | FIXED AND TESTED | Source-order walk, last assignment wins, nested scopes excluded. AnnAssign also handled. |
| F5 | security-H3: f-string eraser deletes Cypher maps and interpolated predicates | High | FIXED AND TESTED | Literal doubled braces preserved, module and local names inline into holes, unresolvable holes keep a marker instead of vanishing. The :112 false positive is gone. |
| F6 | correct-M5: comma FROM list checks only the first table | Medium | FIXED AND TESTED | FROM lists split on top-level commas (paren aware), every table checked. |
| F7 | correct-M6, security-M5: global_catalog_labels ignored by the gate | Medium | FIXED AND TESTED | Catalog set flows into analyze_text. Catalog-only labels exempt; Document and Provision stay fail-closed as TENANT_LABELS members. |
| F8 | security-M4: second-position and backtick labels missed | Medium | FIXED AND TESTED | Node patterns parsed per label with backtick support; binds and map keys excluded by context. |
| F9 | tenant-M4: unqualified table names invisible | Medium | FIXED AND TESTED | Bare names matching a known fsma tenant table are flagged as fsma.name. Unknown bare names stay ignored. |
| F10 | tenant-M3: shim regex over-matches, f-string artifact reddens gate | Medium | FIXED AND TESTED | Shim exempts catalog-alias uses with real node patterns; parens and coalesce variants now match. The bare shim constant stays flagged fail-closed by design. |
| F11 | security-M6: unreadable files and missing roots exit 0 | Medium | FIXED AND TESTED | Missing roots, unreadable files, and syntax errors raise ConfigError, exit 2. |
| F12 | tests-H: scanner tests outside the merge gate | High | FIXED AND TESTED | Unit file added to the blocking backend-ci offline step (backend-ci already triggers on scripts/**). scripts/** and .semgrep/** added to test-suite-check filters. Live-tree test split into test_tenant_scope_gate.py, kept out of blocking suites until the tree is green. CI run itself is not observable from here; YAML validity checked locally. |
| F13 | tests-M: no test calls main or checks exit codes | Medium | FIXED AND TESTED | Subprocess tests assert exit 0 clean, 1 on violation, 1 on stale-only, 2 on missing allowlist. Missing root raises ConfigError. |
| F14 | tests-M: DELETE and INSERT untested | Medium | FIXED AND TESTED | Flagged and passing cases for both verbs added. INSERT counts a tenant column mention (it has no WHERE); upsert ON CONFLICT tails are not second statements. |
| B1 | ops-H, blast-Critical, int-tenant-gate, int-semgrep-gates: gate exits 1 on main | Blocker | BLOCKED | Out of scope. Owned by re-fix-tenant-gate. The 60 fresh hits are listed below for triage. |
| B2 | ops-M: repo-gate test red in fast shard | Medium | BLOCKED | Same family as B1. Test moved to test_tenant_scope_gate.py, still non-blocking. |
| B3 | lead-security Critical 1: suspended tenant API keys still accepted | Critical | BLOCKED | Out of scope. Owned by re-fix-suspended-tenant. Untouched. |
| B4 | 7 xfail cross-tenant leaks (lead-security 3237, int-tenant-gate) | High | BLOCKED | Out of scope. Owned by re-fix-xfail-leaks. Four overlap fresh gate hits (linker TraceEvent x2, chain_integrity Lot, overlay TenantControl, data_quality Lot). |
| L1 | correct-L7, security-L7, tenant-L5: semgrep editor rules never match tenant labels, unwired | Low | Not fixed | Left unwired on purpose until the tree is green. See decision D4. |
| L2 | security-L8: SECURITY DEFINER SQL and scripts outside the gate | Low | Not fixed | Dynamic function names stay unjudged and unflagged (documented limitation). |
| L3 | tests-L: semgrep never executed, catalog test gap | Low | Partly fixed | Plus-concat and Document fail-closed cases added. Semgrep execution still absent. |
| L4 | lead-security low: merge_cypher ON MATCH SET can retag tenant_id | Low | Not fixed | Product code owned by graph team. Flagged in notes. |

## Test commands and results

1. `~/metacode/fleet/heavy .venv/bin/python -m pytest tests/security/test_tenant_scope_scan.py tests/security/test_tenant_scope_gate.py --no-cov -p no:cacheprovider`
   Result: `1 failed, 53 passed in 3.23s`. The single failure is
   test_repo_gate_has_no_new_violations (60 fresh tree findings, expected,
   see B1). Its sibling test_repo_gate_has_no_stale_baseline_entries passes.
2. `.venv/bin/python scripts/security/scan_tenant_scope.py`
   Result: exit 1, 0 stale rows, 60 fresh findings. Same 60 before and
   after the final cleanup edits (diffed, identical).
3. `.venv/bin/python /tmp/old_probe.py` against the pre-fix scanner from
   git HEAD: all 12 key assertions (select list, comment, literal, SET,
   :tid value, MERGE SET, comma FROM, backtick, second label, other node,
   coalesce, parenthesized shim) fail on old code and pass on new code.
   qhash pinning and stale-exit-1 confirmed by code reading of old main.
4. `.venv/bin/ruff check` on the three Python files: All checks passed.
   `.venv/bin/ruff format` applied (repo enforces it via pre-commit).
5. YAML parse of backend-ci.yml, test-suite-check.yml, and the allowlist:
   OK. Full-suite and CI runs not done here: the change is covered by the
   targeted files, and CI is not observable from this checkout. No Postgres
   was needed; every test is offline. No migrations added.

## Fresh gate hits for owning-team triage (60)

Out of scope for this task; each needs a product fix or a baseline row
with a reason from its owning team. I read the flagged query plus its
enclosing function for every site below. Items marked builder or context
rely on the seeding or guard visible there, which the owning team must
confirm before baselining.

1. Other tasks own these, do not duplicate: traceability_linker.py:31
   (bare shim constant, intentionally still flagged), :112 and :126
   (TraceEvent hops, xfail-leaks family), chain_integrity.py:47 Lot
   (BUG-001, xfail-leaks), overlay_resolver.py:59 TenantControl (H2,
   xfail-leaks), data_quality.py:239 Lot (xfail data_quality count).
2. Runtime-seeded WHERE builders, statically invisible (team confirms the
   seed, then baselines with the standard builder reason):
   audit_export_log.py:146 (conditions seeded with tenant_id = :tid,
   verified), auditor_router.py:253 (dynamic where_sql plus RLS backstop),
   exchange_api.py:109, fda_export/queries.py:148, 306, 649,
   compliance_score.py:169, task_queue.py:758 (_claim_one, global queue
   role), agent_operator_view.py:147, 164, exception_queue.py:338,
   request_workflow/queries.py:32, canonical_persistence/writer.py:1263.
3. Joined or correlated tables with the predicate on the sibling (same
   shape as the baselined epcis_export reason): compliance_score.py:295
   (cte_kdes joined on scoped event) and :1154 (NOT EXISTS),
   webhook_router_v2/validation.py:193 (hash_chain joined on scoped event),
   auditor_router.py:556 and :606 (correlated signoff, package, and
   submission counts), remediation/service.py:881, 916, 934 and
   remediation/state.py:109 (correlated EXISTS and subselects),
   assembly.py:480, 605, 644, request_workflow/queries.py:74,
   canonical verification.py:175, cte_persistence verification.py:59, 197
   and queries.py:713 and writes.py:351 and batch.py:477 (hash_chain paired
   with scoped events), canonical writer.py:1294, identity_resolution
   matching.py:47, 183, 228 and review.py:431 and assembly.py:177 (entity
   tables), task_processor.py:518 (global admin claim).
4. Token, id, or message keyed reads with no tenant predicate (team
   decides predicate vs token-as-auth baseline like the sibling row):
   supplier_portal.py:245 (SECURITY DEFINER function), :269 and :307
   (link_token reads), email_ingest/service.py:124 (message_id, SECURITY
   DEFINER), mock_audit.py:100 (drill_id), inflow_workbench.py:623
   (run_id, tenant context is set), remediation/service.py:830
   (run listing), metrics_router.py:119, agent_operator_view.py:412, 476.
5. Deliberately global reads needing explicit acceptance plus baseline:
   fsma_audit.py:364 and :890 (hash-chain control plane, same family as
   the baselined _load_last_checksum), compliance_integration.py:155
   (finds which tenants own lot codes; only runs when tenant_id is None),
   tenant_models.py:113 (creates a hash-keyed Provision node),
   snapshots.py:309 (dual-key tenant_id OR null-tenant with org fallback).
6. Tenant-suffixed or correlated shapes the strict rule still flags but a
   team may clear with a one-line predicate: auditor and remediation rows
   in group 3 whose subquery is the only unscoped part.

## Decisions needed from Christopher

D1. Who triages the 60 fresh hits above, and in what order. Highest
   information value first: snapshots.py:309 (real null-tenant OR shape),
   supplier_portal reads (secret-token keying), compliance_integration
   cross-tenant lookup (accept the design or scope it).
D2. Bare shim constants stay flagged by this scanner (linker :31). If
   re-fix-tenant-gate baselines it instead, that row needs a qhash and a
   catalog-design reason, or the two tasks will fight over the same site.
D3. compliance_integration.py:155 reads every tenant on purpose when no
   tenant is passed. Accept and baseline, or require a tenant argument.
D4. Keep .semgrep/tenant-query-scope.yaml out of the blocking semgrep
   step until the tree is green and baselines are gone, as its own header
   already says. Recommended: yes.
D5. merge_cypher ON MATCH SET r += $properties can overwrite tenant_id if
   a caller passes it in the properties map. No production caller does
   today. Graph team should either strip tenant_id from that map or assert
   it matches.
