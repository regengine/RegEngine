# FIX-REPORT for PR #3224: [audit-medium] Neutralize spreadsheet formulas in recall CSV export

Merge commit ffdfed0b7beca63bafa635aeee59f9cd3b72ad8e.
Reports read: all six re-rv-3224-<angle> SUMMARY.md files (correct, security,
tenant, tests, ops, blast, plus re-rv-3224-blast/REPORT.md), and the lead
summaries that mention #3224 (lead-blast, lead-ops, lead-security,
lead-tenant, lead-tests), re-rv-area-data/SUMMARY.md, and
re-rv-int-deploy-readiness/SUMMARY.md.

## Findings

| # | Source report | Severity | Status | Reason |
|---|---|---|---|---|
| 1 | re-rv-3224-security (CONCERN): recall CSV writer missing `csv.QUOTE_ALL`, so a `;` inside a cell could open a new cell starting with a formula character for readers that split on `;` | Low | FIXED AND TESTED | Added `quoting=csv.QUOTE_ALL` to the `DictWriter` in `_build_csv_export`, matching the FDA export and the contract documented in `shared.fda_export.csv_safety`. New test `test_csv_output_quotes_every_field` fails on the old code and passes on the new code. |
| 2 | re-rv-3224-security (same CONCERN): `safe_cell` does not prefix a leading line feed or fullwidth formula starters (such as the fullwidth equals sign) | Low | BLOCKED | Fixing this means expanding `DANGEROUS_PREFIXES` in the shared helper `services/shared/fda_export/csv_safety.py`, which changes bytes for the FDA and compliance exports too, and existing test `test_dangerous_prefixes_includes_all_known` pins the current set. Needs C.Lee's decision (see below). Reachability is narrow: the recall endpoint only serializes canned scenario data plus counts, per the specialist's own analysis. |
| 3 | re-rv-3224-tests (Low): no test builds an `impact_graph` row, so a later change skipping sanitization for that view would still pass | Low | FIXED AND TESTED | Added `test_impact_graph_cells_with_formula_prefixes_are_neutralized` with a hostile link (`=evil-source`, `+evil-target`, hostile lot codes). Verified it fails when `sanitize_row` is bypassed and passes with the current code. |
| 4 | re-rv-3224-tests (Low note): `test_summary_view_safe_values_unchanged` is a passthrough check, not proof of the fix | Low | BLOCKED | No change required, stated as informational by the specialist itself. The proof is the timeline and contact-list tests plus the two new tests. |
| 5 | re-rv-3224-correct, re-rv-3224-tenant, re-rv-3224-ops, re-rv-3224-blast | None (OK verdicts) | BLOCKED | No findings to fix. Correct and blast confirm the only caller is `export_simulation` with `format=csv` and safe canned values stay byte-identical after parsing. |

No critical, high, or medium findings were filed against #3224 by any
specialist or lead. The security lead carries #3224 as a low-severity CONCERN
with narrow reachability.

Out of scope per the task order (owned by other tasks, only noted here): the
suspended-tenant deny on live auth, the tenant-scope gate failure, and the 7
xfail cross-tenant leaks. None of them touch the recall CSV export path.

## Exact test commands and results

All commands were run through the slot queue (`~/metacode/fleet/heavy`).

1. `~/metacode/fleet/heavy .venv/bin/pytest services/ingestion/tests/test_recall_simulations_1342.py services/ingestion/tests/test_csv_safety_1342.py services/ingestion/tests/test_fda_export_service_1342.py`
   Result: `153 passed in 10.00s`
2. `~/metacode/fleet/heavy .venv/bin/ruff check services/ingestion/app/recall_simulations.py services/ingestion/tests/test_recall_simulations_1342.py`
   Result: `All checks passed!`
3. Fail-without-fix confirmation for finding 1: with the `quoting=csv.QUOTE_ALL`
   argument temporarily removed by hand, `test_csv_output_quotes_every_field`
   FAILED (`AssertionError` on the unquoted header line
   `simulation_id,scenario_id,...`). After restoring the fix, it passes.
4. Fail-without-protection confirmation for finding 3: with `sanitize_row`
   temporarily bypassed by hand (`writer.writerows(rows)`),
   `test_impact_graph_cells_with_formula_prefixes_are_neutralized` FAILED at
   `test_recall_simulations_1342.py:601`. After restoring, it passes.

`scripts/security/scan_tenant_scope.py` was not run because no queries were
touched (the change is a CSV writer flag plus tests).

## Items needing C.Lee's decision

1. Whether to expand `DANGEROUS_PREFIXES` in the shared helper
   (`services/shared/fda_export/csv_safety.py`) with line feed and fullwidth
   formula starters (finding 2). This changes export bytes for FDA and
   compliance paths, not just recall, and breaks a pinned contract test, so it
   was left out as non-trivial for a low-severity, narrow-reachability item.
2. Nothing else. No migrations, no breaking changes, no production config
   touched.
