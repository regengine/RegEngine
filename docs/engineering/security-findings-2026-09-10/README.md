# Historical Gitleaks disposition review — 2026-09-10

**No suppression or release approval.** This review covers every occurrence in the [candidate Gitleaks job](https://github.com/regengine/RegEngine/actions/runs/34521421916/job/103019598469) at `3f1cdea048bf5f52cb822456f8422718460e2a11`. No scanner configuration, baseline, ignore entry, credential, provider setting, or deployment was changed.

## Results

| Disposition | Occurrences | Meaning |
| --- | ---: | --- |
| Demonstrably synthetic/noncredential | 151 | Explicit unexpanded/incomplete documentation placeholders, unsigned JWT forgery fixtures, non-authentication data/code expressions, or PEM-header assertions. Exact source construction supplies the evidence. |
| Synthetic fixture source; issuance unverified | 87 | Test source intent is confirmed, including signing/environment and sanitization fixtures. This does not prove a value was never issued or deployed. Owner disposition remains required. |
| Unresolved | 84 | No sufficiently specific nonfunctional construction established. Requires credential/source-owner investigation. |

There are **322 occurrences, 306 unique fingerprints, and 51 finding commit IDs**. Sixteen additional occurrences share fingerprints because the scanner can report multiple matches at the same commit/file/rule/start line. The JSON preserves all occurrences with separate occurrence IDs; do not silently deduplicate them. Schema version 2 represents each public commit identity as `commit_url`; its final URL path segment is the exact full Git commit ID. Original scanner fingerprints remain unchanged, including their commit-ID component.

The full occurrence fingerprint multiset matches both the candidate job above and [main run 34307820114](https://github.com/regengine/RegEngine/actions/runs/34307820114). Reproduction used Gitleaks **8.30.0**, verified against its published Darwin ARM64 release checksum, and the unchanged repository config. Scanning main ancestry alone yielded only 219 occurrences; scanning ancestry of all 51 historical finding commits reproduced all 322. The inventory records these exact commit URLs, the verified release checksum source and archive URL, and an immutable config source URL. This is why a main-only rerun cannot certify resolution of this historical corpus.

## Production environment findings need explicit owner disposition

All three come from historical `.env.production` in commit `a130816b2c95f51e253b311dd73a9597eb2f88c4`:

| Line | Variable name | Current finding disposition | Required owner evidence |
| --- | --- | --- | --- |
| 15 | ADMIN_MASTER_KEY | Unresolved; no explicit placeholder marker | Determine whether it was issued/deployed; identify old administrative callers and provide provider/application revocation plus replay-denial evidence if real. |
| 18 | AUTH_SECRET_KEY | Unresolved; no explicit placeholder marker | Determine deployment history and signing-key identity; provide cutover and old-token denial evidence if real. |
| 37 | REDIS_PASSWORD | Unresolved; no explicit placeholder marker | Identify affected Redis instance(s), credential-change event and old-credential connection denial if real. |

No values, value hashes, connection URLs, or credential-bearing excerpts are included. These are potential historical credential exposures, not a claim that the credentials are currently valid. Replacing source text or setting a new value does not establish revocation.

## Private-key scanner matches are source assertions

Both private-key occurrences point at `tests/shared/test_digital_signatures.py:175`, in commits `a130816b2c95f51e253b311dd73a9597eb2f88c4` and `a6d476464bfe7afaf3ff830b65dc312a2be6d426`. Python AST inspection shows a byte-string PEM-header argument in `assert key_pair.private_key.startswith(...)`, following `KeyGenerator.generate_rsa(KeySize.RSA_2048)`. No embedded PEM key body exists in that assertion. The scanner matched source text spanning the header; this is concrete noncredential evidence, not merely an inference from the filename.

## Fixture evidence is narrower than provider clearance

The inventory separately identifies test-local signing/environment setup, wrong-key authentication tests, and sanitization/logging input assertions. The ten Stripe-token occurrences all live in sanitization/error/logging tests, but they remain in the **issuance-unverified fixture category**: recognizing test intent or a patterned suffix cannot prove provider non-issuance. The same distinction applies to arbitrary constants in other test files. No real credential is declared revoked by this review.

Six JWT occurrences explicitly decode to `alg=none`; they cannot satisfy the application's signed-token contract. Other JWT fixtures retain the narrower source-fixture disposition.

## Rationale coverage

| Rationale | Occurrences |
| --- | ---: |
| abbreviated_documentation_placeholder | 19 |
| code_expression_not_credential | 1 |
| data_identifier_not_authentication | 2 |
| literal_in_test_source_unverified_issuance | 53 |
| pem_header_assertion_scanner_spillover | 2 |
| production_environment_credential_unresolved | 3 |
| sanitization_or_logging_fixture | 19 |
| test_local_signing_or_environment_fixture | 14 |
| unexpanded_documentation_placeholder | 121 |
| unresolved | 81 |
| unsigned_jwt_forgery_fixture | 6 |
| wrong_signing_key_fixture | 1 |

## Remaining owner work

1. Review every unresolved and issuance-unverified fixture occurrence in `dispositions.json`; each includes exact rule, historical file, commit, line, fingerprint and a fixed rationale.
2. Record who reviewed each fingerprint and the evidence for synthetic/non-issued status, or the affected provider credential identifier and completed revocation/cutover evidence. Never attach secret values.
3. Review any future narrowly scoped scanner dispositions separately. This inventory grants no permission to add ignore entries, rewrite history, or weaken the full-history scan.
4. Keep release held until credential decisions and the separate deployment, migration, recovery, and authenticated evidence-export gates are complete.

Validation performed: pinned scanner reproduction; exact 322-occurrence/306-fingerprint comparison against two CI runs; JSON structure and count checks; absence of raw scanner fields (`Secret`, `Match`) and excerpts in the output schema; repository diff whitespace check. No provider authentication attempts, credential changes, or revocation tests were performed.
