# Independent QA gate review

PR: opened by orchestrator

CI status: pending at time of writing

**Local QA handoff accepted with the explicit limits below. This is not release approval or a clean-backend/production certification.** Reviewed the requested checkout on `qa/2026-10-02-sweep`; changes remain uncommitted for the orchestrator.

Counts: Critical=0 High=3 Medium=10 Low=2

The master findings contain 15 unique findings: Backend 6 (2 High, 4 Medium), Frontend 4 (1 High, 3 Medium), UX 5 (3 Medium, 2 Low). Supporting security findings are counted once. Environment and harness failures are not included as product findings.

## Final checklist

| Check | Result | Evidence / boundary |
| --- | --- | --- |
| Checkout, branch, allowed scope | PASS | Final validator confirms branch and 361 allowed QA/test files at 00:57:56 UTC. Tracked diff is the existing useSync test; new files are tests, QA scripts/docs/artifacts. No product, environment, migration, deployment or secret-baseline change. |
| Required reports and count consistency | PASS | All five required docs, all three group reports/logs, unique finding IDs, complete table fields, and parsed summary counts validated. [Validation](artifacts/gate/20261003T005756.101140Z-gate_handoff_validation.txt). |
| Relative artifact/document links | PASS | All local Markdown targets resolved at final path review; UX subsequently verified its 22 artifact links. [Path and scope review](artifacts/gate/20261003T005712.588167Z-gate_final_paths_scope.txt). |
| Whitespace and harness syntax | PASS | `git diff --check` clean; all seven Python/CJS harnesses parsed without execution errors. [Syntax](artifacts/gate/20261003T005524.476071Z-gate_harness_syntax.txt). |
| Defect-witness rigor | PASS, LOCAL SCOPE | Intended behavior is asserted with finding IDs and strict expected failures. Backend precondition failures are not swallowed by assertion-only xfails. Negative controls establish actual failures; no independent gate pytest ran, to preserve Backend scheduling ownership. |
| Coverage claims | PASS | Raw JSON confirms fixed denominators and documented numerators. [Independent totals](artifacts/gate/20261003T005022.012463Z-gate_coverage_numbers.txt). Broader failed/overlapping selections are not summed or represented as whole-repo coverage. |
| UX evidence | PASS, SAMPLED | Source, durable keyboard observations, repeated axe output and five finding screenshots reviewed. Iframes are labeled constrained CSS widths, browser extensions excluded, and automated scroll finding distinguished from untested cross-browser keyboard behavior. |
| Local process cleanup | INCOMPLETE | Tested server3104/proxy3105 and six browser tabs stopped. Original unused QA dev process PID23587 on127.0.0.1:3102 remains; sandbox denied signaling it. Orchestrator must terminate this exact process. See UX cleanup report. |
| Remote PR, CI, deployment and production | NOT PERFORMED | Orchestrator owns the one draft PR, secret scan, commit and push. No gate commit/push/PR/deploy/network/credential operation occurred. |

## Independently challenged finding claims

- **BE-011 High:** verified capability generation and anonymous submission authority, unchanged KDE persistence, and FDA extras emission. The witness composes real event-builder/export helpers with an invalid synthetic identifier. It proves formatter disclosure, not a live database/export/unauthorized-submission round-trip. Suggested fix covers both `portal_id` and fallback `reference_document`; successful-submit logging also carries the capability and needs a non-authorizing reference.
- **BE-010 High:** source checks Content-Length only; negative control records HTTP200 and ten consumed bytes against an eight-byte limit. Public JSON proof buffering occurs before its own size check. Actual ingress caps, memory exhaustion and production outage were not tested.
- **BE-001/002/003/004 Medium:** route-level witnesses cover naive timestamps, non-finite quantities, duplicate headers and invalid encodings. Auth/persistence are fake boundaries. Findings correctly avoid claiming committed database corruption. The valid BOM, finite/invalid numeric and standard schema controls make the witnesses meaningful.
- **FE-001 High / FE-002 Medium:** parser source and raw outputs establish variable-lot truncation and uncaught URI decoding respectively. Node20 build evidence includes completed TypeScript checks. FE-003 camera denial is supported by source and local response-header execution; no physical camera was used.
- **FE-004 Medium:** ownerless photo storage survives account clearing, then the sync hook dispatches pending photos through the current session. The unwrapped mocked-hook witness records a single upload call after a modeled account switch. Actual IndexedDB/login/backend round-trip was not run. Photos currently reach the CSV upload path and encounter BE-004, so successful cross-tenant persistence is not established. Structured scan payloads retain their original tenant and may be rejected by server mismatch checks.
- **UX-001/002/003 Medium:** mobile modal source lacks focus/Escape management, durable native keyboard observations reproduce Escape and reverse-Tab defects, and verifier focus is clipped in an sr-only input. Two 320px axe reports identify six product scroll regions under one rule finding. The latter remains an automated observation, not a verified cross-browser scroll test.
- **UX-004/005 Low:** screenshots and source establish unconditional outage copy on an intentional demo and missing zero-search-result feedback. Neither is represented as incorrect compliance classification.

Two admin manifest assertions differ only on a disabled graph route:179 runtime omitted operations versus180 committed; enabled250/classification counts match. The exact404 helper did not report an exposed path. This is unresolved inventory/test reproducibility drift, not an independently established authorization vulnerability.

## Harness corrections and honest safety limits

The first Node guard mishandled normalized socket argument arrays. A no-network spy reproduced it, the frontend owner corrected normalization, and an actual `net.connect` entrypoint with a stubbed original was blocked on recheck. Authoritative Node20 runs use the corrected guard.

Early npm installs scrubbed inherited environment but retained ordinary user-config discovery. No credential value/existence was inspected. The logger subsequently disabled user/global config discovery. Therefore this review describes observed controls, not an absolute proof that every package manager avoided every implicit configuration read.

The first broad backend collection attempted an unavailable localhost scratch-Postgres preflight through native libpq. No successful database read/write is established, but zero attempted database contact cannot be claimed. The runner now blocks SQLAlchemy connect/raw_connection and public native driver paths; only root `.coverage*` SQLite files are allowed for coverage artifacts. These are application-level guards, not a native-I/O sandbox.

The local browser proxy now restricts redirects to exactly http://127.0.0.1:3104. No off-host redirect was observed on exercised routes; its guard has a no-network probe. Browser findings/performance remain observations through instrumented, stricter-CSP pages with synthetic APIs and blocked external fonts.

## Remaining verification limits

Full green backend CI, real PostgreSQL RLS/transactions, Redis worker races, exact full dependency-lock installation, current vulnerability-advisory audit, authenticated end-to-end persistence, real mobile devices, three-browser parity, screen-reader speech, and production performance remain unverified for the reasons in SUMMARY/COVERAGE. Gate did not perform its own secret scan; the orchestrator retains the required final scan and publishing responsibility. Local product defects are deliberately unresolved and represented by expected failures.

Gate commands and visual-review actions are in [GATE-SESSION-LOG.md](GATE-SESSION-LOG.md). Gate owns only this report, its log and gate artifacts; no product fixes were applied.
