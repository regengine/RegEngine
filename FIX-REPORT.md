# Fix report: PR #3217 audit-pack verifier

Worktree branch off origin/main e854dadc. Merge commit for PR #3217:
3db0bcd69803b96fe515689a5ffd0d358e682ac9.
Scope: `services/admin/scripts/verify_audit_pack.py` and its tests only.
No queries were touched, so `scripts/security/scan_tenant_scope.py` does
not apply. No migrations, no config, no network calls.

## Findings

| # | Source report | Severity | Status | Reason |
|---|---|---|---|---|
| 1 | re-rv-3217-correct REPORT.md Medium (zip extract aliases: `./`, `//`) | Medium | FIXED AND TESTED | `_is_safe_member` now rejects empty and `.` segments, so alias names fail closed before any hash check. Confirmed with a probe: an alias pack verified True before, False after. |
| 2 | re-rv-3217-correct REPORT.md Low (manifest `chain_length` bool) | Low | FIXED AND TESTED | Manifest `chain_length` must now be a non-bool int when present. Probe: `True` vs artifact `1` verified True before, False after. |
| 3 | re-rv-3217-security H1, confirmed narrowed by re-rv-area-data (SUCCESS banner over self-reported chain flags) | High | FIXED AND TESTED | Success banner now reads Bundle Consistency and states the persisted chain was not recomputed; docstring says the same. The chain itself is still not recomputed: there is no signature scheme and row replay is out of scope for this offline script. |
| 4 | re-rv-3217-security H2 (PARTIAL exits 0) | High (rejected) | BLOCKED | Area-data lead rejected this as a defect: PARTIAL exit 0 matches the package README and the public SDK verifier. Behavior kept; added tests pinning PARTIAL accept plus forged PARTIAL reject. |
| 5 | re-rv-3217-security Low (log injection, SUCCESS printed before attestation crash) | Low | FIXED AND TESTED | `_fail` strips CR/LF, pack-controlled prints use `_display`, non-dict attestation fails closed before the success line. Probe: old code raised AttributeError after printing SUCCESS; new code returns False. |
| 6 | re-rv-3217-security Low (drive-letter and trailing-slash names) | Low | FIXED AND TESTED | `_is_safe_member` rejects `:` and trailing `/`, matching `proof_verify_router._safe_zip_member`. Probe: `C:/...` and `dir/` were accepted before, rejected after. |
| 7 | re-rv-3217-blast Low (`BadZipFile` escapes `except OSError`) | Low | FIXED AND TESTED | Read block catches `OSError`, `BadZipFile`, `zlib.error`, `EOFError`. Probe showed a corrupt member raised `zlib.error` out of `verify_pack` before; it returns False now. Broadened beyond the named `BadZipFile` because the probe proved decompression errors escape too. |
| 8 | re-rv-3217-tests Low 1 (summary-hash branch untested) | Low | FIXED AND TESTED | Added `test_summary_hash_mismatch_fails` pinning the existing check (passes before and after; guards the branch). |
| 9 | re-rv-3217-tests Low 2 (resign self-harm untested) | Low | FIXED AND TESTED | Added `test_resign_unmodified_pack_still_passes` (passes before and after; guards the test helper). |
| 10 | re-rv-3217-tests Low 3 (PARTIAL untested) | Low | FIXED AND TESTED | Added PARTIAL accept and forged-PARTIAL reject tests (pass before and after; pin the contract from finding 4). |
| 11 | re-rv-3217-tests Low 4/5 (control-only tests, coverage floor) | Low | BLOCKED | Informational notes about the existing suite, no code change needed. The new tests above supersede the coverage concern for the changed lines. |
| 12 | Out of scope: suspended-tenant deny on live auth, tenant-scope gate failure, 7 xfail cross-tenant leaks | n/a | BLOCKED | Owned by other tasks per the order. This PR has no tenant path (offline CLI, confirmed by re-rv-3217-tenant OK), so nothing here interacts with them. |

Notes on choices: non-canonical names (`./x`, `a//b`) are rejected
outright rather than normalized and allowed, which is stricter than the
suggested normalize-and-compare but still fail closed, and honest
producer packs only contain canonical names. Case-only collisions are
also rejected because auditors may unzip on case-insensitive volumes.

## Tests

Exact commands (all through the slot queue; `.venv` is the shared
symlink venv, nothing was installed):

1. Baseline before changes:
   `~/metacode/fleet/heavy .venv/bin/pytest services/admin/tests/test_verify_audit_pack.py -q --no-cov`
   Result: 20 passed.
2. New tests against the ORIGINAL verifier (fix copied aside, original
   restored via `git show HEAD:...`, fix restored afterwards):
   same file with `-k "alias or unsafe_member or bool or attestation or
   corrupt or newline or banner or summary or resign or partial"`
   Result: 10 failed, 4 passed. The 10 failures were
   `test_extract_alias_member_rejected[dot/empty/case]`,
   `test_unsafe_member_names_rejected[C:/temp/evil.csv and reports/]`,
   `test_manifest_chain_length_bool_rejected`,
   `test_non_dict_attestation_fails_closed`,
   `test_corrupt_member_fails_closed`,
   `test_newline_in_snapshot_id_cannot_forge_success`,
   `test_success_banner_states_chain_not_recomputed`.
   The 4 passes were the pinning tests (summary, resign, 2 PARTIAL),
   which guard pre-existing behavior by design.
3. Full suite with the fix:
   `~/metacode/fleet/heavy .venv/bin/pytest services/admin/tests/test_verify_audit_pack.py -q --no-cov`
   Result: 34 passed (20 existing plus 14 new).
4. Lint:
   `~/metacode/fleet/heavy .venv/bin/ruff check services/admin/scripts/verify_audit_pack.py services/admin/tests/test_verify_audit_pack.py`
   Result: All checks passed.
5. Finding probes (scratch, `/tmp/probe_3217.py`, `/tmp/probe_crc.py`,
   not committed): alias pack True before / False after; bool length
   True before / False after; attestation string raised AttributeError
   before / False after; `C:/...`, `dir/`, `./x` accepted before /
   rejected after; corrupt member raised `zlib.error` before / False
   after.

Not run: `scripts/security/scan_tenant_scope.py` (no queries touched),
broader admin suite (change is confined to one script plus its tests;
full suite run left for the merge gate).

## Needs Christopher's decision

1. The success line changed from `[SUCCESS] Cryptographic Integrity:
   VERIFIED` to `[SUCCESS] Bundle Consistency: VERIFIED (file hashes
   match; persisted chain was not recomputed)`. Anything outside the
   repo that parses the old stdout wording will need updating.
2. PARTIAL packs keep exiting 0, matching the package README and the
   public SDK. If auditors should treat PARTIAL as a failure, that is a
   product call, not taken here.
3. The verifier still does not replay the persisted row chain and the
   pack has no signature, so a rebuilt but internally consistent pack
   passes. Real chain authentication needs a signature over the
   manifest root, which is new product work.
