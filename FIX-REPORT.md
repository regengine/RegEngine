# FIX-REPORT for PR #3239: Shared fail-closed webhook signature verifier plus semgrep gate

Merge commit 44f4fb873b6990964d91ca0a7e9dbec9e20bf6e6.
Reports read: all six re-rv-3239 angles (blast, correct, ops, security, tenant, tests),
the ops REPORT.md, plus lead-blast, lead-correct, lead-ops, lead-security, lead-tenant,
lead-tests, area-webhooks, int-deploy-readiness, int-overlap, int-rollback,
int-semgrep-gates. No writes were made to any report directory.

Security, tenant, blast and ops specialists filed no findings for #3239 (all OK).
The two mediums came from re-rv-3239-correct and were confirmed by re-rv-area-webhooks
(findings 5 and 6). Lows came from re-rv-3239-correct, re-rv-3239-tests and
re-rv-area-webhooks (finding 10).

## Findings

| # | Source report | Severity | Finding | Status |
|---|---------------|----------|---------|--------|
| 1 | 3239-correct medium, area-webhooks 5, lead-correct | Medium | Timestamped sha1 headers signed by `sign_webhook_payload` never verify: verify hardcoded sha256 (`webhook_auth.py:233`) | FIXED AND TESTED |
| 2 | 3239-correct medium, area-webhooks 6, lead-correct | Medium | Multi-`v1` Stripe-style rotation headers fail: dict parse keeps only the last `v1` (`webhook_auth.py:157-172`) | FIXED AND TESTED |
| 3 | 3239-correct low, lead-correct | Low | Connector `require_webhook_secret` wraps every `Exception` as missing-secret (`base.py:328-336`) | FIXED AND TESTED |
| 4 | 3239-correct low, area-webhooks 10, lead-correct | Low | Semgrep rule misses swapped operand order (`if signature and secret:`) | FIXED AND TESTED |
| 5 | 3239-correct low, 3239-ops, lead-correct | Low | Stripe comment says behavior unchanged, but whitespace-only secrets now 500 (`webhooks.py:705-713`) | FIXED (comment only) |
| 6 | 3239-correct low, lead-correct | Low | `verify_webhook_or_401` drops `algorithm` and `now` | FIXED AND TESTED |
| 7 | 3239-tests low, lead-tests | Low | Unknown-scheme tests use `md5=abcdef`, which a scheme-ignoring bug would also reject (test lines 98, 308) | FIXED AND TESTED |
| 8 | Area-webhooks 10, int-semgrep-gates | Low | Semgrep rule excludes `safetyculture.py` (stale: that file now uses the shared helper) | FIXED AND TESTED |
| 9 | 3239-tests low, lead-tests | Low | Semgrep rule has no positive/negative fixtures and no `semgrep --test` CI job | NOT FIXED, needs decision (see below) |
| 10 | 3239-security open question | None (question) | `sha1=` prefix accepted while caller default is sha256 (header picks scheme) | NO CHANGE, pinned policy (see below) |
| 11 | 3239-security open question | None (question) | Bare (non-timestamped) headers have no freshness check | NO CHANGE, matches old behavior (see below) |

Out of scope, noted only (other tasks own these): the suspended-tenant deny on
live auth, the tenant-scope gate failure, and the 7 xfail cross-tenant leaks.
None of them touch #3239 code paths.

## Fixes applied

- `services/shared/webhook_auth.py`: timestamped verification now HMACs with the
  `algorithm` argument (default sha256) instead of hardcoded `"sha256"`, so sign
  and verify share one rule; unsupported algorithms are rejected fail-closed.
- `services/shared/webhook_auth.py`: `_parse_signature_header` now returns every
  `v1` value as a list and verification accepts when any one matches under
  `hmac.compare_digest`.
- `services/shared/webhook_auth.py`: `verify_webhook_or_401` accepts and forwards
  `algorithm` and `now`.
- `services/shared/external_connectors/base.py`: connector `require_webhook_secret`
  catches `WebhookSecretMissingError` only, so unexpected errors propagate instead
  of being misreported as a missing secret.
- `services/ingestion/app/stripe_billing/webhooks.py`: comment now states that
  blank secrets are refused (no behavior change in this task).
- `.semgrep/webhook-signature.yaml`: added the swapped operand pattern via
  `pattern-either`, and removed the stale `safetyculture.py` exclusion (that file
  now uses the shared verifier and has no fail-open `and` shape).
- `services/shared/tests/test_webhook_auth.py`: strengthened both unknown-scheme
  pins to use a real sha256 hex under an `md5=` label; added
  `TestTimestampedAlgorithmAgreement` (3 tests), `TestRotatedMultiV1Headers`
  (3 tests), `verify_webhook_or_401` forwarding tests (2 tests), and the
  narrow-except propagation test (1 test).

## Tests

New tests added: 11 (3 sha1-timestamp, 3 multi-v1, 2 or_401 forwarding,
1 narrow-except, 2 strengthened scheme pins).

Fail-without-fix confirmation:
- The 4 core probes (sha1 timestamp round-trip, multi-v1 second match, or_401
  algorithm forwarding, or_401 clock forwarding) were run against the original
  module extracted with `git show HEAD:services/shared/webhook_auth.py` via
  `/tmp/repro_old.py`. All 4 raised on the old code (`WebhookSignatureInvalidError`
  for the first two, `TypeError: unexpected keyword argument` for the or_401
  pair) and pass on the new code.
- The narrow-except test was run with the `except` line temporarily reverted to
  `except Exception`: it FAILED (`ValueError` raised instead of `RuntimeError`),
  then the fix was restored by hand (verified with `git diff`).
- The semgrep fix was checked with a planted fixture (`/tmp/sgcheck/plant.py`
  holding both operand orders): the old rule flagged 1 snippet, the new rule
  flags both.
- The strengthened scheme pins pass on old and new code (no live bug there);
  they guard against a future refactor that ignores the scheme label.

Exact commands and results (all through `~/metacode/fleet/heavy`):

- `.venv/bin/python -m pytest services/shared/tests/test_webhook_auth.py services/shared/tests/test_external_connectors_defaults.py services/shared/tests/test_connector_safe_http.py` -> `84 passed in 0.76s`
- `.venv/bin/python -m pytest services/ingestion/tests/test_stripe_webhooks_1342.py -k "secret or missing"` -> `4 passed, 44 deselected in 0.64s`
- `.venv/bin/ruff check services/shared/webhook_auth.py services/shared/external_connectors/base.py services/shared/tests/test_webhook_auth.py services/ingestion/app/stripe_billing/webhooks.py` -> `All checks passed!`
- `.venv/bin/ruff format --check` on the same 4 files -> `4 files already formatted`
- `semgrep --config .semgrep/webhook-signature.yaml --error .` -> `Ran 1 rule on 806 files: 0 findings.`
- `scripts/security/scan_tenant_scope.py` was NOT run: no queries were touched (no SQL or Cypher in this change), so the tenant-scope gate is unaffected.

No database was needed (pure unit tests, no Postgres). No migrations added.
No background processes were left running.

## Needs Christopher's decision

1. Timestamped sha1 scope: I made verify use the `algorithm` argument on both
   sides (default sha256), so a timestamped sha1 header verifies only when the
   caller passes `algorithm="sha1"` to both sign and verify. If `v1` should mean
   sha256-only, say so and the signer should reject `algorithm != "sha256"` with
   a timestamp instead.
2. Semgrep fixtures (finding 9): adding `ruleid`/`ok` fixture files plus a
   `semgrep --test` step in the SAST job. I left this out because a fixture
   containing a fail-open snippet could trip the `--error` gate unless it is
   excluded, and CI wiring is a separate change. Worth doing, but not trivial.
3. Confirm the two pinned policies stay: an explicit `sha1=` header verifies
   under the default sha256 caller setting (the header picks the scheme), and
   bare non-timestamped headers carry no freshness window (same as the old
   connector compare). Both are now covered by tests, so changing them later
   will require a test update.
