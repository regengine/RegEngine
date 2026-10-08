# FIX-REPORT for PR #3238: MFA, suspended-tenant and role-tier fail-closed fixes

Merge commit 2ba61c588104a02555b82dcb690ceceb718ec17b, fixed on top of origin/main e854dadc.
Sources read: all six re-rv-3238-<angle> SUMMARY.md files, re-rv-3238-tenant/REPORT.md,
and the #3238 sections of re-rv-lead-blast/correct/ops/security/tenant/tests and re-rv-area-auth
plus re-rv-int-auth-kernel, re-rv-int-backend-suite, re-rv-int-env-docs, re-rv-int-perf,
re-rv-int-prod-boot.

## Findings

| # | Source report | Severity | Status | Reason |
|---|---|---|---|---|
| 1 | re-rv-3238-security (Critical), re-rv-lead-security item 1, re-rv-area-auth (Critical): suspended-tenant API-key check lives on dead dependency `get_current_tenant`, live `require_api_key` never reads `tenants.status` | Critical | OUT OF SCOPE, not fixed | Task order assigns this to another worker. Noted only. |
| 2 | re-rv-3238-correct (Medium), re-rv-lead-correct 3238 role item, re-rv-area-auth (Medium): `can_invite_role` honors `users.invite.grant_owner` on PATCH role route, so a non-Owner with that permission can self-promote to Owner in place | Medium | FIXED AND TESTED | `update_user_role` now passes `honor_grant_owner=False`; new `honor_grant_owner` flag on `can_invite_role` defaults True so invite creation is unchanged. |
| 3 | re-rv-3238-correct (Medium), re-rv-3238-tenant (Medium), re-rv-area-auth (Medium): role guard compares caller to destination role only, never to the membership current role, so an Admin can demote another Owner to Member | Medium | FIXED AND TESTED | New check in `update_user_role` returns 403 when the target membership current rank is above the caller rank (sysadmin bypass unchanged). |
| 4 | re-rv-3238-security (Medium), re-rv-3238-tenant (Medium), re-rv-lead-security item 30: `role_rank` keys only `*` and `admin.*` as Owner-tier, so a low-named custom role carrying `super_admin` ranks 20/10/0 and is assignable by mid-rank holders | Medium | FIXED AND TESTED | `super_admin` added to `_OWNER_TIER_PERMISSIONS`, matching `permission_implies` which already treats it as every permission. Invite path hardened the same way. |
| 5 | re-rv-3238-blast (High), re-rv-3238-ops (High), re-rv-area-auth (High): strict boot now requires a valid Fernet `MFA_ENCRYPTION_KEY` but `.env.example` and `docs/operations/DEPLOYMENT.md` never mention it, so the next strict deploy can fail `/readiness` | High | FIXED (docs), existing tests pass | Variable documented in both places with the Fernet generate command and no sample secret, plus a warning not to rotate over existing ciphertext. Railway values could not be verified from this checkout. |
| 6 | re-rv-3238-blast (Medium): unknown custom role names rank 0, so a custom role holding `users.manage_roles` cannot assign even Viewer | Medium | NOT FIXED, listed | Rank 0 for unknown names is the deliberate fail-closed default (see comment on `_ROLE_RANK_BY_NAME`): raising it would let an unrecognized role out-rank Owner. Needs Christopher decision on whether custom roles should rank by permission coverage instead of name. |
| 7 | re-rv-3238-blast (Medium): users page lists every role and shows generic toast on 403 | Medium | NOT FIXED, listed | Hiding unassignable roles needs caller-rank data the frontend does not currently fetch, and the backend 403 detail is intentionally opaque. Needs a small API or design decision, left for the frontend lane. |
| 8 | re-rv-3238-tests (Low): suspended/archived/missing denials assert status 403 only, a body of "suspended" would still pass | Low | FIXED AND TESTED | Added `detail == "Invalid API Key"` assertions to the three tests. Verified the source raises exactly that body. |
| 9 | re-rv-3238-tests (Low): non-strict MFA test only sends the accepted token, so a verify bypass would still pass | Low | FIXED AND TESTED | Added bad-token dev test expecting 403. |
| 10 | re-rv-3238-tests (Low): role-change mock returns the caller role no matter what SQL was compiled | Low | NOT FIXED, listed | Test-harness fidelity improvement, not a product bug; the branch is still proven by `test_member_cannot_promote_to_owner`. Left to avoid reworking the shared mock helper. |
| 11 | re-rv-3238-correct/tenant open point: last-Owner check keys off the exact name "Owner", not rank | Medium (residual) | PARTIALLY MITIGATED, listed | After fix 3, only Owner-tier callers (or sysadmin) can move an Owner at all, and name-"Owner" demotions keep the last-Owner backstop. Demoting a custom Owner-tier role by a peer Owner still skips that backstop. Conditional on such rows existing; needs Christopher decision. |
| 12 | re-rv-3238-blast (Low), re-rv-3238-correct (Low: none), re-rv-3238-ops (Low), re-rv-3238-security (Low), re-rv-3238-security checked items | Low | NOT FIXED, listed | Dead-dependency gates with no production caller, readiness-vs-503 note (no code change required per ops report), non-strict MFA skip on mislabeled env (attacker cannot set the var). No action. |
| 13 | Tenant-scope gate failure (lead-security items 10 to 13) and the 7 xfail cross-tenant leaks (lead-security item 9, PR 3237) | High | OUT OF SCOPE, not fixed | Task order assigns these to other workers. Noted only. |

## Test commands and results (all through ~/metacode/fleet/heavy)

1. `~/metacode/fleet/heavy .venv/bin/pytest services/shared/tests/test_permissions.py services/admin/tests/test_audit_medium_mfa_suspended_tier.py services/admin/tests/test_user_routes.py services/admin/tests/test_invite_audit_chain_guard_2857.py services/admin/tests/test_auth_cluster_hardening.py -q -p no:cacheprovider`
   Result: 81 passed (72 dots on the first line at 88 percent, 9 more on the second line, zero failures).
2. Without-fix confirmation: the five new tests were run with the source fixes temporarily reverted by hand (no git commands): `test_role_rank_treats_super_admin_as_owner_tier`, `test_can_invite_role_denies_super_admin_target_to_mid_rank`, `test_grant_owner_hatch_ignored_for_membership_rewrites`, `TestRoleChangeTierCheck::test_grant_owner_hatch_does_not_promote_via_role_route`, `TestRoleChangeTierCheck::test_admin_cannot_demote_other_owner`. Result: all 5 FAILED on old code (the two route tests showed "DID NOT RAISE HTTPException"), all other tests in those files passed. Fixes were then re-applied by hand and the full run in step 1 passed.
3. `~/metacode/fleet/heavy .venv/bin/pytest services/shared/tests/test_auth_1338.py services/admin/tests/test_audit_medium_mfa_suspended_tier.py -q -p no:cacheprovider`
   Result: 61 passed, zero failures.
4. `~/metacode/fleet/heavy .venv/bin/ruff check services/shared/permissions.py services/admin/app/user_routes.py services/shared/tests/test_permissions.py services/admin/tests/test_audit_medium_mfa_suspended_tier.py`
   Result: All checks passed.
5. `ruff format --check` on the same files: my added lines are format-clean. Pre-existing hunks in `services/admin/app/user_routes.py` (the `target_role` tenant check) and `test_audit_medium_mfa_suspended_tier.py` (mock helpers) were already non-conformant at HEAD and were left untouched to keep the diff surgical.
6. `scripts/security/scan_tenant_scope.py`: not run. No queries were added or changed (the `user_routes.py` edit only adds rank comparisons over already loaded rows), so the gate condition in the task order does not apply.

## Items needing Christopher decision

1. Should unknown custom role names keep rank 0 (current fail-closed default, finding 6), or rank by permission coverage? Changing it weakens the guard for unrecognized roles.
2. Should the last-Owner backstop key off rank instead of the exact name "Owner" (finding 11), covering custom Owner-tier roles?
3. Is a valid Fernet `MFA_ENCRYPTION_KEY` already set on Railway production and staging (finding 5)? The repo cannot answer this; confirm before the next strict deploy, and do not rotate over existing MFA ciphertext.
4. Confirm tenant rows that must keep API access use only `active` or `trial` status (context from the out-of-scope suspended-tenant work).
