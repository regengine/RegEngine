# Break report: ingestion disaster recovery and chain verification

Summary: 5 breaks found, 5 fixed and tested, 0 fixed but failing, 0 blocked.

Local checks only. Nothing was deployed, and no production database was used.

## High: a missing hash crashed verification instead of marking the chain invalid

What broke. `verify_chain` sliced a missing previous hash or chain hash. That raised TypeError. The chain verification job then stored status failed and left chain_valid empty, so a corrupt chain was not reported as invalid.

How to reproduce. Build a two-row chain whose second previous hash is null, or a genesis row whose chain hash is null, with a matching event id so the row is not an orphan. Call the legacy verifier, or run the verification job over that chain.

Root cause. `services/shared/cte_persistence/verification.py:151` and `:160` (the slices). An unreadable sequence on an orphan row could also wipe the errors already collected (`:170`).

Fix. `_short_hash` (`:23`) returns `missing` for an empty or non-text value and otherwise returns the first 16 characters. The chain-break and tamper messages keep their existing wording. An orphan sequence that cannot be read is recorded as its own error and the other errors stay.

Test results. `test_null_previous_hash_is_reported_invalid_not_raised`, `test_null_chain_hash_blob_is_reported_invalid_not_raised`, and `test_verification_job_completes_invalid_when_previous_hash_is_missing` in `services/ingestion/tests/test_dr_chain_break_it.py`. Before the fix those tests raised TypeError or left the job failed. After the fix they pass, and the job completes with chain_valid false.

## High: a truncated KDE blob crashed the canonical verifier

What broke. `json.loads` on a truncated blob (`{`), a JSON list, or a number raised out of `verify_chain_canonical`. The same job then recorded a crash instead of an invalid chain.

How to reproduce. One canonical chain row whose KDE column is `{`, `[1, 2]`, or `5`. Call `verify_chain_canonical`.

Root cause. `services/shared/canonical_persistence/verification.py` read the KDE column and decoded it with no guard (call site now `:337`).

Fix. `_kdes_object` (`:162`) accepts null (empty object), a dict, or a JSON object string, including UTF-8 bytes. Anything else raises ValueError. The walk records `Unreadable KDE blob at seq=...` and continues. Valid object blobs still recompute. The EPCIS rule that events without a chain row do not flip valid is unchanged.

Test results. `test_unreadable_kde_blob_is_invalid_not_raised` (three payloads). Before the fix: JSONDecodeError or TypeError. After the fix: valid is false and the unreadable message is present. `tests/shared/test_canonical_verify_chain_2506.py` still passes, so a normal object blob is unchanged.

## High: readiness said the chain was intact when the hashes or the sequence were wrong

What broke. The readiness SQL only counted rows with a null previous hash and a sequence above 1. A flipped chain hash, a previous hash that points at the wrong row, or a hole left by removing a middle row (sequences 1 then 3) all came back as intact.

How to reproduce. Insert linked rows for sequences 1 and 3, or one row whose stored chain hash is not the recomputed hash. Call `_check_hash_chain_integrity`.

Root cause. `services/ingestion/app/disaster_recovery.py` `_check_hash_chain_integrity` (now `:141`). The old statement never selected `chain_hash` and never recomputed it.

Fix. The check loads `sequence_num, event_hash, previous_chain_hash, chain_hash` in sequence order and walks them in `_chain_row_is_broken` (`:111`). A row is one gap when the sequence is not its position starting at 1, a hash is missing, genesis has a previous hash, the stored previous hash does not match the prior row, or `compute_chain_hash` does not match the stored chain hash. The pass and gap sentences are unchanged. A database error is still a warning.

Test results. Unit: `test_sequence_hole_after_truncate_fails_the_dr_check`, `test_corrupt_chain_hash_fails_the_dr_check`, `test_chain_statement_walks_row_hashes`. Updated cases in `test_disaster_recovery_1342.py`. Live SQL: six hash-chain tests in `test_disaster_recovery_readiness_pg.py` passed on a throwaway local database (see Tests below). The default cluster on port 55432 was down, so that file skips there.

## High: an emptied chain with events still on file was only a warning

What broke. Zero hash-chain rows produced the warning "No hash chain records found for tenant" even when non-rejected traceability events remained. Readiness could stay ready after a truncate of the chain.

How to reproduce. Leave `fsma.traceability_events` rows for the tenant with status other than rejected, and delete or never write `fsma.hash_chain` rows. Call the hash-chain check or `test-recovery`.

Root cause. `services/ingestion/app/disaster_recovery.py:165` (the empty-chain branch). It used to return the warning without looking at events.

Fix. When the chain query returns no rows, count `fsma.traceability_events` for that tenant where status is not rejected. A count above zero fails with `Hash chain is missing while N event(s) exist`. A count of zero keeps the old warning, so a tenant with no data stays a warning. The count is filtered by tenant.

Test results. `test_truncated_chain_with_events_fails` and `test_truncated_chain_recovery_is_not_ready` failed before the fix (status warn). `test_empty_chain_without_events_stays_a_warning` passed before and after. Live: `test_truncated_chain_with_remaining_events_fails` passed on the throwaway database, including a second tenant whose event must not be counted.

## Medium: the recovery test said the chain could be rebuilt when it could not be read

What broke. Every hash-chain warning, including a database error, was turned into a pass: the chain can be rebuilt from event data.

How to reproduce. Make the hash-chain query raise a database error during `POST /api/v1/dr/{tenant}/test-recovery`.

Root cause. `services/ingestion/app/disaster_recovery.py` `test_recovery` (rebuild block now `:533`).

Fix. A failed chain that is missing while events exist still says the chain can be rebuilt, because those events remain. Any other failure says a rebuild may not be possible. A warning that is not the empty-tenant warning says the chain could not be read, so rebuild feasibility is unknown. A real pass, or the empty-tenant warning, still says the chain can be rebuilt. Overall scoring is unchanged: two warnings can still score ready.

Test results. `test_unreadable_chain_does_not_claim_rebuild_is_possible` expected a warning and got a pass before the fix. It passes after the fix.

## Tests

Before the fix, this session ran:

`~/metacode/fleet/heavy .venv/bin/pytest services/ingestion/tests/test_dr_chain_break_it.py --tb=line`

Result: 12 failed, 1 passed in 0.72s. The one pass was the empty tenant with no events, which must stay a warning. Failures were TypeError on a null hash, JSON errors on a bad KDE blob, a verification job left failed, ValueError from the old aggregate row shape, the old SQL text, a truncated chain left as a warning, and a rebuild pass when the chain could not be read. The fix was already in the tree after that run. Git restore is not allowed here, so that before-fix run was not repeated.

After the fix:

`~/metacode/fleet/heavy .venv/bin/pytest services/ingestion/tests/test_dr_chain_break_it.py services/ingestion/tests/test_disaster_recovery_1342.py services/ingestion/tests/test_disaster_recovery_readiness_pg.py tests/shared/test_canonical_verify_chain_2506.py tests/shared/test_cte_persistence_verify_chain_1314.py tests/invariants/test_chain_verify_golden.py --tb=short -x`

Result: 108 passed, 15 skipped in 2.16s. The readiness file skipped because nothing is listening on localhost:55432. The golden file skipped because Docker is not available.

Earlier in this session, after the code change and before a small import-order edit:

`~/metacode/fleet/heavy .venv/bin/pytest services/ingestion/tests/test_dr_chain_break_it.py services/ingestion/tests/test_disaster_recovery_1342.py services/ingestion/tests/test_chain_verification_job_1342.py services/ingestion/tests/test_chain_verification_combine_2506.py tests/shared/test_cte_persistence_verify_chain_1314.py --tb=short`

Result: 121 passed in 2.27s.

Live SQL, throwaway database `fleet_brk_re_ingestion_dr` on the local server (socket `/tmp`, port 5432), created for this run and dropped after it. Schema was only `fsma.hash_chain` (no foreign key, matching the later drop of that constraint), `fsma.traceability_events`, and empty stand-in tables so the file's schema check would run. No alembic upgrade. No database URL from a `.env` file.

`REMEDIATION_TEST_SUPERUSER_DSN=postgresql://sellers@/fleet_brk_re_ingestion_dr?host=/tmp ~/metacode/fleet/heavy .venv/bin/pytest services/ingestion/tests/test_disaster_recovery_readiness_pg.py -k 'hash_chain or recomputed or sequence_hole or truncated_chain' --tb=short`

Result: 6 passed, 5 deselected in 0.69s. A follow-up query showed the database was gone.

Ruff, on the six touched Python files:

`.venv/bin/ruff check` and `.venv/bin/ruff format --check`

Result: all checks passed, 6 files already formatted.

## Open questions

An unreadable chain is a warning, and the new rebuild result is a second warning. Two warnings still score overall ready. A corrupt chain or a truncated chain with events is a failure, which scores at risk under the existing rule. Changing the ready threshold needs a product decision. It was left as it is.

Verification jobs are stored in process memory and are not evicted. That was not changed.

Disaster recovery does not check that an evidence attachment file exists in object storage. "Missing blob" in this pass means a missing hash value or a KDE value that is not a JSON object. No network or object-storage call was added.

This session is already a Muse Code instance, so a nested Muse review was not started. The fleet order also allows network only for package installs.
