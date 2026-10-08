# FIX-REPORT: PR #3225 Team invites (merge efcccfed915b4d806ff252a7cccd8093edcd4452)

Sources read: all six re-rv-3225-<angle> SUMMARY.md (blast, correct, ops,
security, tenant, tests), plus the 3225 rows in re-rv-lead-blast,
re-rv-lead-ops, re-rv-lead-security, re-rv-lead-tenant, re-rv-lead-tests,
re-rv-area-auth, and re-rv-int-deploy-readiness. Every cited location was
re-read in the worktree before fixing. Out-of-scope items from the task
(suspended-tenant deny on live auth, tenant-scope gate failure, 7 xfail
cross-tenant leaks) were not touched.

| # | Source report | Severity | Finding | Status | Reason / proof |
|---|---|---|---|---|---|
| 1 | re-rv-3225-blast High; re-rv-3225-correct Medium; lead-blast High | High | accept_invite lower() user lookup uses scalar_one_or_none; two users rows differing only by case raise MultipleResultsFound, escaping as 500 instead of the uniform 400 | FIXED AND TESTED | try/except in accept_invite rolls back and raises the existing generic 400; new test fails on old code with MultipleResultsFound |
| 2 | re-rv-3225-blast Medium; lead-blast Medium | Medium | create_invite member check (line 192) and pending-invite check (line 202) use exact email match while accept folds case, so a case variant of a member gets a mailed invite whose token burns on the accept-time 400 | FIXED AND TESTED | both checks now compare func.lower(email) to the folded invite address; both new 409 tests fail on old code (got 200 with a mailed invite) |
| 3 | re-rv-3225-correct High | High | require_team_write demands require_permission("team.write"), which the plain admin scope on issued keys (dev bypass, demo admin) does not imply, so real admin callers get 403 on invite and role change | FIXED AND TESTED | team_mgmt.require_team_write is now a dependency that accepts team.write or plain admin, delegating to each scope's own require_permission gate so tenant-mismatch checks and rate limiting still run; owner assignment still needs owner tier; new plain-admin tests fail on old code with 403 |
| 4 | re-rv-3225-correct Medium | Medium | update_role never reads the member's current role, so a team.write (non-owner-tier) caller can demote an owner to admin or viewer | FIXED AND TESTED | update_role now runs the owner-tier check when the target member's current role is owner; new test fails on old code (got 200) |
| 5 | re-rv-3225-correct Low | Low | EmailOwnershipConflictError fires for unverified rows too, but the text and comments said verified | FIXED AND TESTED | docstring, message ("already registered for a different user"), and accept_invite comment corrected; existing tests still pass (message keeps the "different user" match) |
| 6 | re-rv-3225-blast Low | Low | team.write granted nowhere; double require_api_key call consumes two rate-limit tokens per write; GETs unchanged | Not fixed (low, pre-existing) | finding 3 fixes the admin-key 403; the double key check and rate-limit accounting predate PR #3225 and only affect callers of these two non-production routes |
| 7 | re-rv-3225-ops, re-rv-3225-security, re-rv-3225-tenant, re-rv-3225-tests, lead-security, lead-tenant, lead-tests, area-auth, int-deploy-readiness | OK / none | No findings; tenant isolation, auth, and test coverage confirmed | No change needed | verified by reading; full test pass below |

## Exact test commands and results

All commands were prefixed with ~/metacode/fleet/heavy and run from the worktree root with the shared .venv (symlink, nothing installed).

1. `~/metacode/fleet/heavy .venv/bin/pytest services/ingestion/tests/test_team_mgmt_1342.py services/admin/tests/test_passwordless_identity_provisioning.py services/admin/tests/test_invite_case_variant_create_3225.py services/admin/tests/test_invite_audit_chain_guard_2857.py services/admin/tests/test_accept_invite_rls_2899.py services/admin/tests/test_invite_routes_email.py services/admin/tests/test_qa_admin_auth_scope_export_invite_wave2.py --no-cov -p no:cacheprovider`
   Result: `130 passed in 9.10s`
2. Fail-without-fix confirmation (each fix temporarily edited away by hand, test re-run, fix re-applied):
   - `test_accept_invite_ambiguous_case_variant_users_returns_400` on old code: FAILED with `MultipleResultsFound` (the production 500).
   - `test_case_variant_of_member_returns_409` and `test_case_variant_of_pending_invite_returns_409` on old code: FAILED (got 200 with an invite row created).
   - `test_plain_admin_scope_can_invite_viewer` and `test_plain_admin_scope_can_change_role` on old code: FAILED (got 403).
   - `test_team_write_caller_cannot_demote_owner` on old code: FAILED (got 200).
3. `~/metacode/fleet/heavy .venv/bin/python scripts/security/scan_tenant_scope.py`
   Result: only the two known pre-existing `services/graph/app/traceability_linker.py` findings (out of scope for this task); nothing new from the touched files.
4. `~/metacode/fleet/heavy .venv/bin/ruff check <all six touched files>`
   Result: `All checks passed!` (one I001 in the new test file was fixed by moving imports to the top).
   `ruff format --check` flags blank-line drift in invite_routes.py that predates this change; left untouched.

## Needs C.Lee's decision

1. Case-variant duplicate users rows are now a clean 400, but the underlying data problem remains. Recommend a follow-up migration that merges such pairs and adds a unique index on lower(email). Until then, any address with a case-duplicate pair cannot accept invites.
2. Unverified user_emails rows stay unclaimable by invitees (fail closed). If product wants a token holder to claim a stale unverified row, say so; that would loosen finding 5 deliberately.
3. No migration was added, no scopes or permissions helpers were widened (permission_implies untouched), and the ingestion team router stays off the production router allowlist.
