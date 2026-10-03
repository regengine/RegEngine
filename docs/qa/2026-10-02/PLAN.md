# RegEngine QA sweep — 2026-10-02

PR: opened by orchestrator

CI status: pending at time of writing

## Scope and identity

- Checkout: `/Users/sellers/Projects/qa-sweep-2026-10-02/RegEngine`.
- Branch: `qa/2026-10-02-sweep`; baseline HEAD `0927b85a` (full SHA in the scope-map artifact).
- Origin: `https://github.com/regengine/RegEngine.git`. Identity verified locally; no remote queries.
- Initial interrupted inventory: 2026-10-02 23:46 UTC. Resumed: 2026-10-03 00:35 UTC. The directory retains the requested local date, 2026-10-02 (America/Los_Angeles).
- Preserve all earlier artifacts. Timebox resumed work to approximately 60–90 minutes, prioritizing production-spine risk over exhaustive suite count.
- Three separate groups apply: Backend QA, Frontend QA, UX QA. Each has its own pass report, UTC command log, charters, and artifact directory. Passes can execute concurrently with disjoint ownership. Backend security review is a supporting lane, not a fourth substitute group.

## Repository map

| Surface | Location | QA significance |
| --- | --- | --- |
| Consolidated FastAPI application | `server/main.py`, route policy/security manifests | Actual mounted surface, middleware ordering, auth policy |
| Ingestion and exports | `services/ingestion/app/` | CSV/webhook/EPCIS normalization, validation, receipts, export integrity |
| Shared evidence and tenancy | `services/shared/` | Canonical persistence, auth, tenant context, hash chains, retry/idempotency |
| Administration | `services/admin/` | Users, sessions, API keys, privileges, audit records |
| Compliance | `services/compliance/`, shared rules | Deterministic validation and explainable results |
| Other service packages | `services/graph/`, `nlp/`, `scheduler/` | Secondary scope; do not confuse package boundaries with separate deployed services |
| UI | `frontend/src/` | Next.js App Router, authenticated dashboard, ingestion workbench, public onboarding |
| Existing tests | `tests/`, service test directories, `frontend/src/**/*.{test,spec}.*`, `frontend/tests/e2e/` | Unit/contract/security foundations plus expensive integration journeys |
| Dependencies | `requirements.in`, `requirements.lock`, `frontend/package{,-lock}.json` | Reproducible install and advisory evidence |
| Architecture guidance | `README.md`, `REPO_PURPOSE.md`, `ARCHITECTURE.md`, `CANONICAL_OWNERSHIP.md` | Current purpose; verify older implementation claims against source |

The shared default checkout and team commit rules are superseded by this task's explicit worktree and orchestrator handoff. `docs/specs/FSMA_204_MVP_SPEC.md` labels itself legacy; its older Neo4j/Kafka and route claims are not assumed current.

## Risk ranking

Impact and likelihood use a 1–5 scale. Scores are planning judgments, not observed defect counts.

| Rank | Area | Impact | Likelihood | Score | Reason |
| --- | --- | ---: | ---: | ---: | --- |
| 1 | Tenant isolation and authorization | 5 | 4 | 20 | Shared infrastructure and many router guards; one wrong scope can expose another customer's records |
| 2 | Ingestion validation and evidence integrity | 5 | 4 | 20 | Malformed boundary values or false successful writes compromise the product's primary guarantee |
| 3 | Build/dependency reproducibility and client contracts | 4 | 4 | 16 | An unreproducible build blocks every release and limits runtime verification |
| 4 | Retry, duplicate submission and export correctness | 5 | 3 | 15 | Replays/concurrency can duplicate evidence; exports must accurately represent persisted events |
| 5 | Main user journeys and error recovery | 4 | 3 | 12 | Upload/login/validation failures can prevent a customer completing the workflow |
| 6 | Keyboard, screen-reader semantics, responsive layouts | 3 | 4 | 12 | Dense forms and dashboard navigation can exclude users or hide critical actions |
| 7 | Resource use, latency and optional modules | 3 | 3 | 9 | Useful supporting evidence after core correctness; local performance cannot establish production SLOs |

## Methods and pass charters

Use the test pyramid: many isolated unit/schema/security checks, a smaller local API contract layer, and a few realistic browser journeys. Preserve existing failures. New defect witnesses are strict expected failures/skips carrying a finding ID; never loosen a product assertion to make a suite green. Distinguish verified bugs, source-supported risks, and unavailable checks.

### Pass 1 — Backend QA

- **BE-C1, 15 minutes:** challenge tenant/auth boundary decisions using existing negative-path tests and an explicit permissions matrix. Trace guards through actual router mounting; review OWASP API Top 10 categories with evidence and residual limits.
- **BE-C2, 20 minutes:** test CSV/schema equivalence classes and boundaries (empty, malformed, overflow, non-finite numeric values), canonical evidence and retry/idempotency behavior. Use property-based cases where a stable pure-function boundary exists; stub I/O and prohibit remote connections.
- **BE-C3, 10 minutes:** run static analysis/type checks on meaningful core surfaces and inspect dependency audit feasibility. Record unresolved imports/tooling instead of presenting incomplete checks as clean.
- Run existing selected suites with coverage before adding tests; repeat the identical measured source set plus new tests after. Publish denominators, line/branch differences and exclusions. Full database-backed RLS and concurrency cannot be inferred from mocks.

### Pass 2 — Frontend QA

- **FE-C1, 15 minutes:** reproduce the checked-in dependency install and run lint, build/type checks, unit/component suites with coverage.
- **FE-C2, 15 minutes:** inspect and test auth/session, client API/error handling and traceability input boundaries. Add minimal test-only witnesses as useful.
- **FE-C3, 10 minutes, shared browser evidence:** local main-flow Playwright smoke on Chromium, Firefox and WebKit; capture console/network errors and performance observations. UX owns browser orchestration to avoid duplicate server/package installs.
- Exact locked dependencies are essential for faithful results. If public packages are unavailable, do not silently substitute versions or report unrelated mock screens as the product. Record install blockers and continue executable source-level checks.

### Pass 3 — UX QA

- **UX-C1, 15 minutes:** discover, sign in, navigate to ingestion and understand validation results; inspect loading/empty/error feedback and recovery. Use synthetic fixtures only.
- **UX-C2, 15 minutes:** axe WCAG 2.2 A/AA plus manual keyboard focus, labels, headings, landmarks and screen-reader semantics. Automated checks do not certify WCAG compliance; actual assistive-technology speech output is a separate limitation.
- **UX-C3, 10 minutes:** mobile and desktop responsive layouts, Nielsen's ten heuristics, action clarity and representative screenshots. Capture meaningful local render/performance evidence if the app can run; otherwise clearly label static review and unavailable screenshots.

## Execution and evidence controls

- Use `scripts/run_logged.py GROUP LABEL -- COMMAND` for all shell work after bootstrap. It records UTC, command, working directory, exit, elapsed duration, timeout and redacted output. Keep per-group logs and link them from `SESSION-LOG.md`.
- Scrub inherited environment variables; never open `.env` or credential files. Disable dotenv loading and telemetry in test processes. Prevent browser/server outbound calls; do not allow local defaults to contact real external services.
- Network allowed only for installing dependencies and fetching public packages/browsers. Advisory API calls, CodeRabbit and Jev calls are excluded by this restriction. Report dependency audit limits explicitly.
- No product changes, CI secret-scan changes, migrations, deploy configuration, environment-file edits, production/database/billing access, secret rotation, commits, pushes, PR operations, or changes to the excluded existing PR/branch.
- Store compact useful screenshots/reports under `artifacts/`; refer to source locations and test names from findings. Do not commit caches, dependencies, virtualenvs, traces containing sensitive state, or huge generated HTML reports.

## Completion and out-of-scope evidence

Produce `PLAN.md`, `SESSION-LOG.md`, `FINDINGS.md`, `COVERAGE.md`, `SUMMARY.md`, group reports/logs and focused tests. Independently review finding severity, repros, expected failures, scope and artifact hygiene. Leave everything uncommitted for orchestrator review, secret scan, commit, push and creation of the single draft PR. PR URL and CI result are unavailable until that handoff occurs.

Out of scope: deployed behavior, live RLS/database migrations, real email/payment/provider integrations, real credentials, production load/penetration testing, full WCAG certification, external review APIs, and already-known leaked-key investigation. Missing coverage of these surfaces is a limitation, not a passing result.

## Browser follow-up pass

Bootstrap preceded the first recorded server command at 2026-10-03 02:02:45 UTC (2026-10-02 in America/Los_Angeles); the exact first-tool timestamp was not retained. Checkout identity reverified: sole worktree `/Users/sellers/Projects/qa-sweep-2026-10-02/RegEngine`, branch `qa/2026-10-02-sweep`, RegEngine origin, HEAD `c98e1a30`, initially clean. Earlier QA artifacts are already present at this HEAD; this follow-up leaves its own changes uncommitted.

Only previously blocked browser coverage is in scope. Preserve the earlier reports and artifacts; append follow-up results, except the explicitly requested current coverage status and summary count-line updates. Three independent work lanes own existing E2E execution, FE-001/FE-004 browser regressions, and screenshots/accessibility/keyboard/console/network evidence. The coordinator owns the isolated server, consolidated documents and evidence review.

1. Run the existing E2E inventory for Chromium, Firefox and WebKit through Playwright 1.63.0 and the orchestrator's loopback browser server; distinguish blocked database-dependent local setup from individual browser assertions.
2. Add browser witnesses for FE-001 and FE-004 under `frontend/tests/e2e/qa-2026-10-02/`. Mark only the intended product assertions as expected failures after prerequisites/controls succeed. No product fixes.
3. Capture real top-level 1440×900 and 390×844 viewports, run `@axe-core/playwright` on main public routes, and exercise primary keyboard navigation. Record console errors, failed requests and deliberately blocked/stubbed traffic per route.
4. Append statuses, exact commands, artifacts, limitations and reconciled finding counts to the five mandatory reports; review test validity and artifact scope before handoff.

Reuse the existing production build in a disposable mirror, the existing `node-isolation.cjs` guard and `run_logged.py` command ledger. All credentials/auth/backend responses used by witnesses are synthetic; no database or deployed service is permitted. No direct browser launch, persistent context, browser installation, Lighthouse, real device, screen-reader, backend/static/security repeat, commit, push or PR operation. Public npm package retrieval is allowed only for missing QA tooling. Jev and remote reviewers remain excluded by the orchestrator's network restriction.

Completed with the unchanged existing suite exercised in all three engines, both requested browser witnesses, 42 initial route/viewport scans and additional state/keyboard evidence. Independent review required a per-hop redirect proxy repair and an unchanged-outcome suite rerun; both are recorded. The final local handoff passes document/count/link/scope validation. Remaining limitations and exact nonpassing tests are retained in `COVERAGE.md` and the browser evidence indexes.
