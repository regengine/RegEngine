# FIX-REPORT: PR #3228 tool-access token 24h expiry follow-up

Worktree branch off origin/main e854dadc. Finding sources: all six
re-rv-3228-<angle> SUMMARY.md reports, re-rv-area-auth (per-PR verdicts),
re-rv-lead-* and re-rv-int-* mentions of #3228. Out of scope per the task
(suspended-tenant deny on live auth, tenant-scope gate failure, 7 xfail
cross-tenant leaks) were noted only and not touched.

## Findings

| # | Source report | Severity | Finding | Status | Reason |
|---|---|---|---|---|---|
| 1 | re-rv-3228-blast (Medium), re-rv-3228-security (High), re-rv-3228-tenant (Medium), re-rv-3228-correct (Medium), re-rv-3228-tests (Medium) | High/Medium (same root cause) | 24h JWT expiry never runs on the only user-facing caller: `GET /api/tools/check-access` returns `hasAccess: !!token` and the verify route sets a 30-day cookie, so `decode_tool_access_token` (called only by tests) never enforces expiry in production | FIXED AND TESTED | New backend `POST /api/v1/tools/check-access` verifies signature, aud, iss, required unexpired exp, and 24h max lifetime; Next.js check-access proxies to it, fails closed, and clears stale cookies; verify route sets cookie maxAge from `expires_in_seconds` (default 86400) |
| 2 | re-rv-3228-security (Low), re-rv-3228-tenant (Low), re-rv-area-auth (Medium) | Low/Medium | `TOOL_ACCESS_TOKEN_EXPIRE_HOURS` has no upper bound, so an operator value like 100000 hours mints an 11-year token and decode accepts any future exp | FIXED AND TESTED | `_tool_access_expire_hours` falls back to 24h for values above 24h; `decode_tool_access_token` rejects lifetimes over 24h (+5s truncation tolerance) via `_enforce_tool_access_max_lifetime` |
| 3 | re-rv-3228-ops (Low) | Low | `TOOL_ACCESS_TOKEN_EXPIRE_HOURS` is an undocumented optional env var; operators get only a warning log on bad values | FIXED AND TESTED | Documented as optional, shorten-only, never required in README.md line 165; no behavior change, correctly not added to production-required env |
| 4 | re-rv-3228-tests (Medium), re-rv-3228-correct (Medium) | Medium | Tests prove mint/decode helpers but not the PR claim that a cookie stops working after 24h | FIXED AND TESTED | Added gate-level tests: backend check-access endpoint cases plus frontend check-access and cookie-maxAge tests, all verified to fail on pre-fix code |
| 5 | re-rv-int-deploy-readiness (Medium #4) | Medium | Existing long-lived cookies stop working once expiry is enforced; needs a comms note, no code fix | FIXED AND TESTED | Enforcement is now real: legacy no-exp cookies return `hasAccess: false` and are cleared; announcement wording is left to C.Lee (see decisions below) |
| 6 | re-rv-int-rollback (Medium) | Medium | Solo revert of 3228 conflicts on one generated `.secrets.baseline` timestamp line | No fix needed | Informational only; this change adds no baseline entries (verified by scanning all changed files with detect-secrets 1.5.0, zero findings) |

Skipped: none. Every confirmed critical, high, and medium finding above is
fixed. No BLOCKED or FIXED BUT TESTS FAILING items.

## Changes

- `services/admin/app/tool_verification_routes.py`: added
  `TOOL_ACCESS_TOKEN_MAX_LIFETIME_HOURS` (24.0); capped
  `_tool_access_expire_hours`; `_mint_tool_access_token` accepts an
  optional `expire_hours`; `decode_tool_access_token` enforces the max
  lifetime on both decode paths; new rate-limited (30/minute)
  `POST /api/v1/tools/check-access` returning `{hasAccess}` without
  logging the token; `ConfirmCodeResponse` gains `expires_in_seconds`.
- `frontend/src/app/api/tools/check-access/route.ts`: verifies the
  `re_tool_access` cookie through the admin service instead of checking
  presence; fails closed on backend error or missing backend URL;
  clears invalid cookies.
- `frontend/src/app/api/tools/verify/route.ts`: cookie `maxAge` now
  follows the backend `expires_in_seconds` (validated, capped at 24h,
  default 86400) instead of a fixed 30 days.
- `services/admin/tests/test_tool_access_check_endpoint.py` (new, 20
  tests): env cap, mint cap, decode lifetime cap, check-access endpoint
  accept/reject matrix, confirm `expires_in_seconds` reporting.
- `frontend/src/__tests__/api/tools-check-access-route.test.ts` (new, 5
  tests) and 3 new tests in
  `frontend/src/__tests__/api/tools-verify-route.test.ts`: backend
  verification wiring, fail-closed behavior, stale-cookie clearing,
  cookie maxAge derivation and cap.
- `README.md`: one sentence documenting the 24h expiry, the verified
  gate, and the optional shorten-only env var.

No migrations, no production config changes, no new dependencies
(`jose` was already present but is not used; the secret stays in the
backend). No queries touched, so
`scripts/security/scan_tenant_scope.py` was not run.

## Test commands and results

Backend (through the slot queue):

- `~/metacode/fleet/heavy .venv/bin/python -m pytest services/admin/tests/test_tool_access_check_endpoint.py -q --no-cov -p no:cacheprovider`
  Result: 20 passed.
- Same runner on the three pre-existing tool files
  (`test_tool_access_token_expiry.py`,
  `test_tool_access_jwt_separation.py`,
  `test_tool_verification_code_store.py`): 60 passed, no regressions.
- After `ruff format`: combined run of all four files: 80 passed.
- `ruff check` on both changed backend files: All checks passed.
- Fail-without-fix: with the HEAD version of
  `tool_verification_routes.py` swapped in by file copy (no git
  commands), the new test file fails (cap tests, decode-cap tests,
  check-access endpoint tests with AttributeError, and both
  `expires_in_seconds` tests); restored afterward and re-verified
  20 passed plus byte-identical restore via `diff -q`.

Frontend (deps installed with `npm ci`, run through the slot queue):

- `./node_modules/.bin/vitest run src/__tests__/api/tools-check-access-route.test.ts src/__tests__/api/tools-verify-route.test.ts`
  Result: 2 files passed, 10 tests passed.
- Fail-without-fix: with both HEAD route files swapped in, 7 of the 10
  tests fail (all 7 new ones; the 3 pre-existing pass); restored
  afterward and re-verified 10 passed plus identical restore.
- `npm run lint` on the four changed frontend files: 0 errors
  (41 warnings are pre-existing in surrounding files; the changed files
  use only allowed `console.error`), design-lint clean.
- CSRF regression: `vitest run
  src/__tests__/lib/csrf-exempt-prefixes.test.ts
  src/__tests__/proxy-csrf.test.ts`: 10 passed.

Secrets: installed detect-secrets 1.5.0 to /tmp (shared venv left
untouched) and scanned all five changed/new code files: zero findings,
so `.secrets.baseline` needs no update.

Not run: full admin pytest suite (needs local Postgres/Redis per repo
notes; targeted files cover the change), `npm run build` (lint plus
type-checked tests cover this surface; build needs full env), and
`scripts/security/scan_tenant_scope.py` (no queries changed).

## Needs C.Lee's decision

1. Session-change announcement: previously verified visitors (including
   30-day cookies and legacy no-exp cookies) will now see the email
   gate again after at most 24 hours, and immediately if their cookie
   has no valid exp. The deploy-readiness note asks for an announcement;
   the wording and channel are yours.
2. Backend availability tradeoff: if the admin service is unreachable,
   the tool gate now fails closed (shows the email form) instead of
   honoring the cookie. Tool content itself always renders, so this only
   re-shows lead capture, but confirm if that tradeoff is acceptable
   during outages.
