# BREAK-REPORT: frontend/ (client auth, HTML bind, API error handling)

## Summary

Break-it pass over `frontend/` on Oct 8, 2026, scoped to client-side auth
bypass, unsafe HTML binding, and API error handling that hides 401/403.
All testing was local unit/component tests. No production URLs were called.

- Breaks found: 4 (all in API error handling, all fixed and tested)
- Fixed and tested (tests pass): 4
- Fixed but failing: 0
- Blocked: 0
- Attack attempts that did NOT break (documented below): 3

## Findings (sorted by severity)

### 1. HIGH: `apiFetch` retried 401/403/404 responses, tripling auth-failure traffic

What broke: every client error (including expired-session 401s) was sent to
the backend 3 times with 500ms and 1500ms delays, and surfacing the auth
failure to the UI was delayed by about 2 seconds each time.

How to reproduce: mock `fetchWithCsrf` to resolve `{ ok: false, status: 401 }`
and call `fetchAlerts('tenant-123')`. On the old code the mock was called
3 times. Test: `src/__tests__/lib/api-hooks-adversarial.test.ts`
("sends exactly one request on 401").

Root cause: `frontend/src/lib/api-hooks.ts` (old lines 42-54). The `throw`
for 4xx sat inside the same `try` whose `catch` recorded the error and fell
through to the retry delay, so the "Don't retry client errors" comment did
not match the behavior.

Fix: restructured the loop so only network failures, 429, and 5xx retry.
All other 4xx throw immediately with status attached
(`frontend/src/lib/api-hooks.ts`, new `frontend/src/lib/api-error.ts`).

Test results: the 4 break-proof tests failed on old code (3 calls instead of
1, status `undefined`), all 6 tests in the file pass on the new code.

### 2. HIGH: dashboard showed fake zeroed data instead of login prompt on 401/403

What broke: `useSystemMetrics` and `useSystemStatus` replaced ANY error,
including expired-session 401 and forbidden 403, with zeroed demo data
("Service unreachable"). A logged-out user saw fake unhealthy services
instead of being asked to log in again.

How to reproduce: mock `apiClient.getSystemMetrics` to reject with
`{ response: { status: 401 } }` and render `useSystemMetrics`. Old code
returned `{ _demo: true, total_tenants: 0, ... }`. Test:
`src/__tests__/hooks/useApi-auth-errors.test.tsx`.

Root cause: `frontend/src/hooks/use-api.ts` (old lines 107 and 121):
`data: query.data ?? (query.error ? DEMO_* : undefined)`.

Fix: demo substitution now applies only to non-auth failures via the new
`isAuthError` gate; 401/403 surface as real errors. `fetchAggregatedStatus`
additionally throws (instead of aggregating) when any health proxy returns
401/403.

Test results: 401/403/32-bit tests failed on old code (demo object returned
instead of `undefined`); all 4 pass on new code, including the guard test
that 503 still degrades to demo data.

### 3. MEDIUM: query and review hooks dropped the status into a text-only message

What broke: `authFetch` (`use-api-query.ts`) and `reviewFetch`
(`use-review.ts`) threw `new Error("API error: 401 ...")` with no status
property, so no caller could branch on 401 vs 403 without parsing the
string. Session-expiry handling and forbidden UI were impossible to wire
correctly.

How to reproduce: mock a 403 response through `useApiQuery` or
`useReviewItems` and read `error.status ?? error.response?.status`. Old code
yielded `undefined`. Tests: `src/__tests__/hooks/useApiQuery-auth-errors.test.tsx`,
`src/__tests__/hooks/useReview-auth-errors.test.tsx`.

Root cause: `frontend/src/hooks/use-api-query.ts` (old line 46) and
`frontend/src/hooks/use-review.ts` (old line 26).

Fix: both now throw via the shared `apiError()` helper, which sets
`error.status` and `error.response.status`. `reviewFetch` keeps the
server-provided message and only adds the status fields.

Test results: all 4 tests failed on old code (verified for the review file
by temporarily restoring the original: 2 failed, then restored the fix);
all pass on new code.

### 4. MEDIUM: successful POSTs with malformed bodies re-executed up to 3 times

What broke: `apiFetch` parsed the success body (`res.json()`) inside the
retryable `try`, so a 200 with an empty or malformed body was treated as a
transient failure and the request (including POST mutations such as alert
acknowledgement) was sent up to 3 times.

How to reproduce: mock `fetchWithCsrf` to resolve `{ ok: true, json: ()
=> { throw new SyntaxError(...) } }` and call `acknowledgeAlert`. Old code
called fetch 3 times. Test: `src/__tests__/lib/api-hooks-adversarial.test.ts`
("does not re-execute a POST when the success body is malformed").

Root cause: same `try` block as finding 1,
`frontend/src/lib/api-hooks.ts` (old line 39).

Fix: body parsing now happens outside the retryable section, so a parse
failure throws immediately with no retry.

Test results: failed on old code (3 calls), passes on new code.

## Attempts that did not break

1. Forged `localStorage` sysadmin profile (`is_sysadmin: true`,
   `permissions: ["review.read", "review.decide"]`, foreign tenant id) with
   no cookie session: `isAuthenticated`, `hasAdminSession`, and
   `hasTenantSession` all stay false because the token state requires the
   cookie-backed `/api/session` answer. Pinned by
   `src/__tests__/auth/client-bypass.test.tsx` (3 tests, pass).
2. Unsafe HTML bind audit: the only `dangerouslySetInnerHTML` in shipped
   code is `src/components/seo/json-ld.tsx`, which serializes through
   `stringifyForScript` (escapes every `<`). Existing XSS tests in
   `src/__tests__/lib/json-ld.test.ts` cover `</script>`, `<!--`, keys, and
   nesting. No markdown-to-HTML renderer with raw HTML was found in shipped
   code. No break, no change.
3. Login redirect (`next` param) audit: `PasswordlessEntryClient` routes
   through `safeNextPath` with deny prefixes for `/login` and
   `/auth/verify`, and post-login forwarding gates on `isAuthenticated`
   (not localStorage user alone). Adversarial values (`//evil.com`,
   `javascript:`, backslashes, tab-injected paths) are covered by the
   existing `src/__tests__/lib/safe-redirect.test.ts`. No break, no change.

## Verification

- New tests: 6 files, 23 tests, all pass.
- Full frontend unit suite: 142 files, 1205 passed, 4 expected fail,
  2 skipped, 0 failed.
  (`./node_modules/.bin/vitest run --bail 1` in `frontend/`)
- `tsc --noEmit`: clean.
- `eslint` on all changed and new files: clean.
- Old-code check: each break-proof test was run against the pre-fix code
  and failed there (api-hooks 4 failures, useApiQuery 2, useApi 3 plus one
  guard assertion corrected, useReview 2 via temporary restore).

## Open questions

1. `hasAdminSession` in `auth-context.tsx` uses exact
   `permissions.includes("review.read")` while `permissions.ts` matching is
   case and separator insensitive. A backend grant of `Review.Read` or
   `review:read` would fail closed (admin UI hidden, no bypass). Changing
   it to `hasPermission` would widen access, so I left it alone. C.Lee
   should confirm the canonical permission spelling with the backend team.
2. `decodeRegEngineClaims` (`jwt-claims.ts`) accepts tokens that omit
   `aud`, `iss`, or `exp`. The backend is the authoritative verifier and
   the frontend check is documented as defense in depth, so I left it. If
   the proxy should reject missing-claim tokens up front, that is a
   follow-up.
3. `validateUuid` (`api-proxy.ts`) accepts only UUID v1-v5. If the backend
   ever issues v6/v7 tenant ids, legitimate proxy calls would 400. No
   change made; flagging in case id formats change.
