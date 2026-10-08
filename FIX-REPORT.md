# FIX-REPORT: PR #3234 follow-up (audit fail-closed)

PR #3234 merge commit f40df74cb0c68aa27b05c2c1a55df1b8e40acfeb.
Scope: confirmed CONCERN and BLOCKER findings rated critical, high or medium.
Out of scope per task (noted, not fixed): the suspended-tenant deny on live
auth, the tenant-scope gate failure, the 7 xfail cross-tenant leaks, and the
two re-rv-int-error-semantics mediums that belong to PR #3243
(supplier_graph_sync RuntimeError swallow, REQUIRED_PRODUCTION_CREDENTIALS
boot gap).

## Findings

| # | Source report | Severity | Finding | Status | Reason |
|---|---|---|---|---|---|
| 1 | re-rv-3234-correct HIGH, re-rv-lead-correct, re-rv-area-data | High | `epcis/validation.py` `create_task` and `chain_verification_job.py` `ensure_future` detach the audit write; a failed write dies silently in the task and the request or job still finishes | FIXED AND TESTED | Done callbacks now log the failure at error level; sync-path swallow raised from debug to error; docstrings state best-effort honestly |
| 2 | re-rv-3234-correct MEDIUM, re-rv-3234-blast MEDIUM, re-rv-lead-blast, re-rv-lead-ops | Medium | Retention helpers commit the delete then catch `AuditStorageError` as generic failure and return False (same as row not found); `process_deletion_request` reports `soft_deleted` false with null error | FIXED AND TESTED | `AuditStorageError` re-raised after commit in soft and hard delete; `process_deletion_request` reports committed delete with audit error; cleanup job counts the loud failure per record and keeps sweeping |
| 3 | re-rv-3234-tests MEDIUM, re-rv-lead-tests, re-rv-area-data | Medium | `TestAuditWriteFailures` runs only in non-required test-suite-check, so reverting the raise can merge green | FIXED AND TESTED | `tests/shared/test_audit_logging.py` added to the blocking `repo-root-suite` offline pytest in backend-ci.yml; file uses fakes and mocks only, ~0.4s |
| 4 | re-rv-3234-correct LOW | Low | `storage.py` raises `AuditStorageError` with no `__cause__` because admin `log_event` swallows the driver error | Not fixed | Fixing needs the admin audit path to stop swallowing or to hand back the driver error, which changes direct admin caller behavior; larger than a trivial fix |
| 5 | re-rv-3234-correct LOW, re-rv-3234-security | Low | `audit_action` skips `BaseException` and drops the audit error on double failure | Not fixed | Matches pre-PR behavior, re-raises the function error so nothing reads as success, locked by test; security reviewer accepted |
| 6 | re-rv-3234-tests LOW | Low | Two preservation tests pass on full revert, so they do not prove the change | Partially fixed | Mask test now also asserts the `audit_action write failed` error record, which old code never emits; propagation test kept as a preservation lock |
| 7 | re-rv-3234-blast LOW | Low | Fire-and-forget audit task raises after a None chain write; caller status unchanged | FIXED AND TESTED | Same fix as finding 1; failure now surfaces at error level instead of as an unhandled task exception |

## Test commands (all through the slot queue) and results

1. `~/metacode/fleet/heavy .venv/bin/pytest tests/shared/test_audit_logging.py tests/shared/test_data_retention_failure_modes_2900.py services/ingestion/tests/test_epcis_validation_1342.py services/ingestion/tests/test_chain_verification_job_1342.py --no-cov -o "testpaths=tests" -p no:cacheprovider`
   Result: `150 passed in 3.05s` (repeat with `-W error::RuntimeWarning`: `150 passed in 1.84s`).
2. `~/metacode/fleet/heavy .venv/bin/ruff check <the 7 changed Python files>`
   Result: `All checks passed!`
3. `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/backend-ci.yml'))"`
   Result: `yaml ok`.

How the new tests were confirmed to fail without the fix (by hand neutralization, then restore, no git commands):

- Validation: removed `.add_done_callback(_audit_task_done)`; new test FAILED; restored; passes.
- Chain job: removed `.add_done_callback(_chain_audit_task_done)`; new test FAILED; restored; passes.
- Retention: changed both `raise` to `return False`; the 3 re-raise tests FAILED (`3 failed, 1 passed`); restored; all pass. The schedule-audit test passes both ways; it locks pre-existing correct behavior.
- Mask test: read-only check of pre-PR `writer.py` shows zero occurrences of `audit_action write failed` and the old `log` never raised on False storage, so the new error-record assertion fails on old code.

`scripts/security/scan_tenant_scope.py` was not run: no query predicate was touched (only exception handling, logging and scheduling around existing statements).

## Needs C.Lee's decision

1. Fail-closed vs best-effort for the two detached audits: they stay best-effort with error-level logging because both call sites are sync and awaiting needs async restructuring of the ingestion path and the job runner. If product wants validation rejection or chain verification to fail when the audit row is missing, that is a bigger change.
2. Retention now raises `AuditStorageError` to callers after the delete commits. In-repo callers: none found outside the module and tests. If anything outside this checkout calls `DataRetentionManager`, it must handle the new raise.
3. The blocking `repo-root-suite` gate gains one offline file (`tests/shared/test_audit_logging.py`, ~0.4s). No new dependency.
