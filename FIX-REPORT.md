# FIX-REPORT: PR #3233 ([qa] Admin auth, role, invite, export and tenant-scope unit coverage)

Merge commit f9ea84fa29cfe0f0241bceb297fd0748ed57f1ad. PR #3233 added only
`services/admin/tests/test_qa_admin_auth_scope_export_invite_wave2.py`
(485 lines); no product code changed. All fixes below are test-only
strengthening in that same file. Product files (`auth_routes.py`,
`dependencies.py`, `invite_routes.py`) were temporarily mutated to prove
each new test fails without the fix, then restored by hand edit.
`git status` confirms only the test file differs.

Reports read: all six re-rv-3233-<angle> SUMMARY.md files (correct,
security, tenant, tests, blast, ops SUMMARY.md plus ops REPORT.md), and
lead/area mentions of #3233 in re-rv-lead-tests, re-rv-lead-blast,
re-rv-lead-correct, re-rv-lead-ops, re-rv-lead-security, re-rv-lead-tenant,
re-rv-area-tenant, re-rv-int-rollback.

## Findings

| # | Source report | Severity | Finding | Status | Reason / proof |
|---|---------------|----------|---------|--------|----------------|
| 1 | re-rv-3233-tests Medium 1 (also re-rv-lead-tests, re-rv-area-tenant item 13) | Medium | `test_none_tenant_returns_empty` passed a bare MagicMock and asserted `== []`, so deleting the no-tenant fail-closed guard in `_resolve_session_permissions` stayed green | FIXED AND TESTED | Renamed to `test_none_tenant_returns_empty_without_touching_db`: db double now yields a role with `permissions=["users.read"]` and the test asserts `db.execute` was not called. Temporarily replacing the guard with `pass` made only this test FAIL; restored, full file green. |
| 2 | re-rv-3233-tests Medium 2 (also re-rv-3233-tenant Low, re-rv-lead-tests, re-rv-area-tenant item 13) | Medium | Tenant/user SQL predicates replaced by canned mock rows; removing WHERE filters in PermissionChecker, `_resolve_session_tenant_id`, `_resolve_session_permissions`, `_load_active_organization_membership` stayed green | FIXED AND TESTED | Added `TestTenantScopePredicates` (4 tests) capturing the statement passed to `db.execute` and asserting bound params plus table-qualified columns (`memberships.user_id`, `memberships.tenant_id`, `memberships.is_active`, `organization_memberships.user_id`). Proved each: dropping the tenant predicate in `_resolve_session_permissions` FAILED the permissions test; dropping it in PermissionChecker FAILED the checker test; dropping the user predicate in `_resolve_session_tenant_id` FAILED the resolver test. All mutations restored by hand; file green. |
| 3 | re-rv-3233-tests Medium 3 (also re-rv-lead-tests, re-rv-area-tenant item 13) | Medium | E2E outbox test covered only the missing-path return; an always-False function passed | FIXED AND TESTED | Added 3 tests for 4 total gate branches: fully enabled local outbox writes exactly one JSON line and returns True; cloud marker set returns False with no file; e2e mode off returns False with no file; missing path returns False (pre-existing). Temporarily stubbing `_record_e2e_invite_email` to `return False` made the positive test FAIL; restored, green. |
| 4 | re-rv-3233-tests Low 4 (also re-rv-lead-tests lows) | Low | `test_expired_session_is_rejected` used a 1-second expiry margin, so a backward clock step over 1 second between two `now()` calls could flake | FIXED AND TESTED | Trivial low, fixed: margin widened to 5 minutes; module docstring corrected from "no clock dependence" to "wide clock margins". Full file green. |
| 5 | re-rv-3233-correct, re-rv-3233-security, re-rv-3233-ops, re-rv-3233-blast | None | All four returned verdict OK with no findings | No action | Nothing to confirm or fix. |
| 6 | Out of scope per task brief | N/A | Suspended-tenant deny on live auth; tenant-scope gate failure; 7 xfail cross-tenant leaks | Not touched | Owned by other tasks, noted only. |

## Test commands and results

Baseline before changes (all through the slot queue):

- `~/metacode/fleet/heavy .venv/bin/python -m pytest services/admin/tests/test_qa_admin_auth_scope_export_invite_wave2.py -q --no-cov -p no:cacheprovider` => 40 passed.

After changes:

- Same file => 47 passed (40 existing incl. 1 renamed, plus 7 new: 4 predicate, 3 outbox).
- `~/metacode/fleet/heavy .venv/bin/python -m pytest services/admin/tests/test_qa_admin_auth_scope_export_invite_wave2.py services/admin/tests/test_e2e_safety.py -q --no-cov -p no:cacheprovider` => 51 passed.
- `~/metacode/fleet/heavy .venv/bin/ruff check services/admin/tests/test_qa_admin_auth_scope_export_invite_wave2.py` => All checks passed.
- `~/metacode/fleet/heavy .venv/bin/ruff format --check services/admin/tests/test_qa_admin_auth_scope_export_invite_wave2.py` => 1 file already formatted (after running `ruff format` once, which also normalized one pre-existing block).

Fail-without-fix proof (temporary product mutations, each restored by hand edit, verified via `git status` showing only the test file modified):

- Guard `if tenant_id is None: return []` replaced with `pass` => `test_none_tenant_returns_empty_without_touching_db` FAILED, all others passed.
- `MembershipModel.tenant_id == tenant_id` removed from `_resolve_session_permissions` => `test_resolve_session_permissions_scopes_to_user_and_tenant` FAILED (first attempt with params-only assertion did not catch it because `TENANT_ID` is also bound by the RoleModel predicate; strengthened to table-qualified `memberships.tenant_id` string check, then it failed as required).
- `MembershipModel.tenant_id == current_tenant_id` removed from PermissionChecker => `test_permission_checker_scopes_to_user_and_tenant` FAILED.
- `MembershipModel.user_id == user_id` removed from `_resolve_session_tenant_id` => `test_resolve_session_tenant_id_scopes_to_user_and_active` FAILED.
- `_record_e2e_invite_email` stubbed to `return False` => `test_fully_enabled_local_outbox_writes_one_record` FAILED.

`scripts/security/scan_tenant_scope.py` was not run because no queries were touched (test-file-only change).

## Needs C.Lee's decision

None. Test-only change, no product behavior altered, no migration, no API change.
