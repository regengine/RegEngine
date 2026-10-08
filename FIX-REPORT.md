# FIX-REPORT: PR #3240 tenant isolation matrix findings

Merge commit be1e3270. All six re-rv-3240 angles read, plus the lead
(correct, security, tenant, tests, blast, ops) and area summaries that
mention #3240. Every finding below was confirmed against the code before
fixing. Out of scope items (other tasks own them) are listed at the end,
not fixed here.

## Findings table

| # | Source report | Severity | Status | Reason |
|---|---|---|---|---|
| 1 | correct, tenant H5, security, tests-lead | High | FIXED AND TESTED | Path test accepted 400/401/403/404/409/422 as proof and checked own call only for not-409. Billing subscription 403s on both calls before any tenant check (verified: require_permission precedes _resolve_tenant_context). Rewrote verdicts: own call must authenticate, cross call must be the route mismatch denial. |
| 2 | correct medium, security low | Medium | FIXED AND TESTED | HTTP 200 with body lacking tenant B counted as scoped. Any 200 on a cross-tenant path now fails. The substring check survives only as a backstop on denials and on pinned claim probes. |
| 3 | tenant H6, correct high-2, security medium-2 | High | FIXED AND TESTED | 111 pathless routes never got a cross-tenant probe. New test sends conflicting query, header (both names), and JSON body claims to all 136 API-key ops: mismatch denial required, or per-channel pin in CLAIM_UNENFORCED_PROBES (91 pins) with 2xx-no-B guard. Includes the billing invoice-pdf route the reports named. |
| 4 | blast medium | Medium | FIXED AND TESTED | Own-tenant POSTs wrote process-global stripe.api_key and _onboarding_store, and setdefault kept real dev-shell Stripe/Redis values. Fixture now forces synthetic values and restores both globals in teardown. Verified post-run: stripe.api_key None, no store leftovers, probe keys disabled. |
| 5 | tests-lead high-3, tests angle | High | FIXED | File added to the blocking repo-root-suite pytest list in backend-ci.yml. YAML validated; suite green locally. Whether the gate is required in branch protection was not verified here. |
| 6 | correct medium (63 session ops), security medium-3 (roles/MFA/expiry) | Medium | FIXED AND TESTED (part) / BLOCKED (part) | Added expired-key 401 test (with live twin control) and low-scope-key 403 order pin. Session and Bearer cookie matrix (63 ops), MFA step-up, and disabled-key cases still need a session harness: BLOCKED, larger work, docstring now states the API-key-only scope. |
| 7 | tenant medium-4, security medium-4 | Medium | FIXED (part) / BLOCKED (part) | Header claim probe now sends both X-Tenant-ID and X-RegEngine-Tenant-ID (same collectors, no outcome change observed). Mounting TenantContextMiddleware in the matrix app is BLOCKED: it couples to RLS contextvars, JWT, and metrics, and no handler was found trusting request.state over resolve_tenant_context. |
| 8 | correct low, security low-5 | Low | FIXED AND TESTED | Docstring cited resolve_tenant/403; tests exercise resolve_tenant_context/409. Docstring rewritten to cite the real helpers and codes. Trivial. |
| 9 | blast low | Low | FIXED AND TESTED | Failed app build left sys.path and app modules unrestored. Both paths now share _restore_module_state. Trivial. |
| 10 | tests low | Low | FIXED AND TESTED | Probe list could shrink silently. Added MIN_API_KEY_OPERATIONS (100, today 136) and MIN_PATH_OPERATIONS (20, today 25) floors plus the existing HMAC pin. Trivial. |

## Out of scope (noted, not fixed)

Suspended-tenant deny on live auth (owned by the #3238 task), the
tenant-scope gate failure (owned by the #3246 task), and the 7 xfail
cross-tenant leaks (owned by their task). Deliberately untouched:
migration 043, agent-middleware-api site/demo areas, production config.

## Test commands and results

Exact commands (all prefixed with the fleet slot queue as required):

1. `~/metacode/fleet/heavy .venv/bin/pytest -q tests/security/test_tenant_route_isolation_matrix.py` on HEAD code before changes: `....... [100%]`, 7 passed. This is the bug demonstration: green while finding 1 (billing 403 false pass) and finding 3 (111 routes unprobed) held.
2. Scratch survey (live app, bypass credential): `billing:GET:/api/v1/billing/subscription/{tenant_id} own=403 cross=403`, all other 24 path ops cross=409 E_TENANT_MISMATCH. Confirms finding 1 concretely.
3. Negative control (new strict verdicts applied to the old bypass credential): `own=403 cross=403`, `NEGATIVE CONTROL: FAILURES (strict verdict bites as intended), billing:...: own-tenant request not authenticated (status 403)`. Proves the rewritten path test fails without the credential fix.
4. New claim test with empty pins: FAILED (about 100 unpinned non-denials). Proves the new test bites; pins then filled from that output (90 entries plus 1 preemptive body pin for the intermittently 429ing regulation route).
5. `~/metacode/fleet/heavy .venv/bin/python /tmp/matrix_teardown.py` (pytest in-process, then inspects globals): `PYTEST_RC=0`, `stripe.api_key after module: None`, `onboarding leftovers: []`, probe keys enabled in neither store. Proves finding 4 fix.
6. Final: `~/metacode/fleet/heavy .venv/bin/python -m pytest tests/security/test_tenant_route_isolation_matrix.py tests/security/test_auth_coverage.py tests/security/test_route_security_manifest.py -q --no-cov -p no:cacheprovider`: `.................................... [100%]`, 36 passed (10 matrix, 26 neighbors, no interference).
7. `.venv/bin/ruff check` and `.venv/bin/ruff format --check` on the test file: `All checks passed!`, already formatted.
8. `python3 -c yaml.safe_load(backend-ci.yml)`: YAML OK.
9. `scripts/security/scan_tenant_scope.py`: not run. No production queries were touched (only a test file and a CI list line), so the gate has nothing new to scan from this change.

Notes on nondeterminism: the two ingest regulation routes answer 429 on some runs and 422 on others (endpoint-level limiter vs body validation order). Both outcomes are pinned (KNOWN_RATE_LIMITED_OPERATIONS plus UNENFORCED entries), so either outcome passes; a third outcome fails. Three full-file runs were green.

## Needs Christopher's decision

1. Session and Bearer cookie tenant matrix (63 ops in the manifest): new harness, roughly a second matrix file with login/session fixtures. Approve as a follow-up task or accept the documented gap.
2. Mounting TenantContextMiddleware in the matrix app: approve as a follow-up or accept the header-level coverage (both header names are probed through the resolver claim checks).
3. The 91 per-channel CLAIM_UNENFORCED_PROBES pins say, in writing, that those probes do not evaluate tenant claims today. Most are validation-first or unavailable-backend answers, which is fine, but the three 200-served probes (two catalog reads, one billing opt-out) mean a conflicting claim is silently ignored there. If product wants every tenant-scoped route to reject conflicting claims explicitly, that is a production change across those handlers.
