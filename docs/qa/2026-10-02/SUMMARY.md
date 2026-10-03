# RegEngine QA sweep — orchestrator handoff

PR: opened by orchestrator

CI status: pending at time of writing

Counts: Critical=0 High=3 Medium=11 Low=4

The three QA passes found **15 confirmed issues**. Product behavior is unchanged. Test additions, QA scripts, reports, logs and screenshots remain uncommitted on `qa/2026-10-02-sweep` for the orchestrator's review, secret scan, commit, push and single draft PR. No PR was opened by the QA agent; its URL and actual CI result are not yet available. The required PR line above identifies the publishing owner.

## Findings by group

| Group | Critical | High | Medium | Low | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Backend QA | 0 | 2 | 4 | 0 | 6 |
| Frontend QA | 0 | 1 | 3 | 0 | 4 |
| UX QA | 0 | 0 | 3 | 2 | 5 |
| Total | 0 | 3 | 10 | 2 | 15 |

The Backend security supporting report repeats BE-010/011; they are counted once. Environmental/test-harness failures are not counted as product defects. No Critical finding was established; this is not a claim that every surface is safe.

## Top five risks and next-fix order

1. **BE-011 — High:** FDA export evidence contains the bearer capability that authorizes supplier submissions. Replace it with a non-authorizing provenance reference across evidence, exports and logs.
2. **FE-001 — High:** Scanning a valid lot code can silently shorten its identity to `LOT-`. Correct variable-length GS1 parsing before customers rely on scanned traceability data.
3. **BE-010 — High:** Chunked or absent-length bodies bypass the global request-size limit. Enforce actual bytes before buffering to reduce resource-exhaustion risk.
4. **FE-004 — Medium:** Offline photos from one account replay through the next account's upload handler. Preserve owner/tenant identity and quarantine unowned queue entries; successful cross-tenant persistence was not demonstrated.
5. **BE-003 — Medium:** A duplicate CSV quantity column silently replaces 10 with 999. Reject ambiguous normalized headers before constructing accepted events.

Next address non-finite quantities (BE-002), client-error handling for timestamps/encodings/scan escapes (BE-001/004, FE-002), camera policy (FE-003), keyboard focus/navigation and scroll access (UX-001/002/003), then misleading static demo status and missing search-empty feedback (UX-004/005). Convert strict expected failures to ordinary regression tests as each product fix lands. Product fixes belong in subsequent scoped changes, not this QA-only handoff.

## Verification outcome

- **Backend focused tests:** ingestion **75 passed / 14 expected failures**; shared/auth/security **213 passed / 2 expected failures**, with one real-Redis case deselected. The new tests alone contain **13 passing controls / 16 strict expected failures**, plus 140 deterministic property examples. A separate exact-core-lock framework overlay reproduced all 29 new cases. Isolated admin auth/session tests passed **34 cases**.
- **Frontend:** locked dependency install, lint, production build and TypeScript checks passed, including the CI-family Node 20 build. Final full Vitest selection: **1,033 passed / 7 expected failures / 2 skipped** across 137 files, with 1,000 generated GTIN checks inside one passing test.
- **Coverage:** focused backend ingestion statements **65.07% → 66.18%**, selected shared statements **59.92% unchanged**; frontend lines **69.95% → 69.97%** on the same 196 instrumented files. These are scoped measurements, not whole-repository coverage.
- **UX:** actual built UI rendered in native Chrome through a restricted local test proxy, with axe, native keyboard checks, responsive constrained-iframe observations, synthetic form-error states and saved screenshots. The proxy blocks external resources and stubs APIs; browser extensions are excluded from product findings.
- **Broader checks remain incomplete:** the broad shared selection reached **886 passing tests** with three intentional DNS-guard failures and 16 skips. The broad ingestion attempt retained 463 passes plus six guard-related failures, 14 collection/setup errors and 50 skips before its failure cap. Focused mypy reports an existing Optional-header typing error. Two route-manifest tests show a disabled-operation inventory discrepancy; enabled classifications are unchanged. A completely green backend suite was not established.

Counts across overlapping test selections must not be summed. Expected failures reproduce bugs while allowing the added QA suite to remain green; they are not successful product behaviors. Exact commands, failed attempts, exclusions and raw evidence remain in the pass logs.

## What could not be tested

| Area | Reason / consequence |
| --- | --- |
| Chromium, Firefox and WebKit Playwright parity | All three native browser launches failed under macOS sandbox restrictions before navigation. Native Chrome fallback is useful render evidence, not three-browser parity. |
| Real mobile devices and top-level mobile viewport emulation | The available browser viewport override did not take effect; 390/320 px same-origin iframes establish CSS-width behavior only. |
| Full screen-reader speech and WCAG certification | Manual semantics/focus plus sampled axe scans cannot certify the entire app or replace an assistive-technology session. |
| Authenticated end-to-end ingestion and exports | Real database/provider use is excluded; browser APIs are synthetic stubs. Local witnesses stop at explicit fake boundaries. |
| PostgreSQL RLS/transactions and real Redis races | Database/remote effects are outside scope; guards exclude those fixtures. An early unavailable localhost fixture preflight and subsequent stronger native-driver guards are disclosed in the backend log. |
| Current dependency vulnerability audit | Network is allowed only for public package/browser retrieval, and no offline advisory database was supplied. Dependency inventory is not a clean vulnerability verdict. |
| Production performance, provider configuration and customer behavior | Production systems, credentials, billing, deployment and external authenticated APIs were prohibited. Any local timing is diagnostic, not a production SLO or Lighthouse score. |
| Remote PR and CI | The orchestrator owns publishing. No commit, push, merge, deployment or PR command was executed by the agent. |

## Handoff index

Local handoff validation passed: mandatory docs/counts/branch/scope, QA script syntax, Markdown evidence links and `git diff --check`. Gitleaks 8.30.1 found no leaks in the changed test paths or final QA artifacts ([artifact scan](artifacts/meta/20261003T005754.472010Z-final-artifact-secret-scan.txt)); no secret-scan baseline or ignore list was changed. The orchestrator still performs its own scan before publishing.

**Orchestrator cleanup required:** the unused original QA Next dev process **PID 23587 on 127.0.0.1:3102** remains running. Sandbox denied signaling it and its failed watcher ignored a cooperative shutdown change in the disposable mirror. Its logger was interrupted, so no timeout remains. Stop this specific QA process. The tested built server 3104, proxy 3105 and all six QA browser tabs were closed. No browser test used port 3102.

- [Plan and risk ranking](PLAN.md)
- [Master session log](SESSION-LOG.md), with separate Backend / Frontend / UX logs and supporting review logs
- [Complete findings and reproductions](FINDINGS.md)
- [Coverage denominators and gaps](COVERAGE.md)
- [Backend pass](BACKEND-REPORT.md), [security supporting analysis](SECURITY-REPORT.md)
- [Frontend pass](FRONTEND-REPORT.md)
- [UX pass and screenshots](UX-REPORT.md)
- [Independent gate review](GATE-REPORT.md)

Keep all changes uncommitted for the orchestrator. No product, dependency lock, deployment, migration, environment file, secret-scan baseline or protected PR branch was changed. Build-generated `next-env.d.ts` changes were restored to baseline. Previously known leaked keys were not investigated or rotated.

## Browser follow-up pass

PR: opened by orchestrator

CI status: pending at time of writing

The current count line now includes **18 findings: the original 15 plus UX-006 Low, UX-007 Medium and UX-008 Low**. The earlier report sections above describe the first sweep; its browser-launch and top-level viewport blockers are superseded by this follow-up. Product code is unchanged.

**FE-001 is confirmed in Chromium, Firefox and WebKit. FE-004 is confirmed in Chromium and Firefox using real IndexedDB and the real replay hook with synthetic sessions.** FE-004 proves an attempted client upload of A's photo under B's cookie; a local 422 stub prevents persistence. WebKit's native Blob storage fails before replay and remains unverified for that scenario. New test witnesses and their setup boundaries are in the [regression evidence index](artifacts/browser/fe-regressions-summary.md).

The new regression selection exits **0: 5 strict expected failures, 1 environment skip, 0 unexpected failures**. Controls and prerequisites execute before each `test.fail()` marker; the WebKit skip requires an independent native storage control. These expected failures document unfixed defects.

| Existing E2E project | Passed | Failed | Skipped | Failure classification |
| --- | ---: | ---: | ---: | --- |
| Chromium | 21 | 8 | 61 | 6 environment, 2 test harness |
| Firefox | 20 | 9 | 61 | 6 environment, 3 test harness |
| WebKit | 18 | 11 | 61 | 7 environment, 3 test harness, 1 product (UX-008) |
| Total | 59 | 28 | 183 | 19 environment, 8 test harness, 1 product |

These are all 270 discovered cases from the unchanged existing suite, run through an isolated local browser configuration. **The existing suite is not green.** The stock local configuration stops at prohibited database bootstrap; authenticated/backend scenarios are not end-to-end verified. The 183 skips comprise 180 missing auth/backend/key prerequisites and 3 opposite sandbox-branch conditions. [Attempts, exact commands and triage](artifacts/browser/existing-e2e-results.md).

**42 initial route/viewport combinations** cover seven routes across all three actual engines at desktop 1440×900 and mobile 390×844, with screenshots, axe, console and network evidence. All return 200 without uncaught page errors, unexpected local network failures or whole-page horizontal overflow. Eight additional synthetic error/empty states and keyboard navigation were checked. Axe reconfirms narrow verifier scrolling gaps; keyboard checks reconfirm the mobile menu and upload-focus defects. New findings are scanner heading order (UX-006), invisible global skip-link focus (UX-007), and a clipped WebKit tour tooltip (UX-008). [Screenshots and per-route evidence](artifacts/browser/browser-ux-summary.md).

External fonts were deliberately blocked; synthetic 401/503 responses and CSP console errors are excluded from product failures. Lighthouse remains **not covered**, as do real mobile devices, screen-reader speech and authenticated flows against a real backend. No backend/static/security pass, production call, commit, push or PR operation was repeated. The orchestrator owns the final secret scan and publishing.

Final review corrected a redirect-isolation gap in the QA wrapper. The existing suite was rerun through a proxy that validates each redirect hop; **all 270 outcomes and the counts above are unchanged**. The [authoritative result](artifacts/browser/existing-e2e-proxy-local-browser-summary.json) supersedes earlier isolation claims. No product fix or original-test modification was needed.

Independent review and [local handoff validation](artifacts/browser/20261003T022030.966307Z-final-browser-handoff-validation-corrected.txt) passed. All five required reports are updated; earlier content/artifacts are preserved. Follow-up servers 3114/3115 are stopped, and the earlier 3102 listener is also absent; browser server 3950 is left with the orchestrator. [Cleanup readback](artifacts/browser/20261003T021959.765139Z-final-browser-listener-readback.txt). All follow-up changes remain uncommitted on `qa/2026-10-02-sweep`.

Fix pass: see FIXES.md
