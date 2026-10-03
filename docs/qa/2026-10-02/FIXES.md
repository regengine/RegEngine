# QA fix pass — 2026-10-02

Local fix branch: `qa/2026-10-02-fixes`. Sweep base: `b5dd065e`. Product freeze: `b6222b29`. No remote writes, deployments, migrations, environment/credential changes, key rotation, or secret-scan baseline changes. The locally recorded PR #3149 paths were protected throughout.

Critical findings: none. High findings were handled in the SUMMARY priority order: BE-011, FE-001, BE-010. Optional work began only after those dispositions were complete. Each fixed finding has a separate local commit and normal passing regression tests.

| Finding ID | Severity | Title | Status | Commit SHA | Proving test (file::name) | Notes or reason deferred |
| --- | --- | --- | --- | --- | --- | --- |
| BE-011 | High | Supplier submission capability is disclosed in FDA exports | deferred | — | `tests/qa_sweep_20261002/test_portal_export_disclosure.py::test_redacted_fda_export_does_not_disclose_portal_capability` (unchanged xfail) | The complete fix changes supplier bearer-credential handling and persisted provenance. Credential work is explicitly excluded; safely replacing historical evidence references also needs compatibility decisions. No partial token filtering or rotation attempted. |
| FE-001 | High | Valid barcode lot identifiers are silently truncated | fixed | `a7f001fc` | `frontend/src/__tests__/lib/qa-sweep-gs1.test.ts::FE-001 preserves lot %s through the group separator`; `frontend/tests/e2e/qa-2026-10-02/fe-001-barcode.spec.ts::FE-001 preserves complete GS1 lot identifiers in the real scanner form` | Removed inferred AI boundaries inside variable fields and preserved explicit parenthesized delimiters. Before: 9 ordinary failures. Related tests: 39 passed / 3 unrelated xfail; actual scanner: 3 engines passed. |
| BE-010 | High | Streaming bodies bypass the global request-size limit | fixed | `dbdacb67` | `tests/qa_sweep_20261002/test_request_safety.py::test_streamed_body_is_limited_without_content_length` | Actual ASGI bytes are checked before retaining chunks or dispatching handlers. Before: 1 failed / 2 passed. Final focused tests: 62 passed, including deceptive lengths, disconnects, timeouts, multipart and streaming responses. |
| BE-003 | Medium | Duplicate CSV headers silently replace a quantity | fixed | `21a6e6cc` | `services/ingestion/tests/test_qa_sweep_20261002_contract.py::test_csv_rejects_conflicting_duplicate_headers` | Reject normalized duplicate headers before row dictionaries are constructed. Before: 2 failures. Related tests: 258 passed / 12 unrelated xfail. Comment-row fixtures now use distinct headers while preserving their existing assertions. |
| BE-002 | Medium | CSV accepts non-finite quantities | fixed | `f769b82e` | `services/ingestion/tests/test_qa_sweep_20261002_contract.py::test_csv_rejects_nonfinite_output_quantity`; `services/ingestion/tests/test_qa_sweep_20261002_contract.py::test_csv_rejects_nonfinite_input_quantity`; `services/ingestion/tests/test_qa_sweep_20261002_contract.py::test_webhook_nonfinite_quantity_returns_validation_error_before_ingest` | Require finite output and nested input quantities; retain output >0 and input >=0. Narrow error-detail conversion preserves structured HTTP 422 for numeric overflow. Before: 6 CSV failures. Related tests: 216 passed / 6 unrelated xfail; locked-framework gate: 65 passed / 6 xfail. |
| BE-001 | Medium | Timezone-naive webhook timestamps cause HTTP 500 | deferred | — | `services/ingestion/tests/test_qa_sweep_20261002_contract.py::test_webhook_naive_timestamp_is_a_validation_response` (unchanged xfail) | QA requires timezone rejection, while existing replay tests and CSV handling define naive timestamps as UTC. Choosing rejection versus normalization requires clear contract intent. No source change for this finding. |
| BE-004 | Medium | Non-UTF8 uploads cause HTTP 500 | fixed | `b6222b29` | `services/ingestion/tests/test_qa_sweep_20261002_contract.py::test_csv_non_utf8_upload_returns_client_error` | Catch only UTF-8 decode errors and return actionable HTTP 400. Before: 3 failures. Related tests: 79 passed / 3 unrelated xfail. UTF-8 BOM and non-ASCII content remain accepted; no MIME policy change. |
| FE-002 | Medium | Malformed Digital Link escapes crash scan handling | deferred | — | `frontend/src/__tests__/lib/qa-sweep-gs1.test.ts::FE-002 handles malformed Digital Link escape %s without throwing` (unchanged xfail) | Parser-only recovery would let malformed URLs reach FieldCaptureClient synthetic SCAN-identifier save/upload behavior. Complete safe rejection needs a broader caller policy decision. No source change for this finding. |

Counts for findings listed above:

| Severity | Fixed | Partial | Deferred |
| --- | ---: | ---: | ---: |
| Critical | 0 | 0 | 0 |
| High | 2 | 0 | 1 |
| Medium (selected or explicitly assessed) | 3 | 0 | 2 |
| Low | 0 | 0 | 0 |
| Total | 5 | 0 | 3 |

FixCounts: fixed=2 partial=0 deferred=1

The machine-readable FixCounts line includes Critical and High only. Other optional findings were not changed and are outside these totals. FE-004 owner/session queue behavior, FE-003 camera policy, and UX findings remain in the original QA backlog. FINDINGS.md was not rewritten.

**Full-suite and comparable results** (pass / fail / xfail / skip; errors listed separately):

| Selection | Before | After | Interpretation |
| --- | --- | --- | --- |
| Full frontend Vitest, 137 files | 1033 / 0 / 7 / 2 | 1042 / 0 / 4 / 2 | Three FE-001 expected failures converted; six new passing cases. Coverage thresholds passed. |
| Existing browser E2E, same 270 identities | 59 / 28 / 0 / 183 | 58 / 29 / 0 / 183 | Same 28 baseline failures plus one Chromium tour geometry fluctuation; unchanged tour source and no GS1 parser dependency. Separate same-build retry: 3 passed / 0 failed. Full-run counts are not replaced with retry results. |
| Added browser QA regressions, 6 cases | 0 / 0 / 5 / 1 | 3 / 0 / 2 / 1 | FE-001 now passes on Chromium, Firefox and WebKit. FE-004 still xfails on two engines; WebKit native Blob-storage prerequisite remains skipped. |
| Root backend full suite (guarded) | 10644 / 246 / 3 / 541, plus 480 errors | 11406 / 253 / 5 / 539, plus 342 errors | Not a clean snapshot comparison: inventory began before edits, overlapped later work, and lacked the restored temporary SDK overlay. |
| Added backend QA selection, exact core-lock overlay | 13 / 0 / 16 / 0 | 56 / 0 / 4 / 0 | 12 expected failures converted and 31 new passing cases; only BE-001 (three) and BE-011 (one) remain. |
| Sweep-comparable focused ingestion | 75 / 0 / 14 / 0 | 107 / 0 / 3 / 0 | Same file selection; 11 expected failures converted and 21 new passing cases. Only BE-001 expected failures remain. |
| Sweep-comparable shared/auth/security | 213 / 0 / 2 / 0, 1 deselected | 241 / 0 / 1 / 0, 1 deselected | One expected failure converted and 27 new passing cases. BE-011 remains. Original real-Redis deselection retained only here; full root run has no exclusions. |

The original sweep did not establish a green full backend suite. Its broad ingestion attempt had 463 passed / 6 failed / 14 errors / 50 skipped / 15 deselected before its failure cap; broad shared in-process selection had 886 passed / 3 DNS-guard failures / 16 skipped. These different selections overlap and must not be summed or treated as equivalent full-suite baselines. The fix-pass initial full inventory classified 536 guard denials, 128 missing-module entries and 62 other failures among its 726 failure/error entries. Restoring the exact sweep SDK overlay reached 12,524 collected tests, with two additional import probes blocked by the guard. Final full run completed at frozen b6222b29 in 525.29 seconds with no selection exclusions or failure cap. It remains red. The restored SDK overlay lets previously uncollected tests execute, so the two full-run totals do not measure only fix effects. Ten apparent new failures were random UUID parameter-ID changes with the same database guard error. After UUID normalization, five new bad identities belong to modules blocked at collection in the initial inventory: four subprocess-guard cases and a Jev logging assertion that passes in isolation. Eleven prior errors now execute as failures: three DNS guards, two known route-manifest assertions and six job/auth HTTP 500 assertions. All six HTTP 500 assertions fail identically with the final limiter and the original b5dd065e limiter, both ending at denied Redis DNS. No new failing identity in changed test surfaces and no attributable fix regression were found; no revert was required.

**Build, typecheck and lint:**

- Frontend production build passed; served build ID `nbeA56-sCPEIKdGXlL47I` matched the final FE-001 source. The later backend fixes do not affect that build. Generated next-env.d.ts was restored.
- Standalone `tsc --noEmit --incremental false` passed. There is no npm typecheck script.
- Frontend lint passed with 0 errors / 41 pre-existing warnings; design lint passed all 676 files, matching the sweep.
- Python Ruff bug gate passed, and Ruff on all 11 changed Python files passed. Full Ruff reports 57 import-order errors across 49 files; every failing file is byte-identical to the sweep base, so those errors are pre-existing.
- Focused mypy retains exactly the sweep Optional-header len() error (csv_templates.py:784 before, :801 after). Full mypy is blocked by duplicate regengine modules in regengine/__init__.py and cli/regengine.py; those files and pyproject.toml are unchanged. No new static error was attributed to this pass.
- The root Python application is explicitly not packaged/built by pyproject.toml; no backend app build target exists. Docker/deploy work was excluded.

**Evidence and remaining risks:**

Every shell command, test run, decision and dead end is recorded in [FIX-SESSION-LOG.md](FIX-SESSION-LOG.md), with redacted outputs under artifacts/fix. [Backend result index](artifacts/fix/backend-final-summary.json) records the full/focused runs and paired original-code controls; [exact failure identities](artifacts/fix/backend-failure-identities.json) retain the comparison. [Frontend result index](artifacts/fix/frontend-final-summary.json) preserves full counts, exact versions, all 270 browser identities, the isolated tour retries and proving logs. Independent local gate reviewed each fix and exact locked-framework backend witnesses. Per-finding test selections overlap and are not additive. Remote CodeRabbit/Jev calls were not allowed by the package-download-only network restriction.

Backend tests use synthetic authentication and fake persistence with network, database, subprocess and environment-file guards; no live tenant/RLS, real export round-trip, production, provider, remote CI or customer proof is claimed. Accepted request bodies are now buffered up to the existing cap before handler dispatch. Historical supplier capability disclosure remains unresolved. Other expected failures and browser environment/harness/product failures remain visible. No unrelated failing test was weakened or fixed, and no attributable regression has required a revert.

Unit/build Node was 20.19.4 versus the sweep 20.20.2; browser driver Node was 26.7.0 with Playwright 1.63.0. Actual engines matched the sweep (Chromium 153.0.8010.12, Firefox 155.0, WebKit 26.6). Browser traffic used the existing guarded loopback proxy; authenticated persistence, physical cameras, production headers and external resources were not validated. Owned local servers were stopped; the supplied browser server was left running.

Product commits passed default-rule Gitleaks and offline detect-secrets scans. Two test-client header diagnostic lines in each full backend log were fully redacted before rescans passed; no scanner baseline or ignore list changed. Final raw and archive-aware artifact scans passed after full-suite output and regression controls. The final staged Gitleaks scan passed; scope, file-size and whitespace checks passed.

Large new raw logs are stored as lossless .txt.gz archives, with the original .txt paths retaining metadata, final excerpts and SHA-256 pointers. [Compression index](artifacts/fix/compressed-log-index.json) records byte counts and verified hashes; no original sweep artifact was altered. Two new WebKit screenshots also use verified lossless .png.gz archives to stay below the file-size limit; their original paths and hashes are mapped in the [screenshot archive index](artifacts/fix/compressed-screenshot-index.json).

Captured diff/test output sometimes contains trailing whitespace that fails git diff --check. Display-only whitespace was normalized in new text logs; [original command log archive index](artifacts/fix/original-command-log-whitespace-index.json) maps every affected log to its verified complete original bytes.

The orchestrator owns remote review, push and PR creation. All changes in this pass are local commits only.
