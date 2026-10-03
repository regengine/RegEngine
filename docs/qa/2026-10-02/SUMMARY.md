# RegEngine QA sweep — orchestrator handoff

PR: opened by orchestrator

CI status: pending at time of writing

Counts: Critical=0 High=3 Medium=10 Low=2

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
