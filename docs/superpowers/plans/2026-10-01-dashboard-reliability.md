# Dashboard Reliability Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development to implement each scoped task with tests and independent review. The user has authorized execution; preserve that authorization through the plan.

**Goal:** Deliver a tested first repair milestone for trustworthy receiving/import, evidence status, request/export completion and shared operator interactions.

**Architecture:** Correct existing request/response adapters and state machines. Preserve authoritative tenant/permission checks and production capabilities. Separate independent work lanes; serialize shared-file edits through the controller.

**Tech Stack:** Python 3.11 / FastAPI / PostgreSQL; Node 20 / Next.js 16.3.5 / React / TanStack Query / Vitest / pytest.

**Spec:** `docs/superpowers/specs/2026-10-01-dashboard-reliability-design.md`.

## Execution outcome — 2026-10-01

The six implementation lanes, independent reviews, final repair and aggregate validation are complete. Checked items below record delivery of their implementation/test scope; not every initial regression assertion has a separately recorded old-source failure. See the [delivery record](2026-10-01-dashboard-reliability-delivery.md) for that evidence limitation, the completion API migration, exact results and remaining program. The reviewed branch is prepared for a draft PR; merge and deployment remain separate release steps.

## Global Constraints

- No production deployment, merge, external notification, or customer-data mutation is part of implementation verification.
- Preserve the exact production router allowlist; repair optional feature presentation without enabling its backend.
- No new dependencies, speculative service rewrite, or weakened authentication/tenant checks.
- Worktree: `/workspace/worktrees/regengine-dashboard`; original `/workspace/RegEngine` stays unchanged.
- Use `PATH=/workspace/setup/toolchains/node20/node_modules/.bin:$PATH` for frontend commands and `venv/bin/python` for backend commands.
- Use synthetic fixtures. Never print secrets or copy live data into tests.
- Write test evidence and file ownership to `/workspace/reports/dashboard-execution/`; controller owns commits and integration.
- Workers do not spawn agents, commit, reset, or touch another lane's files. Request a shared-file edit from the controller.

## Review Focus

- HTTP 200 with mixed/rejected items: retain actionable failures and never claim full completion (Task 1).
- A dependency rejects after the user starts a consequential operation: preserve status/draft and never advance completion (Tasks 2–4).
- Empty envelope, real zero, missing response and unavailable dependency: display distinct truthful results (Tasks 2, 3, 5).
- Delayed old request or conflicting identity arrives after user context changes: ignore stale results and preserve the current identity (Tasks 1, 3, 4).
- Native keyboard, modal focus and logout rejection: keep controls operable and failed sign-out visible (Tasks 4, 6).

## Task 1: Receiving contract and observed-identity safety (D01–D02)

**Owns:** `frontend/src/app/dashboard/receiving/page.tsx`, `frontend/src/lib/scan-match.ts`, focused new receiving helpers, ingestion proxy idempotency header allowlist, associated receiving/scan-match/proxy tests.
**Reads:** webhook router/model/required receiving KDE validators.
**Interfaces:** Browser submission supplies the backend's existing receiving DTO and `Idempotency-Key`; proxy forwards it unchanged; result interpretation consumes actual accepted/rejected/event persistence fields. Matching requires every supplied identifier to agree and preserves observed versus expected data.

- [x] Write and run failing tests for GTIN/lot contradictions and ambiguous identifiers; missing header forwarding; real required KDEs; mixed HTTP 200 outcomes; unchanged retry versus changed payload identity.
- [x] Implement the minimal complete receiving request path; provide required user inputs with labels and preserve retry state.
- [x] Run receiving, scan matching and ingestion-proxy tests plus validator-backed fixture verification.
- [x] Self-review, write exact commands/results and remaining limitations to `receiving.md`; controller obtains independent review before committing.

## Task 2: Recall and request lifecycle (D04–D05)

**Owns:** `frontend/src/hooks/use-sla.ts`, recall-response and recall-report pages, `frontend/src/components/fsma/phase-gates.tsx`, `recall-timer.tsx`, request list/detail, request-specific hook module, backend `sla_tracking.py`, `request_workflow_router.py` and relevant request query/assembly code and tests.
**Shared constraint:** Do not edit `use-control-plane.ts` concurrently with Task 3; create/extract a focused request hook module or submit a coordinated patch for the request section only.
**Interfaces:** SLA lists decode actual envelopes; export requires a valid <=90-day scope; completion requires confirmed evidence rather than window opening. Request reads include explicit status/history and ID lookup; visible sign-offs map to existing backend transition types.

- [x] Add failing real-wire-shape tests for empty/populated envelopes and mandatory export dates.
- [x] Add workflow tests: failed export cannot complete; review/final approval reaches ready; completed/amended case remains readable; invalid transition preserves current state/error; elapsed time never completes a milestone.
- [x] Implement guarded list/export/completion flows, valid review actions, completed history, and accurate milestone/timer state.
- [x] Run focused recall/request frontend tests and SLA/request backend tests; inspect authority and tenant boundaries.
- [x] Write `recall.md` with evidence and limitations; controller independently reviews before commit.

## Task 3: Import receipts and deliberate exception sign-off (D03, D06, D13 subset)

**Owns:** ingest page/types and focused adapters, analysis result client, Exceptions, Records detail handling, `use-control-plane.ts` excluding request section, exception backend router/shared transition logic and tests.
**Shared constraint:** `api-client.ts` edits require controller coordination; keep endpoint adapters focused.
**Interfaces:** Distinct synchronous `document_id` receipt versus async `job_id`; exception resolve/waive sends case-specific reason, uses pending/error state, and surfaces stale transition conflicts. CSV run identity is preserved; canonical IDs are not inferred from incompatible legacy event IDs.

- [x] Add failing tests using actual URL response and explicit failed async state; late response cannot overwrite current input.
- [x] Add failing exception tests requiring deliberate case-specific rationale, preserving input on 403/409/500, and preventing duplicate actions; unknown blocker counts cannot render clear.
- [x] Implement these paths and recoverable record/analysis detail errors; preserve durable run identity where the existing backend supports it.
- [x] Run focused ingestion/exception/record frontend and backend transition tests.
- [x] Write `ingestion.md`; request independent review before commit.

## Task 4: Read-only policy verification and reliable session teardown (D08–D09)

**Owns:** security settings, `auth-context.tsx`, providers/cache lifecycle, session route, organization policy read handler, associated auth/admin tests. Does not own dashboard layout.
**Interfaces:** `logout(): Promise<void>` rejects on unconfirmed session-delete and sensitive client content is cleared; layout in Task 6 displays that rejection. Policy verification performs GET/read capability only, preserving high-assurance authorization on writes. Query reset must be safe outside QueryClient context used by isolated tests.

- [x] Add failing tests: Verify performs no PUT and leaves verified/SSO-only fields untouched; DELETE 503/offline rejects; bounded revoke failure still expires local cookies when endpoint handles it; prior identity requests cannot repopulate a new sensitive cache.
- [x] Implement read-only verification, explicit teardown error, bounded revocation, and guarded finite hydration if needed for this flow.
- [x] Preserve normal full-reload passwordless login and all high-assurance requirements; do not implement a new first-passkey proof ceremony.
- [x] Run focused auth/session/organization tests and notify Task 6 of final logout behavior.
- [x] Write `session-admin.md`; obtain security/tenant-focused independent review before commit.

## Task 5: Truthful status and integrity coverage (D07, D11)

**Owns:** dashboard overview, Issues, compliance score page, snapshots, conditional audit-log wording, metrics/compliance widgets, `use-api.ts` metrics behavior, admin system routes/compliance status service, scoring response metadata and associated tests.
**Shared constraint:** Exceptions count state belongs to Task 3. Avoid `api-client.ts` edits without controller coordination. Preserve frontend/backend type consumers when adding metadata.
**Interfaces:** Unknown verifier stays unavailable; real zero remains zero; all-clear requires every necessary successful complete source. Snapshot verdict carries actual hash version/coverage. Score policy metadata originates from backend or a single authoritative contract.

- [x] Add failing fixtures for verifier unavailable with existing records, failed readiness with healthy health endpoint, sixth-case blocker, new unassessed workspace, and legacy identity-only hash.
- [x] Implement source availability and coverage states without fabricating a new assessment; remove unsupported blanket assurance.
- [x] Align scoring weights/explanations with actual backend policy and ensure real zero is retained.
- [x] Run focused overview/issues/compliance/snapshot tests and changed backend tests.
- [x] Write `truthful-status.md` with any report items left open; obtain independent review before commit.

## Task 6: Shared navigation, feedback and recovery (D17–D18)

**Owns:** dashboard layout, global layout/skip target, toast implementation, accessibility widget/CSP-compatible preference handling, handled-boundary error reporting and related UI tests.
**Interfaces:** Task 4 logout rejects when unconfirmed; render pending/error state in desktop and mobile. Existing Radix Dialog provides modal semantics and focus lifecycle. Error reporting uses existing sanitized client reporter.

- [x] Add failing behavioral tests for actual toast update/dismiss identity; hidden-link focus; drawer initial/trapped/returned focus; skip target; mobile sign-out including rejection.
- [x] Repair native navigation semantics, accessible modal/skip behavior and shared logout affordance; maintain capability gating.
- [x] Allocate toast identity once and report handled errors through existing instrumentation without duplicate/sensitive logging.
- [x] Make font preference truthful under enforced CSP using available assets or explicit load/failure behavior; do not add an unlicensed font/dependency.
- [x] Run navigation/core/toast/error tests and document any manual browser checks still unavailable in `shell.md`.

## Task 7: Integration and release evidence

**Owns:** controller only; docs, coordinated shared changes and integration fixes delegated to originating worker.

- [x] Independently review each lane against design and tests; resolve important findings with the same owner and scoped re-review.
- [x] Run aggregate impacted frontend tests, lint/design lint, build, and backend suites covering changed contracts; explain environmental failures precisely.
- [x] Run an independent whole-branch review for tenant boundaries, consequential state transitions, contract compatibility and scope.
- [x] Update a checked-in delivery record with completed tasks, exact validation, unresolved requirements and next program milestone.
- [x] Commit reviewed changes in logical batches and prepare a reviewable branch/draft PR if the authenticated remote supports it. No merge or deployment.

## Follow-on program

D10/D12–D16/D19–D22 and browser/performance measurements remain explicit follow-on packages unless this milestone's implementation directly closes their acceptance criteria. Do not mark an entire package complete for a partial overlapping repair. The comprehensive audit under `/workspace/reports/dashboard-audit/REPORT.md` contains the full program and detailed source evidence.
