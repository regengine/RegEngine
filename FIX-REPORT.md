# FIX-REPORT: PR #3219 GDPR erasure follow-ups

All six re-rv-3219 angles plus the lead and area summaries that mention
#3219 were read. Every finding below was confirmed in code before fixing.
Out of scope items from the brief (suspended-tenant deny on live auth,
tenant-scope gate failure, 7 xfail cross-tenant leaks) are noted at the
end and were not touched.

| # | Source report | Severity | Finding | Status |
|---|---|---|---|---|
| 1 | re-rv-3219-blast, re-rv-3219-correct (Med 2), re-rv-lead-blast (High) | High | `test_request_erasure_cannot_mutate_another_identity` expects 3 outbox rows with params exactly `{user_id}`, but erasure now writes 6 rows (delete plus anonymize per marker tenant) | FIXED AND TESTED |
| 2 | re-rv-3219-blast (Med), re-rv-lead-ops (Med) | Medium | `ON CONFLICT DO NOTHING` keeps a still-pending pre-fix delete row with the old actor_id-matching Cypher, so the drainer could still delete shared records | FIXED AND TESTED |
| 3 | re-rv-3219-correct (Med 1), re-rv-3219-security (Med 1), re-rv-lead-security 3219b | Medium | Identity node keyed only by `actor_id` is neither deleted nor anonymized, raw id stays | FIXED AND TESTED |
| 4 | re-rv-3219-security (Med 2), re-rv-lead-security 3219c, re-rv-3219-correct (Low 1) | Medium | `PendingSupplierInvite.email`, `created_by`, `accepted_by` survive erasure | FIXED AND TESTED |
| 5 | re-rv-3219-security (High), re-rv-lead-security 3219 | High | Erasure token is a deterministic unsalted hash stored beside the raw user id, rejoinable by outbox readers; params never cleared after drain | FIXED AND TESTED (see notes) |
| 6 | re-rv-3219-tests (Med 1), re-rv-lead-tests 3219 | Medium | Graph-outcome tests reimplement Cypher in Python and stay green on query regression | FIXED AND TESTED |
| 7 | re-rv-3219-tests (Med 2), re-rv-lead-tests 3219 | Medium | Anonymize tests never assert the SET property rewrite | FIXED AND TESTED |
| 8 | re-rv-3219-blast (Low) | Low | `DISASTER_RECOVERY.md` says erasure deletes a user's graph nodes | FIXED (trivial doc edit, no test) |
| 9 | re-rv-3219-correct (Low 2) | Low | `request_erasure` comment describes a single DETACH DELETE | FIXED (trivial comment edit, no test) |
| 10 | re-rv-3219-security (Low) | Low | Delete plus anonymize run as two auto-committed statements with swallow-and-return-accepted on error | Listed, not fixed (reason below) |

## What changed per finding

1. `tests/security/test_account_erasure_identity_isolation_pg.py`: expects
   6 rows, 3 delete rows with params exactly `{user_id}` plus 3 anonymize
   rows with `{user_id, erased_actor_id}`, user B absence check kept.
2. `services/admin/app/erasure_routes.py` (`_apply_account_erasure`): after
   each delete enqueue, any still-pending row under the same dedupe key gets
   its Cypher refreshed to the fixed statement. Drained rows untouched.
3. `_CYPHER_DELETE_IDENTITY_NODES`: delete now also matches
   `n.actor_id = $user_id`, still gated on the identity label filter, so
   shared records are never matched.
4. `_CYPHER_ANONYMIZE_SHARED_ACTOR_REFS`: WHERE also matches `created_by`
   and `accepted_by`; SET rewrites all four actor fields to the token and
   drops `email` on `PendingSupplierInvite` nodes the erased user accepted
   (their own address; NULL removes the property in Neo4j).
5. `_erased_actor_token`: HMAC-SHA256 under `ERASURE_TOKEN_SECRET` (fallback
   `AUTH_SECRET_KEY`) when set, plain sha256 fallback otherwise.
   `GraphOutboxDrainer._mark_drained` clears `params` to `{}` on drained
   `user_erasure` rows; failed rows keep params for retry.
6. `_apply_fixed_semantics` in `test_gdpr_erasure_graph_scope.py` now reads
   its predicates from the real query text, and two new outcome tests cover
   the actor_id-keyed identity node and invite bookkeeping.
7. SET-clause assertions (`SET`, `m.actor_id`, `m.user_id`,
   `THEN $erased_actor_id`) added in both `test_gdpr_erasure_graph_scope.py`
   and `test_gdpr_neo4j_erasure_1412.py`.
8. `docs/operations/DISASTER_RECOVERY.md`: erasure deletes identity nodes
   and rewrites actor references on other nodes.
9. `request_erasure` comment now describes the two-step delete plus
   anonymize flow.
10. Not fixed: the two-statement best-effort immediate path predates this
    PR; making it one explicit Neo4j transaction would rework the driver
    interaction and its mocks for a best-effort path whose durability
    guarantee is the outbox. Listed for a later change.

## Test commands and results

All run through `~/metacode/fleet/heavy`:

- `.venv/bin/python -m pytest services/admin/tests/test_gdpr_erasure_graph_scope.py services/admin/tests/test_gdpr_neo4j_erasure_1412.py services/admin/tests/test_graph_outbox.py services/admin/tests/test_erasure_hardening.py -q`
  Pass: 40 passed.
- `pytest tests/security/test_account_erasure_identity_isolation_pg.py -q --no-cov -o testpaths=tests`
  against a throwaway `fleet_3219` database migrated with
  `scripts/run-migrations.sh` (roles mirroring backend-ci, database dropped
  afterwards). Pass: 1 passed.
- `.venv/bin/python scripts/security/scan_tenant_scope.py`: flags only the
  two known out-of-scope `traceability_linker.py` sites (PR #3220); zero
  mentions of `erasure_routes` or `graph_outbox`.
- `.venv/bin/ruff check` on all six touched Python files: all checks passed.
- Full `services/admin/tests/` suite: only 3 failures, all in
  `test_audit_medium_mfa_suspended_tier.py` (strict-startup error ordering
  for `MFA_ENCRYPTION_KEY`, a different PR surface; that file never imports
  erasure or outbox code). Pre-existing, unrelated.

Fail-without-fix confirmation (each new or updated test was run against
the reverted code and failed, then passed after restore):

- Updated pg test with the anonymize enqueue disabled: FAILED (3 rows, not
  6); with fix: passed.
- `test_delete_query_targets_only_identity_nodes`,
  `test_anonymize_query_preserves_records_and_rewrites_actor`,
  `test_erasure_refreshes_stale_pending_delete_row`,
  `test_erased_actor_token_uses_configured_secret`,
  `test_drainer_redacts_erasure_params_on_success`: all FAILED on reverted
  code, pass with fix.
- `test_identity_node_keyed_only_by_actor_id_is_deleted` and
  `test_invite_bookkeeping_fields_are_anonymized`: FAILED on regressed
  queries (missing actor_id match, missing created_by SET), pass with fix.
- PG redaction probe (`/tmp/fleet3219_redact_probe.py`, throwaway file):
  drained `user_erasure` row on real Postgres shows
  `status: drained params: {}`, proving the `SET params` typing works on
  JSONB.

## Needs Christopher's decision

1. Set `ERASURE_TOKEN_SECRET` (long random value, sealed) in production. Without
   it the token falls back to the plain hash, readable beside the user id
   until each row drains. `AUTH_SECRET_KEY` is already used as a fallback.
2. One-time production SQL for already-pending pre-fix delete rows (the code
   self-heals per user on their next erasure, but rows pending for users who
   never re-request still carry old Cypher until drained):
   refresh `graph_outbox` rows with `operation = 'user_erasure'` and
   `status = 'pending'` whose Cypher is not the fixed statement, and enqueue
   any missing `user_erasure_anonymize:` rows. Needs an ops call; I did not
   touch production.
3. Accepted gaps, by design: audit marker rows keep the raw `actor_id`
   (tamper-evident trail); pending invites addressed to the erased user's
   old email keep that address (joining it would require storing the old
   email in the outbox); other marker tenants update on drain, not in the
   request.
4. The 3 MFA strict-startup failures above belong to whoever owns that
   surface, not this fix.
5. Out of scope, untouched as briefed: suspended-tenant deny on live auth,
   tenant-scope gate failure (`traceability_linker.py`, PR #3220 owns it),
   7 xfail cross-tenant leaks.
