# Dashboard reliability repair design

## Intent and scope

The operator must be able to receive or import evidence, inspect it, deliberately resolve exceptions, review a request, generate an export, and retain its history. A failed, incomplete, unavailable or unassessed operation must not appear completed, clear, compliant or verified.

The user authorized the engineering roadmap after the comprehensive dashboard review and asked for coordinated execution. This document preserves the design for the first implementation milestone: the verified production-path defects in work packages D01–D09, scoring-policy consistency (D11), and shared navigation/feedback repairs (D17–D18). The remaining program is explicitly tracked below; completion of this milestone does not imply all 22 audit work packages are complete.

## Approach

Repair existing contracts and state transitions in place, using existing FastAPI routers, Next.js clients, TanStack Query, Radix components and test infrastructure. Keep production router policy, permission checks, high-assurance requirements, tenant isolation, immutable evidence, and existing persistence owners authoritative. Do not introduce new services or dependencies.

1. Receiving supplies required KDEs and a stable per-submission idempotency key through the proxy, checks durable event outcomes, and preserves rejected rows. Observed identities are separate from expected identities; contradictory lot/product scans cannot auto-verify.
2. URL ingestion recognizes the actual synchronous document response. CSV receipts and analysis failures retain identity and truthful status. Exceptions require case-specific rationale, deliberate confirmation, pending/error handling, and stale-transition feedback.
3. Recall consumes real response envelopes and valid bounded export dates. Generating an artifact and completing a request are separate confirmed operations. Request list/detail expose valid sign-offs and retain completed cases. Milestone completion comes from actual work; elapsed time expresses urgency only.
4. Policy-access verification is read-only. Logout reports confirmation failure, clears sensitive local state, and bounds backend revocation. Account-bound caches cannot survive supported identity changes. Preserve full-reload passwordless login behavior; its normal relogin is not a demonstrated cache leak.
5. Integrity and readiness responses carry truthful availability/provenance. No fallback infers chain validity from sequence count. Unknown is not zero. New workspaces are unassessed. Legacy snapshot verification states its actual coverage. Score explanations use the actual policy.
6. Shared navigation preserves native semantics, excludes hidden items, uses a real modal focus lifecycle, and includes mobile sign-out. Toast lifecycle uses one identity. Handled render failures reach the existing sanitized reporter. Accessibility preferences only claim successfully available behavior.

## Constraints and success criteria

- No production deployment, merge, external notification, or customer-data mutation is part of implementation verification.
- Preserve the exact production router allowlist; repair optional feature presentation without enabling its backend.
- No new authentication bootstrap ceremony or weakened guard is inferred from this repair authorization. Existing eligible credential paths remain; unsupported enrollment gets accurate guidance pending a separately reviewed security design.
- Every consequential defect receives a regression assertion that fails against the old behavior, plus targeted existing coverage.
- Test actual wire shapes, proxy forwarding, mixed batches, failed writes, stale transitions and delayed responses.
- Keep frontend/backend contract changes additive where possible; audit all changed type consumers.
- All changes occur on `codex/dashboard-reliability` in an isolated worktree. The original checkout stays unchanged.
- Record tests, review findings, resolutions, and remaining work in the execution ledger; do not claim browser validation when no browser was exercised.

## Program after the first milestone

| Work package | Required follow-through |
|---|---|
| D10 | Shared pagination envelopes, complete server totals, globally ordered agent reviews, supplier aggregates, people/role traversal |
| D12 | Shared capability-aware route/actions; fix approved Auditor gate, invalid destinations and empty-catalog creation |
| D13 | Durable CSV receipt-to-canonical-record handoff, row correction and resumable evidence investigation |
| D14 | Independent alert acknowledgment/resolution, discoverable unresolved work and preserved failed notes |
| D15–D16 | Known configuration baselines, optimistic concurrency, one-time invite links and delivery feedback |
| D19 | Finite auth hydration now where coupled; separately reviewed first-passkey proof/recovery design |
| D20 | Typed artifact transport and real QR/PDF/markdown shapes before graph capability promotion |
| D21–D22 | Immutable evaluation binding, immutable curation identities, recoverable enqueue, honest identity/integration capability |
| Measurement | Authenticated browser/assistive-technology pass and route/performance baseline before optimization targets |

## Risk controls

Repair first-failure chains as a unit: a receiving header-only fix is incomplete; a recall envelope-only fix exposes unsafe completion. Never substitute hard-coded acceptance or client truth for backend persistence. New output metadata must not imply verification occurred. Significant auth/tenant changes receive independent review. Any unimplemented requirement remains visible in the ledger and final handoff.
