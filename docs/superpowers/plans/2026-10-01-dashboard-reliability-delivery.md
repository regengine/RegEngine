# Dashboard reliability milestone — delivery record

Date: 2026-10-01. Branch: `codex/dashboard-reliability`. Base: `0927b85a8f934889bab73a0f0a94562e10a3c3aa`. Final application commit: `b494d9b2`.

The first repair milestone is implemented and independently reviewed. It corrects receiving/import outcomes, evidence and readiness claims, request completion, policy/session behavior, and shared dashboard navigation and feedback. This delivers the scoped repairs from D01–D09, D11 and D17–D18, with partial D13/D19 overlap. It does **not** close all acceptance criteria in the 22-package dashboard audit; authenticated browser validation and the remaining program are listed below.

Design: [dashboard reliability design](../specs/2026-10-01-dashboard-reliability-design.md). Implementation checklist: [implementation plan](2026-10-01-dashboard-reliability.md).

## Changes and operator impact

| Lane | Delivered behavior | Impact and remaining limit |
|---|---|---|
| Receiving, D01–D02 | Required receiving KDE inputs; observed identity separated from expectations; conflicting/ambiguous identifiers rejected; stable per-payload idempotency header forwarded; success requires coherent persisted event outcomes; accepted rows excluded from retry. Late responses cannot revive a replaced tenant/submission context. | Prevents false receipt completion and incorrect lot association. Authenticated browser requests bypass shared response caching; backend content-based durable deduplication provides separate duplicate-write protection. Draft persistence and reconciliation after an uncertain network receipt remain follow-ons. |
| Import and exceptions, D03/D06 and partial D13 | Synchronous URL `document_id` receipts no longer enter job polling; real asynchronous failures terminate visibly; replaced input disposes old monitors. CSV `ingestion_run_id` links to the existing authenticated receipt. Exception resolve/waive requires deliberate rationale, preserves failed input, and exposes stale transition conflicts. Detail failures have retry/error states. | Keeps failed or partial work actionable and improves the sign-off audit trail. A dedicated receipt-to-canonical-record correction flow is still needed. |
| Recall and requests, D04–D05 | Real paginated envelopes; mandatory bounded export dates; awaited nonempty audited export; separate explicit completion attestation. Durable row-locked completion binds tenant, export hash/type/date range and operator evidence. Completed/amended history stays readable. Valid sign-offs support review, ready and missing-scope recovery. Persisted UUID rows load correctly; overdue status derives after loading. | Operators can distinguish artifact generation, recorded completion and urgency. Replays preserve completion time and failed persistence cannot publish completion. Operator scope attestation is not automated coverage verification or proof of external delivery. |
| Policy and session, D08–D09 | Policy access verification uses GET and preserves the high-assurance guard. Supported tenant/credential changes cancel and clear query caches. Logout clears sensitive local state and exposes browser DELETE failure with retry. Server revocation is bounded and reports its confirmation separately from local cookie expiry. | Removes a policy mutation from an access check and gives operators recoverable sign-out feedback. Browser cookie behavior and a new first-passkey proof ceremony are not verified/implemented here. |
| Readiness and integrity, D07/D11 | Overview all-clear requires valid verification and complete successful required sources. Unknown is distinct from zero; verifier scope is visible. Issues inspect every active case returned by the deadline endpoint with bounded concurrency; the endpoint cap still limits global completeness. New workspaces are unassessed. Failed preflight refresh suppresses stale eligibility. Score explanations use backend policy metadata; snapshots state actual hash version/coverage. | Reduces false reassurance from outages, empty datasets, limited verification and legacy hashes. Authoritative collection totals and comprehensive freshness metadata remain separate work. |
| Shared shell, D17–D18 | Native navigation; collapsed children unmounted; Radix mobile dialog focus lifecycle; mobile logout and recovery; content skip target; one toast identity; sanitized reporting from all 17 dashboard error boundaries. | Repairs common keyboard, feedback and error-recovery paths. OpenDyslexic is explicitly unavailable because no licensed local asset exists; CSP was not weakened. Browser/assistive-technology conformance remains unclaimed. |

## Completion API compatibility

`PATCH /api/v1/sla/requests/{request_id}/complete` intentionally rejects bodyless or `export_ids`-only completion with **422**. Consumers must generate an audited, nonempty `fda_export_all` artifact for the authenticated tenant and submit its actual hash and exact date range:

```json
{
  "export_hash": "<actual 64-character lowercase hexadecimal export hash>",
  "start_date": "2026-09-01",
  "end_date": "2026-09-30",
  "completion_notes": "Describe the reviewed scope and the completion evidence.",
  "acknowledged": true
}
```

The date window must pass the existing export validator (maximum 90 days). The illustrative hash placeholder is not valid input. A missing/mismatched durable artifact returns 409; unavailable completion persistence returns 503. The updated dashboard sends the new body. Coordinate any other API consumers before deployment; no database migration or dependency change is included.

Session DELETE now distinguishes local cookie expiry from confirmed central revocation through `local_cookie_expiry` and `revocation_confirmed`. A successful local response must not be described as confirmed central invalidation when the latter is false.

## Verification

| Check | Final result | Scope |
|---|---|---|
| Full frontend Vitest suite | **154 files; 1,127 passed, 2 existing skips** | Final frontend application source at `c2a785f9`; later application changes affect only backend overdue classification. |
| Impacted backend suite | **370 passed, 0 failures/errors/skips** | Admin organization/hardening/tenant boundaries, receiving validation, exceptions, SLA evidence/tracking, request workflows, scoring and snapshot invariants; rerun after the final backend fix. |
| Real local PostgreSQL | **3 passed**, included in the 370 | Normal runtime role; cold-cache durable completion/replay, cross-tenant artifact rejection, failed write rollback, and scope-signoff recovery through submission. Synthetic fixtures use outer rollback/savepoints. |
| Production Next.js build | **Passed**, including TypeScript | Standard `npm run build`; 187 static pages generated. |
| ESLint and design lint | **Passed**, 0 errors; 41 existing warnings | Design lint clean across 682 files. Existing warnings are retained. |
| Independent review | **Accepted with recorded limits** | Six lanes reviewed; important findings repaired and re-reviewed. Whole-branch review identified one additional overdue-load defect; one final fix and scoped re-review resolved it. |

Frontend commands (from `frontend/`, Node 20 on PATH):

```sh
npm run test:run -- --maxWorkers=2
NEXT_TELEMETRY_DISABLED=1 npm run build
npm run lint
```

Final backend command (repository root, configured local disposable PostgreSQL; do not point the opt-in fixture at a shared database):

```sh
source /workspace/setup/regengine-dev-env.sh
REGENGINE_RECALL_TEST_DATABASE_URL="$DATABASE_URL" venv/bin/python -m pytest \
  services/admin/tests/test_admin_organizations_router.py \
  services/admin/tests/test_admin_service_hardening.py \
  services/admin/tests/test_compliance_service_sync_tenant_isolation.py \
  services/admin/tests/test_compliance_routes_idor.py \
  services/ingestion/tests/test_receiving_dashboard_contract.py \
  services/ingestion/tests/test_exception_router.py \
  services/ingestion/tests/test_exception_router_1342.py \
  services/ingestion/tests/test_sla_completion_evidence.py \
  services/ingestion/tests/test_sla_tracking_1342.py \
  services/ingestion/tests/test_request_workflow_router.py \
  services/ingestion/tests/test_request_workflow_router_1342.py \
  services/ingestion/tests/test_recall_lifecycle_postgres.py \
  tests/test_request_workflow_unit.py \
  services/ingestion/tests/test_compliance_score_1342.py \
  services/ingestion/tests/test_compliance_score_2708.py \
  services/ingestion/tests/test_compliance_score_2960_2962.py \
  tests/invariants/test_compliance_snapshots.py -q --no-cov
```

The frontend worktree initially reused a dependency symlink that Turbopack rejected as outside its filesystem root. Copying the already installed locked dependencies locally restored the standard build; no manifest, lockfile or build configuration changed. The first aggregate frontend run exposed a gating test that queried collapsed links; it now opens the visible disclosure and preserves flag-off assertions. The full suite then passed.

Regression evidence includes reproduced old-source failures for review findings and other targeted defects, but **not every initial assertion has a separate recorded failing old-source run**. This is a process limitation against the design's stronger regression-evidence goal. Passing implementation-shaped assertions alone are not claimed as proof of the original failure.

Local execution artifacts are retained under `/workspace/reports/dashboard-execution/`: lane reports, independent review reports, `frontend-suite.log`, `final-backend-suite.log`, `backend-results.xml`, `final-build.log`, `final-lint.log`, and `final-fix.md`. These workspace artifacts are not part of the repository; this record preserves their principal results for PR reviewers.

## Remaining work and rollout gates

1. **Before production release:** authenticated browser traversal of receive → import → investigate → review → export → completion/history; real browser cookie sign-out/retry; keyboard/mobile/screen-reader/zoom checks; review the completion API consumer migration. No deployment or merge was performed here.
2. **Next implementation milestone — complete and reachable evidence (D10/D12/D13):** unify server pagination/totals and global priority order; make primary actions respect capabilities and carry case/lot context; connect durable import receipts to canonical records and row correction. Acceptance must include the only critical item beyond the first page and reload recovery of a partial upload.
3. **Configuration and operational recovery (D14–D16/D19):** separate alert acknowledgment from remediation, protect configuration writes with known baselines/concurrency, expose real invitation delivery/link state, and design first-passkey enrollment proof/recovery.
4. **Artifact and experimental workflow contracts (D20–D22):** typed verified export bytes, immutable evaluation/input binding, immutable curation identity, recoverable enqueue and honest integration capability before promotion.
5. **Measurement:** capture route performance and accessibility baselines before setting optimization targets. No quantified production speed, conversion or incident-reduction impact is claimed.

Nonblocking review observations remain visible: receiving's page-local generation boundary could explicitly consume the credential identity epoch for future same-route identity replacement; submitted/amended request detail can show a fallback `0.0h remaining`. The review did not establish a normal offered same-route credential replacement that causes a receiving leak. Neither observation was silently promoted into a claim of fixed behavior.

Evidence limits: no authenticated browser or assistive-technology session, actual browser cookie store, independent-session database race, database restart, customer-data/live-verifier exercise, external file delivery, or whole-repository backend suite was run. Local PostgreSQL tests prove the exercised SQL/UUID and rollback paths, not those broader properties.
