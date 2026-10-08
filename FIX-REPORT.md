# FIX-REPORT for PR #3241: Stop bulk upload and webhook paths from reporting success on failure

Merge commit b68cab26905324d3fdb4b5a8b820c975f15e895d. Reports read: all six
re-rv-3241-<angle> SUMMARY.md files, plus lead-correct, lead-blast, lead-ops,
lead-security, lead-tenant, lead-tests, area-webhooks, int-deploy-readiness,
int-error-semantics and int-frontend-build sections that mention #3241.

## Findings table

| # | Source report | Severity | Status | Reason |
|---|---|---|---|---|
| 1 | re-rv-3241-correct HIGH, re-rv-lead-correct #14, re-rv-area-webhooks #4: failed webhook still acked as seen, status route still reports durable queue | High | FIXED AND TESTED | `_process_new_items` now withholds the seen-ack when notify() adds an unpersisted dead letter, and `_webhook_dlq_status` reports the live count plus `at_risk` |
| 2 | re-rv-3241-correct Low: commit 400 drops row-level detail | Low | FIXED AND TESTED | Trivial: the ValueError now names section, row and message for up to 5 blocking errors |
| 3 | re-rv-3241-blast Low, re-rv-int-frontend-build Low: frontend type and UI miss `validation_warning_count` / `validation_warnings` | Low | FIXED AND TESTED | Trivial: two optional fields added to `SupplierBulkUploadCommitSummary`, warning block rendered next to the sync-warning block; standalone tsc parse clean, no syntax errors |
| 4 | re-rv-3241-tests Low 1: sequential test passes on old global, thread test is timing-dependent | Low | FIXED AND TESTED | Trivial: added deterministic barrier-interleave test `test_concurrent_validations_isolated_with_forced_interleave` |
| 5 | re-rv-3241-tests Low 2: `TestUnpersistedNack` never asserts the error logs | Low | FIXED AND TESTED | Trivial: both tests now assert `webhook_dead_letter_unpersisted` / `webhook_outbox_append_failed` via a logger mock |
| 6 | re-rv-3241-tests Low 3: commit test checks only 400 and `failed` status | Low | FIXED AND TESTED | Trivial: asserts detail text names `event row 1` and that no facility or event rows were inserted |
| 7 | re-rv-3241-correct open question: autofill `TLC-UNKNOWN` commits stay HTTP 200 | Low (question) | BLOCKED | Needs product confirmation that fabricated lot codes are acceptable regulatory data; test `test_commit_summary_carries_autofill_warnings` pins current behavior, left unchanged |
| 8 | re-rv-int-error-semantics Medium 1 (`supplier_graph_sync.py` RuntimeError swallow) and Medium 2 (POSTGRES boot gate) | Medium | BLOCKED | Out of scope: files belong to PR #3243 / #3234 territory, not PR #3241; listed for Christopher's routing |
| 9 | Task out-of-scope items: suspended-tenant deny on live auth, tenant-scope gate failure, 7 xfail cross-tenant leaks | Mixed | BLOCKED | Owned by other tasks, noted only |

## Exact test commands and results

All run through `~/metacode/fleet/heavy` with the shared `.venv` (symlink, nothing installed).

1. ` .venv/bin/pytest services/scheduler/tests/test_notifications.py services/scheduler/tests/test_scheduler_hardening.py services/scheduler/tests/test_webhook_dlq_2510.py services/scheduler/tests/test_webhook_retry_1150.py services/scheduler/tests/test_kafka_emit_observability.py services/scheduler/tests/test_kafka_delivery_ack_2711.py services/scheduler/tests/test_silent_failures_2697.py tests/test_scheduler_dlq_unpersisted_status_3241.py -p no:cacheprovider --no-cov`
   Result: `82 passed in 1.59s`, exit 0.
2. `.venv/bin/pytest services/admin/tests/test_bulk_upload_false_success.py services/admin/tests/test_bulk_upload_validators_1342.py -p no:cacheprovider --no-cov`
   Result: `39 passed in 1.35s`, exit 0.
3. `.venv/bin/pytest tests/test_monolith_observability_drift.py -p no:cacheprovider --no-cov`
   Result: `17 passed in 4.77s`, exit 0.
4. `.venv/bin/ruff check` on all 8 changed Python files: `All checks passed!`
5. `.venv/bin/ruff format --check` on all touched Python files: clean (one hunk auto-formatted in bulk_upload/routes.py, tests re-run green after).
6. Frontend: `tsc --noEmit` standalone parse of `frontend/src/types/api.ts` (exit 0, no errors) and `frontend/src/app/onboarding/bulk-upload/page.tsx` (zero syntax errors, zero errors on edited lines 827-836; only missing-node_modules import/JXS-runtime artifacts identical to adjacent pre-existing lines). Full `npm run lint` / `npm run build` not run: `frontend/node_modules` is absent and a full `npm ci` was disproportionate for a 12-line additive UI change.

`scripts/security/scan_tenant_scope.py` not run: no queries were touched, and the gate is already red on main (owned by another task per the brief).

## Old-code failure confirmation (each new test fails without its fix)

1. Ack withhold: temporarily forced `webhook_ack_withheld = False` in `service.py`, ran `TestUnpersistedWebhookWithholdsAck`: `1 failed, 1 passed` (the withhold test failed, the durable-behavior test passed). Fix restored, suite green.
2. Status `at_risk`: temporarily reverted the `or unpersisted > 0` clause, ran the new status file: `1 failed, 2 passed`. Also verified via `git show HEAD:server/routes_scheduler_status.py` that the old dict contains zero mentions of `unpersisted`. Fix restored, suite green.
3. Commit detail: temporarily restored the old bare ValueError message, ran the strengthened commit test: `1 failed`. Fix restored, suite green.
4. Barrier isolation: temporarily simulated the pre-3241 shared global in `validators.py` (collector returns `_AUTOFILL_WARNINGS`, clear at start, read global at end), ran the new barrier test: `1 failed in 0.45s` (deterministic, no hang). Fix restored, suite green.
5. Log asserts: temporarily deleted the two `logger.error` calls in `notifications.py` (counter kept), ran `TestUnpersistedNack`: `2 failed, 1 passed`. Fix restored, suite green.

No fix was backed out: every attempted fix passed its tests on the first full run.

## Items needing Christopher's decision

1. Autofill commits (`TLC-UNKNOWN`, `Unnamed Facility`) still return 200 `completed` with warnings. Confirm fabricated lot codes are acceptable regulatory data, or say they must block like unknown FTL categories do.
2. Route the two int-error-semantics mediums (graph-mirror RuntimeError swallow in `services/admin/app/supplier_graph_sync.py`, POSTGRES variables missing from the boot-required list) to the owning task; they were found while reviewing #3241 but live in other PRs' files.
3. Deploy note (no code change): dashboards may show new webhook error/warning volume (`webhooks_delivered` now logs at warning on partial failure, plus `webhook_ack_withheld`); if any alert pages on scheduler warning event names, expect new pages until `WEBHOOK_OUTBOX_PATH` is set.
