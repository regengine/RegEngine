# QA coverage and verification boundaries

PR: opened by orchestrator

CI status: pending at time of writing

## Comparable before and after measurements

Coverage denominators are held constant within each comparison. Backend measurements use the same selected modules and existing tests before, then add the QA regressions after. Frontend measurements use Node 20.20.2, the same 196 instrumented product files and unchanged coverage exclusions/thresholds. These are local results, not a repository-wide or deployed coverage claim.

| Scope / metric | Before | After | Change |
| --- | ---: | ---: | ---: |
| Backend selected ingestion statements | 531/816 (65.07%) | 540/816 (66.18%) | +9 statements, +1.10 percentage points |
| Backend selected shared statements | 607/1013 (59.92%) | 607/1013 (59.92%) | No change |
| Frontend statements | 6215/9184 (67.67%) | 6219/9184 (67.71%) | +4 statements |
| Frontend branches | 4664/7755 (60.14%) | 4668/7755 (60.19%) | +4 branches |
| Frontend functions | 1285/2142 (59.99%) | 1285/2142 (59.99%) | No change |
| Frontend lines | 5825/8327 (69.95%) | 5827/8327 (69.97%) | +2 lines |

The GS1 parser specifically increases from 92/96 to 94/96 lines, 108/120 to 112/120 statements and 82/99 to 86/99 branches. Existing broad coverage did not prevent its lot-code boundary bug. Backend branch coverage was not enabled; statement coverage must not be described as branch coverage.

## Executed test scope

| Test selection | Before | After | Meaning |
| --- | --- | --- | --- |
| Focused ingestion | 65 passed | 75 passed, 14 strict expected failures | CSV parsing, webhook models, authz, route-level input errors, batch OpenAPI boundaries |
| Focused shared/auth/security | 210 passed, 1 real-Redis case deselected | 213 passed, 2 strict expected failures, same deselection | Tenant/auth/permissions, idempotency/HMAC/canonical checks plus request-limit and export-capability witnesses |
| New backend tests only | Absent | 13 passed, 16 strict expected failures | 29 cases; 140 deterministic Hypothesis examples within two property tests |
| Full frontend unit/component suite | 136 files; 1027 passed, 2 skipped | 137 files; 1033 passed, 7 expected failures, 2 skipped | Includes complete existing Vitest selection plus GS1 and offline-photo regressions |
| Added frontend tests | Absent | 6 passed, 7 expected failures | Includes 1,000 generated GTIN checksum checks within one passing test |

Expected failures execute intended-behavior assertions and identify the matching finding. They are evidence of defects, not passing product behaviors. `--runxfail` and frontend standalone/temporary negative controls reproduce the failures without editing product source. Detailed commands and outcomes are in [Backend QA](BACKEND-REPORT.md), [Frontend QA](FRONTEND-REPORT.md), and their separate session logs. Coverage includes executed lines in expected-failure tests.

A separate backend compatibility retest overlaid the exact locked FastAPI, Starlette, Pydantic/core and supporting pins in `/private/tmp`; all 29 added cases retained the same **13 passed, 16 strict expected failures** ([result](artifacts/backend/20261003T004902.545619Z-locked-runtime-added-tests.txt)). This verifies the defects with the locked core framework versions, but is not a clean full-lock install or the environment used for the before/after coverage comparison. Isolated admin authorization/session tests additionally passed **34 cases**; route-manifest tests have a separate unresolved omitted-operation inventory discrepancy (enabled classifications unchanged).

## Reports and denominators

- Backend machine reports are in [artifacts/backend](artifacts/backend/); [BACKEND-REPORT.md](BACKEND-REPORT.md) maps exact before/after artifacts to source modules and lists all broad-suite attempts.
- Frontend [comparison](artifacts/frontend/coverage-comparison.json), [before per-file summary](artifacts/frontend/coverage-node20-before-summary.json), [after per-file summary](artifacts/frontend/coverage-node20-after-summary.json), and [changed-file comparison](artifacts/frontend/coverage-changed-files.json) retain numerators and denominators. Generated HTML/source copies were moved out of the handoff; the original interrupted artifacts remain intact.
- An early Node 26 baseline is retained for provenance. It is not mixed into the authoritative Node 20 before/after comparison.
- Broader backend runs improve exploration breadth but have different source scopes, failed tests, exclusions, or collection limits. Their percentages are partial-run observations and must not be compared with the narrow baseline as a coverage improvement. Pass counts across overlapping runs must not be added together.

## Remaining gaps

- Live PostgreSQL RLS, real tenant grants, persistence transactions, database export round-trips, Redis multiworker races, scheduler/provider effects and real authentication lifecycle were not exercised. Stubbed boundaries establish local decisions only.
- The full FSMA rule catalog, every CTE variant, full FDA export golden-file matrix, MFA/WebAuthn lifecycle and all authenticated dashboard workflows were not exhaustively validated. The sweep emphasizes the selected ingest/auth/evidence boundaries and does not certify regulatory correctness of the whole product.
- Broad backend collection contains optional-dependency/module-stub and isolated-process issues. Network and subprocess fixtures cannot pass under the sweep guard. A complete green backend suite is not established; exact failed attempts are retained in the backend log.
- Vitest measured 196 product files; the inventory includes 672 non-test TS/TSX files (including type-only modules). Uninstrumented files are absent from these percentages. Low measured areas include dashboard heartbeat, alerts, API hooks and API-client branches.
- Cross-browser Playwright launches were attempted but blocked by macOS sandbox restrictions. Native Chrome fallback provides local rendered-page evidence; it does not replace Chromium/Firefox/WebKit parity, real mobile-device testing, or authenticated end-to-end persistence.
- Axe and semantics checks are sampled page/state evidence, not complete WCAG 2.2 AA certification or a real screen-reader speech session. [UX-REPORT.md](UX-REPORT.md) records exact route/state coverage, screenshots and responsive limitations.
- Current dependency vulnerability advisories were not queried because allowed network use is limited to public package/browser downloads and no offline advisory database was supplied. Package inventory is not an assurance that dependencies have no vulnerabilities.
- No production system, paid service, deployment, remote CI or real customer workflow was validated. CI status remains pending at time of writing.
