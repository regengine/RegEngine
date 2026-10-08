# FIX-REPORT: PR #3251 findings (merge cd1f37787)

Scope: confirmed CONCERN and BLOCKER findings for PR #3251 from the six
re-rv-3251-<angle> reports plus the angle and area leads that mention #3251.
No critical was reported for #3251 by any reviewer. Out of scope items named
in the task (suspended tenant deny on live auth, tenant scope gate failure,
7 xfail cross tenant leaks) were not touched.

## Findings

| # | Source report | Severity | Status | Reason |
|---|---------------|----------|--------|--------|
| 1 | re-rv-3251-tests, re-rv-3251-correct, re-rv-lead-tests (high 12), re-rv-lead-correct, re-rv-area-data | High | FIXED AND TESTED | `_QA_TENANT` was `"qa-gap-tenant"` but both snapshot routes type the path as UUID, so FastAPI returned 422 before the handler ran and strict xfail swallowed it. Changed to a generated UUID string. |
| 2 | re-rv-3251-tests (medium), re-rv-lead-tests (starred medium) | Medium | FIXED AND TESTED | `test_known_checklist_without_scope_is_noop` asserted only 200 and `valid is True`, so it could not pin the known id branch. Now asserts full body equality with the no id request plus `rules_evaluated == 0`. |
| 3 | re-rv-3251-correct (medium), re-rv-3251-security open question, re-rv-area-data open question | Medium | FIXED AND TESTED | `refreeze_snapshot` copied stored name and reason into a new sealed row with no seal check, so a tampered row was re sealed under a fresh valid hash. Added the same 409 guard `attest_snapshot` uses. Removed the now passing xfail marker. |
| 4 | re-rv-3251-correct (low), re-rv-lead-correct (low) | Low | BLOCKED | Duplicate POST creating two rows is ordinary POST behavior. `SnapshotCreateRequest` has no idempotency field, and no reviewer found a client contract promising one. Left as a strict xfail tripwire. Needs Christopher's decision (see below). |
| 5 | re-rv-3251-correct (low) | Low | BLOCKED | Gap fixture omits `fsma.compliance_alerts`. Verified create still returns 201 through the fail closed NOT CAPTURED path, so the tripwire is valid as is. Adding the table is optional hardening, not needed for the finding. |
| 6 | re-rv-3251-security open questions | Low | NOTED, no change | `POST /validate` with `config` omitted returns `valid: true, rules_evaluated: 0`. Pre existing behavior, now pinned by the strengthened noop test. Any change to that contract needs Christopher's decision. |

## Test commands and results

All run from `services/compliance/` through `~/metacode/fleet/heavy`:

1. `../../.venv/bin/python -m pytest tests/test_qa_deep_compliance_gaps.py tests/test_snapshots_router.py --no-cov -p no:randomly`
   Result: `74 passed, 1 xfailed in 3.18s`. The 1 xfail is finding 4, the
   duplicate POST tripwire, which fails on its stated assertion.
2. `../../.venv/bin/python -m pytest tests/test_validation_engine.py --no-cov -p no:randomly`
   Result: `20 passed in 0.85s` (adjacent validate path regression check).
3. `../../.venv/bin/ruff check app/snapshots.py tests/test_qa_deep_compliance_gaps.py`
   Result: `All checks passed!`
4. `scripts/security/scan_tenant_scope.py` was not run: no queries were
   touched. The new guard is a Python level check before any SQL, and every
   query still filters on `ctx.tenant_id`.

## How each fix was proven to fail without it

- Finding 1: a scratch probe POSTing to `/v1/compliance/snapshots/qa-gap-tenant`
  returned `422` with `uuid_parsing` at path `tenant_id`. After the fix,
  `--runxfail -k retry_of_create` shows two `201 Created` responses and the
  test fails on the duplicate row count assertion, proving the tripwire now
  tests the real behavior. (Probe script kept in /tmp during the run, since
  removed.)
- Finding 2: a temporary mutation making the config omitted branch return
  `rules_evaluated=3` when `checklist_id` is present made the strengthened test
  FAIL, while the old assertions (200 plus `valid is True`) would have passed
  it. Mutation reverted; `git diff` confirms `routes.py` is untouched.
- Finding 3: with the new guard temporarily removed, the unmarked
  `test_refreeze_of_tampered_snapshot_is_rejected` FAILED because refreeze
  returned `200 OK` and re sealed the forged name. With the guard restored,
  refreeze returns 409 and the test passes.

## Needs Christopher's decision

1. Is duplicate POST idempotency a real contract? If yes, the fix is an
   idempotency key on `SnapshotCreateRequest` plus a uniqueness rule, and the
   remaining xfail becomes a passing test. If no, the xfail should be removed
   or rewritten as a documenting test that two rows are the expected outcome.
   I changed neither behavior nor that marker.
2. Is `POST /validate` with no `config` returning `valid: true` acceptable, or
   should a request that evaluates zero rules fail closed? The strengthened
   test now pins the current contract, so either choice is a deliberate
   follow up.
