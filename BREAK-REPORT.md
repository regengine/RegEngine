# Break report: admin audit integrity, routes, and middleware

## Summary

Breaks found: 7
Fixed and tested: 7
Fixed but failing: 0
Blocked: 0

Local SQLite tests only. No production URL, no production database, no migration.

## High: missing or short privacy salt still masks in production

What broke: Audit export masking hashed emails with a process-local salt whenever REGENGINE_ENV was not the exact string production. A surrounding space, a salt shorter than 16 characters, or production set only on ENV, ENVIRONMENT, RAILWAY_ENVIRONMENT, RAILWAY_ENVIRONMENT_NAME, or VERCEL_ENV all kept masking. A guessable salt lets someone undo a masked email.

How to reproduce: Unset AUDIT_PII_HASH_SALT. Set one of those six names to " production " (spaces included) and call the salt helper. Or set REGENGINE_ENV=production and AUDIT_PII_HASH_SALT=short, then mask an email. Before the fix, neither case raised.

Root cause: services/admin/app/audit_routes.py, the old salt helper compared os.getenv("REGENGINE_ENV", "").lower() to production with no strip and no minimum length. The replacement is _runtime_is_production at line 111 and _pii_hash_salt at line 123.

Fix: If any of the six names strips to production and the stripped salt is shorter than 16 characters, raise RuntimeError. A non-empty salt outside production is still used. Development with no salt still uses the process salt.

Test results: test_missing_salt_fails_closed_for_each_production_signal and test_short_salt_fails_closed_in_production failed before the fix (RuntimeError was not raised). test_development_still_masks_without_a_configured_salt passed before the fix and still passes. They pass after the fix. See the command block at the end.

## High: a clean export looked tampered, and a rewritten actor looked the same

What broke: Export verification hashed the public file: masked email, nested severity, redacted metadata, and a SQLite timestamp that had lost its UTC offset. A clean chain reported integrity_hash_mismatch. Changing actor_email produced the same failure, so the tamper was not a distinct result.

How to reproduce: Log one audit row, export with include_verification, and read chain_verification.valid. Before the fix it was false on an untouched row. Then set actor_email to another address and export again. Both reports failed the same way.

Root cause: services/admin/app/audit_routes.py used to call verify_chain on the public entries. Verification now builds a stored-field row in _canonical_verification_entry at line 186 and calls verify_chain at line 674. Timestamp normalization is chain_timestamp in services/admin/app/audit_integrity.py at line 15.

Fix: Verification uses the stored actor email, top-level severity, endpoint, metadata, and a UTC timestamp. The downloaded entries stay redacted. Formula neutralization is applied only to the public file, at line 579, so the hash input is unchanged.

Test results: test_clean_export_verifies_and_tampered_actor_does_not failed before the fix (valid was false on the clean export). It passes after the fix: the clean export is valid and contains no raw email, and the rewritten actor reports integrity_hash_mismatch.

## High: deleting the start of the chain still verified

What broke: The first row in an export was trusted as the start of the chain. After the first row was deleted, the remaining rows still linked to each other, so a missing prefix was not reported as a missing anchor. Before this fix the export was already invalid for the wrong reason (the redacted hash), so the missing prefix was hidden.

How to reproduce: Log three rows, delete the first, export with verification, and look for chain_anchor_missing. Before the fix that error was absent.

Root cause: services/admin/app/audit_integrity.py trusted the first row's prev_hash. The new branch is the anchored check at line 154 and the missing_anchor error at line 118. The export loads the previous row in _predecessor_row at line 217 and decides missing_anchor at line 667.

Fix: If the first exported sequence is not 1, load the previous stored row for that tenant and require the window to link to it. If no previous row exists, report chain_anchor_missing. A later time window whose parent row is still stored stays valid. Rows further back than the immediate parent are not scanned, and the parent's own content hash is not recomputed.

Test results: test_deleted_chain_prefix_does_not_verify failed before the fix because chain_anchor_missing was missing. It passes after the fix. test_time_window_keeps_the_parent_link was added with the fix, so it was not in the pre-fix failure run. It passes: a window that starts at the second row stays valid and does not include the first action.

## High: spreadsheet formulas left the export unchanged

What broke: Action, endpoint, and metadata text that starts with =, +, -, @, tab, or carriage return was copied into the JSON export. Opening or converting that file in Excel can run the formula.

How to reproduce: Log an action of =cmd|'/c calc'!A0, an endpoint of +1-415-555-0100, and metadata with the same formula plus a normal value. Export. Before the fix the action was still the raw formula.

Root cause: services/admin/app/audit_routes.py had no neutralization on the public entry. The helper is _neutralize_formula at line 154, applied through _neutralize_export_entry at line 178 and the append at line 579.

Fix: Prefix one single quote on those display strings, including nested metadata keys and values. The integrity block and the verification input stay raw, so a neutralized export still verifies.

Test results: test_export_neutralizes_spreadsheet_formulas failed before the fix (the action compared equal to the raw formula). It passes after the fix: formula fields gain a leading quote, the safe value is unchanged, and chain_verification.valid is true.

## Medium: a malformed chain row crashed verification

What broke: verify_chain assumed event, resource, integrity, and metadata were dictionaries. A null block, a string, or a non-object entry raised AttributeError. One bad row could take down the whole check.

How to reproduce: Call verify_chain with event set to null, resource set to null, integrity set to null, event set to the string "login", or the entry itself set to a string. Before the fix each case raised AttributeError.

Root cause: services/admin/app/audit_integrity.py called .get on those blocks. The guard is the non-dict entry branch at line 128 and _as_dict at line 31, used at line 136.

Fix: A non-object entry or a non-object block is recorded as malformed_entry and valid is false. Hashing continues with empty objects so the same row can also report a hash mismatch. An empty integrity object is still only a hash mismatch, which existing tests already expect.

Test results: test_verify_chain_malformed_entry_is_invalid_without_raising failed before the fix with AttributeError. It passes after the fix: valid is false, errors is non-empty, and verified stays between zero and the row count.

## Medium: a hostile request id and user agent were stored as audit evidence

What broke: Audit context copied request.state.request_id and the User-Agent header as sent. A value with a carriage return and line feed, or a very long agent string, could land in the audit record. The response header path in RequestIDMiddleware was left alone.

How to reproduce: Dispatch AuditContextMiddleware with request id legit followed by CR LF and "X-Admin: true", and a user agent of "Mozilla/5.0" plus CR LF, "X-Injected: 1", and 800 A's. Before the fix the request id was kept verbatim.

Root cause: services/admin/app/audit_middleware.py assigned the raw values in dispatch. The filters are _audit_request_id at line 58 and _audit_user_agent at line 66, used at lines 178 and 180.

Fix: A request id must match ^[A-Za-z0-9._:-]{1,128}$. Anything else is replaced with a new UUID. The user agent drops non-printable characters, which removes CR, LF, and tab, then keeps at most 512 characters.

Test results: test_audit_context_rejects_hostile_request_id_and_user_agent failed before the fix. It passes after the fix: the stored request id is replaced, has no CR or LF, and is at most 128 characters. The user agent has no CR or LF and is at most 512 characters. Existing middleware tests still pass, including reuse of a normal request id and the 512 character cap.

## Low: the verified count went negative

What broke: verified was the row count minus the number of error objects. One row can fail the link, the sequence, and the hash, so the count went below zero.

How to reproduce: Verify two rows where the second has a wrong previous hash, a wrong hash, and a sequence that skips ahead. Before the fix, with both rows also carrying a bad hash, the assertion saw verified == -2.

Root cause: services/admin/app/audit_integrity.py subtracted len(errors). The return is now line 223, using the set of broken indexes filled by fail at line 106.

Fix: Each broken row is counted once. verified is len(entries) minus the number of broken indexes.

Test results: The original fixture failed before the fix as -2 == 1, because both rows were broken. The fixture was then changed so the first row uses a real hash and stays valid. That tightened version was not re-run on the unfixed code. With the old counter, one clean row plus one row with three errors would report verified = 2 - 3 = -1. test_verified_count_does_not_go_negative_when_one_row_has_many_errors passes after the fix with verified == 1.

## Commands

Before the fix:

~/metacode/fleet/heavy .venv/bin/pytest services/admin/tests/test_audit_break_it.py --tb=line --no-header

17 failed, 1 passed in 0.56s. The one pass was the development salt fallback. The time-window test was not in this run.

After the fix:

~/metacode/fleet/heavy .venv/bin/pytest services/admin/tests/test_audit_break_it.py services/admin/tests/test_audit_integrity_1342.py services/admin/tests/test_audit_chain_sequence_2513.py services/admin/tests/test_epic_k_audit_hygiene.py services/admin/tests/test_audit_export_self_log_2522.py services/admin/tests/test_audit_middleware_1342.py services/admin/tests/test_admin_service_hardening.py tests/security/test_audit_integrity.py --tb=line --no-header

156 passed, 1 skipped, 3 warnings in 3.25s. The skip is the pre-existing SQLite listener no-op at test_admin_service_hardening.py:82. The three warnings are pre-existing SQLAlchemy transaction notices from the admin conftest.

~/metacode/fleet/heavy .venv/bin/ruff check services/admin/app/audit_integrity.py services/admin/app/audit_routes.py services/admin/app/audit_middleware.py services/admin/tests/test_audit_break_it.py

All checks passed.

## Open questions

The v1 hash fallback still accepts a row whose actor fields were rewritten and whose hash was downgraded to v1. That is the recorded behavior of issue 2523. It was not changed.

Actor IP and user agent are not inside the integrity hash. No new hash version was added.

A gap or a content change that sits strictly before the export window, and is not the immediate parent, is not detected. The parent row's stored hash and sequence seed the link. Its content is not rehashed. Scanning the whole prefix can be large.

RequestIDMiddleware still copies the raw X-Request-ID onto the response header. That file was not part of this change.

The metadata phone pattern can still redact a 10 digit lot code. That behavior is older than this task.

A negative export limit is still accepted by the query declaration. Postgres rejects LIMIT -1. SQLite may not. This was not one of the three named themes and was not changed.

Only an environment value that strips to production fails closed. Staging keeps the process salt. A production salt shorter than 16 characters will now fail the export. That is a behavior change for a deploy that set a short AUDIT_PII_HASH_SALT.

Postgres timestamptz round-trip was not run. The passing tests prove the SQLite naive datetime path, which is treated as UTC. On Postgres the column is timestamptz and an aware value keeps its offset. That last sentence is reasoned from the column type, not from a Postgres run.

The whole admin suite was not run. verify_chain's docstring still says entries are shaped like the export endpoint. Verification now uses the stored-field shape.
