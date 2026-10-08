# Break Report: services/admin auth and invite/role routes

## Summary

Probed invite creation and acceptance, role assignment guards, session and
challenge auth paths, and token generation, using local SQLite harnesses and
unit probes only. Found 5 breaks, fixed and tested all 5. No fixes are failing.
No live endpoints were touched, no Postgres throwaway database was needed
(SQLite harnesses sufficed), no migrations were added, and the suspended
tenant and 3225 areas were not reworked. Token entropy was checked and is not
broken: invites, session tokens, and WebAuthn challenges all use
256 bit secrets, OTPs are 6 digit codes stored as keyed HMAC digests with a
5 attempt lockout, and invite tokens are SHA-256 hashed at rest.

Severity counts: 1 high, 2 medium, 2 low.

## Finding 1 (high): case-variant emails bypass invite duplicate guards

What broke: POST /admin/invites compared the requested address with exact
string equality when checking for an existing member and for a pending
invite. Inviting ADMIN@EXAMPLE.COM while admin@example.com was already a
member returned 200 and issued a live invite instead of 409. Inviting
user@EXAMPLE.com while User@example.com had a pending invite returned 200 a
second time, leaving two usable tokens for one mailbox. Every downstream
consumer (accept_invite lookup, ensure_passwordless_identity, challenge
creation) matches case-insensitively, so the create path disagreed with the
rest of the system about what counts as the same mailbox.

How to reproduce: mount invite_routes with stubbed auth on SQLite, create a
member admin@example.com, then POST /admin/invites with
{"email": "ADMIN@EXAMPLE.COM", ...}. Pre-fix: 200 with an invite body.

Root cause: services/admin/app/invite_routes.py, InviteCreate.validate_email
(stored the raw address) and the two existence queries in create_invite
(exact == comparisons).

Fix: the validator now strips and lowercases the address before validation
and storage, both existence checks compare with func.lower so legacy
mixed-case rows are still caught, and accept Path A stores the normalized
address for newly created users.

Test results: 4 new tests in
services/admin/tests/test_invite_break_adversarial_2026.py
(TestCaseVariantInvites plus test_accept_stores_normalized_user_email). All
fail on pre-fix code (returned 200 or stored raw case) and pass now. File: 11
passed.

## Finding 2 (medium): concurrent or repeated invite writes return 500

What broke: two simultaneous creates for the same mailbox both pass the
pre-checks, then the loser hits the unique index and raises an unhandled
IntegrityError, which becomes a 500. Re-inviting after a revoke does the
same on backends whose unique index covers revoked rows (SQLite renders the
partial index as a full unique index; Postgres excludes revoked rows, so prod
accepts the re-invite, but the concurrent race still 500s there).

How to reproduce: create an invite, revoke it, re-invite the same address on
SQLite. Pre-fix: 500 Internal Server Error.

Root cause: services/admin/app/invite_routes.py, bare db.flush and db.commit
in create_invite with no IntegrityError handling.

Fix: both calls are wrapped. On IntegrityError the handler rolls back, logs
a warning with the masked email, and returns the same 409 the pre-checks
return, so concurrent outcomes are indistinguishable from sequential ones.

Test results: 3 new tests (flush conflict, commit conflict with nothing
persisted, re-invite after revoke). All fail pre-fix (500), pass now.

## Finding 3 (medium): concurrent invite accepts return 500

What broke: two simultaneous accepts of one token both pass the usability
checks, then the loser collides on the membership primary key and raises an
unhandled IntegrityError, which becomes a 500. The endpoint promises a
uniform 400 for every unusable-invite outcome, so the 500 also acts as a
state oracle.

How to reproduce: force the final commit in accept_invite to raise
IntegrityError once (simulates losing the race). Pre-fix: 500.

Root cause: services/admin/app/invite_routes.py, bare db.commit at the end
of accept_invite.

Fix: wrapped in try/except IntegrityError. On conflict the handler rolls
back, logs a warning, and raises the standard uniform 400.

Test results: 1 new test (test_accept_commit_conflict_returns_uniform_400).
Fails pre-fix (500), passes now.

## Finding 4 (low): accept requires a name field it never reads

What broke: AcceptInviteRequest declared name as required, but the handler
only ever reads token. Token-only clients get a 422 for omitting a field
that has zero effect.

How to reproduce: POST /auth/accept-invite with {"token": "<valid>"} and no
name. Pre-fix: 422 Field required.

Root cause: services/admin/app/invite_routes.py, AcceptInviteRequest.name
with no default and no reader.

Fix: name is now optional (str or None, default None). Fully backward
compatible: clients that send it see no change.

Test results: 1 new test (test_accept_without_name_succeeds, full 201 accept
through real identity provisioning). Fails pre-fix (422), passes now.

## Finding 5 (low): grant_owner docstring overclaims its scope

What broke: can_invite_role's docstring said users.invite.grant_owner is an
escape hatch for both the Owner-tier check and the basic tier check. The code
honors it for Owner-tier targets only. A reader following the docstring would
believe a low-rank holder of the permission can assign any sub-Owner role
above their tier, which the code (correctly) denies.

How to reproduce: can_invite_role("manager", ["users.invite.grant_owner"],
"admin", []) returns False, contradicting the old docstring.

Root cause: services/shared/permissions.py, can_invite_role docstring.

Fix: docstring corrected to state the permission applies to Owner-tier
targets only and never lifts the basic tier check. Code unchanged, least
privilege preserved. A unit test pins the behavior both ways (manager with
grant cannot invite admin; admin with grant can invite owner).

Test results: 1 new test. It passes both before and after (behavior pin, not
a behavior change), which is expected and noted honestly.

## Areas checked with no break found

* Token entropy: invite tokens, opaque session tokens, and WebAuthn
  challenges use secrets.token_urlsafe(32). OTPs are HMAC-SHA256 digests
  bound to challenge, purpose, and email fingerprint, with constant-time
  verify and a 5 attempt lockout. No change.
* Role escalation on update_user_role and create_invite: the #1387
  can_invite_role guard is present on both, wildcard-permission roles rank
  at Owner tier, cross-tenant roles are rejected as unknown, and the last
  Owner guard covers demotion and deactivation races. No new break found.
* Challenge verify: browser binding required, uniform 401s, session and
  refresh hashes stored hashed. Refresh rotation uses atomic claim with
  reuse tombstones and family revocation. Session revoke is user-scoped
  (404 on a session owned by someone else). No change.
* No role-creation route exists in app code, so trojan custom roles cannot
  be minted through these routes.

## Verification commands and results

* New file: services/admin/tests/test_invite_break_adversarial_2026.py,
  11 passed.
* Fail-before proof: with HEAD's invite_routes.py temporarily in place, 10
  of 11 new tests fail (the grant_owner pin passes on both, as documented);
  with the fix restored, 11 of 11 pass.
* Neighbors: test_invite_audit_chain_guard_2857, test_accept_invite_rls_2899,
  test_invite_routes_email, test_user_routes, test_user_routes_1342,
  test_user_routes_last_owner_2906, 47 passed.
* services/shared/tests/test_permissions.py: 3 passed (full shared suite has
  one unrelated pre-existing failure in test_extract_document_script about
  stderr routing, which does not import permissions).
* ruff check on all touched files: passed. ruff format: new test file
  clean; invite_routes.py was already non-format-clean at HEAD and was left
  that way to keep the diff surgical.

## Open questions

1. Re-invite after revoke still diverges by backend: Postgres returns 201
   (partial index excludes revoked rows) while SQLite returns the new
   handled 409 (full unique index). Christopher should decide whether to
   accept the divergence (SQLite is dev and test only) or align SQLite with
   a matching partial index in test setup.
2. The invite email regex still accepts technically invalid forms such as
   consecutive dots in the domain. Delivery simply fails for those. Tighten
   only if bounce noise becomes a problem, since stricter rules risk
   rejecting rare but valid addresses.
3. deactivate_user, reactivate_user, and revoke_invite have no tier-rank
   check of the #1387 kind (deactivate needs users.disable, the others need
   users.manage_roles or users.invite). A subordinate holding those
   permissions can deactivate an Owner (last-Owner guard aside) or
   reactivate a dormant non-sysadmin Owner. This matches the current
   permission design, so no change was made, but Christopher may want to
   confirm that is intended.
