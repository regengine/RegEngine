# Password Reset Flow Review - 2026-05-12

## Summary

Status: implemented with live-email coverage gated behind explicit credentials.

This review cross-references the May 12 password reset checklist against the
current remediation. Local unit and gated Playwright checks cover the backend,
frontend, proxy, and no-credentials live-QA skip path. Items that require real
Supabase email delivery, mailbox access, or deployed session validation remain
marked as live-gated rather than asserted from mocks.

## Traceability Matrix

| # | Checklist item | Status | Fix / evidence | Tests / QA | Residual risk |
|---|---|---|---|---|---|
| 1 | Existing email reset request shows success | Pass | Forgot-password UI posts to `/api/admin/auth/forgot-password`; backend returns generic success and sends Supabase reset email when configured. | `frontend/src/__tests__/auth/password-reset.test.tsx`; `services/admin/tests/test_forgot_password_1086.py` | Live delivery still requires gated QA env. |
| 2 | Non-existent email gets identical success | Pass | Backend catches Supabase errors and always returns `_FORGOT_PW_GENERIC_MSG`; UI does not display provider details. | `services/admin/tests/test_forgot_password_1086.py` | Frontend error remains generic only for non-2xx transport/API failures. |
| 3 | Reset email arrives within 60s, link single-use | Live-gated | Live Playwright artifact polls mailbox for reset email and verifies reuse failure after successful reset. Backend enforces recovery-token single-use by `jti`/`session_id`. | `frontend/tests/e2e/password-reset.live.spec.ts`; `services/admin/tests/test_reset_password_token_scope.py` | Requires `LIVE_PASSWORD_RESET_QA=true` and mailbox command. Redis errors intentionally fail open. |
| 4 | Token expires after stated duration with clear error | Partial / live-gated | UI shows expired/no-session state with 1-hour email-link copy. Backend separately rejects already-minted recovery sessions older than 15 minutes. | `services/admin/tests/test_reset_password_token_scope.py`; `frontend/src/__tests__/auth/password-reset.test.tsx` | True Supabase email-link expiry must be verified in a live/staging Auth configuration. |
| 5 | Token cannot be reused after successful reset | Pass / live-gated | Backend single-use claim rejects replay; live QA reopens the same reset URL in a fresh context after success. | `services/admin/tests/test_reset_password_token_scope.py`; `frontend/tests/e2e/password-reset.live.spec.ts` | Live replay proof requires credentials; Redis outage path is fail-open by design. |
| 6 | Token is bound to email | Partial | Reset route derives the RegEngine user from `sb.auth.get_user(token).user.email`; no email parameter is accepted from the reset URL. | Existing backend route tests cover token-user lookup; live QA doc lists token/email binding verification. | Copying issued tokens across accounts needs live Supabase/session-log verification. |
| 7 | New password invalidates existing sessions | Pass / live-gated | Reset bumps `token_version`, revokes all user sessions, and revokes elevation tokens before confirmation email send. | `services/admin/tests/test_auth_routes_1333.py`; `services/admin/tests/test_reset_password_token_scope.py` | Browser-level proof for already-open sessions remains live-gated. |
| 8 | Reset enforces signup password rules | Pass | Reset route calls shared `validate_password`; frontend removed the hardcoded 8-character blocker and surfaces backend `detail`. | `services/admin/tests/test_password_policy_1342.py`; `frontend/src/__tests__/auth/password-reset.test.tsx` | None known locally. |
| 9 | Reset cannot set current password | Pass | Reset route compares the submitted password with the current hash and returns 400 before DB write/Supabase sync. Live QA appends a per-run suffix to avoid accidental current-password reuse. | `services/admin/tests/test_auth_routes_1333.py`; `frontend/tests/e2e/password-reset.live.spec.ts` | Failed reset attempts still consume the recovery-scoped token, matching current single-use ordering. |
| 10 | Multiple reset requests behavior documented | Live-gated | Live QA doc requires issuing two reset emails and recording whether Supabase accepts only the latest or all unexpired links. | `docs/qa/password-reset-live-qa.md` | Cannot be concluded from local mocks; depends on Supabase project behavior. |
| 11 | Reset link works in incognito/no session | Live-gated | Live Playwright test opens the emailed reset URL in a fresh browser context before completing reset. | `frontend/tests/e2e/password-reset.live.spec.ts` | Requires live email and Supabase credentials. |
| 12 | Confirmation email sent after successful change | Implemented / live-gated | Reset route sends best-effort Resend confirmation after commit, session revocation, and elevation revocation. | `services/admin/tests/test_auth_routes_1333.py`; live QA polls for confirmation email. | Delivery depends on `RESEND_API_KEY`/mail provider and live mailbox access. |

## Implementation References

- Frontend reset request and policy handling:
  `frontend/src/app/forgot-password/ForgotPasswordClient.tsx`,
  `frontend/src/app/reset-password/ResetPasswordClient.tsx`.
- Admin proxy unauthenticated reset paths:
  `frontend/src/app/api/admin/[...path]/route.ts`.
- Backend forgot/reset routes:
  `services/admin/app/password_reset_routes.py`,
  `services/admin/app/auth/reset_password_router.py`.
- Live QA instructions:
  `docs/qa/password-reset-live-qa.md`.

## Read-Only Review Merge

Five read-only reviewer scopes were attempted as subagents. The subagent pool
hit the Codex usage limit, so the same scopes were executed locally without
file edits before this ledger merge.

| Reviewer scope | Files reviewed | Merged findings | Disposition |
|---|---|---|---|
| Frontend/Auth UX | `ForgotPasswordClient.tsx`, `ResetPasswordClient.tsx`, admin proxy route, frontend auth/proxy tests | No new findings. Forgot-password and reset-password both route through `/api/admin`, recovery `Authorization` is preserved, and backend password-policy errors are surfaced. | No frontend worker assigned. |
| Backend forgot-password | `password_reset_routes.py`, `test_forgot_password_1086.py`, `.env.example` | No new findings. Generic response, provider-error masking, email normalization, and server-side `redirect_to` fallback are covered. | No forgot-password worker assigned. |
| Backend reset security | `reset_password_router.py`, reset/security tests | No new findings. Current-password reuse is rejected before DB commit/Supabase sync, successful reset bumps `token_version`, revokes sessions/elevation tokens, and sends confirmation email best-effort. | No backend reset worker assigned. |
| Live Email QA | live Playwright config/spec and QA doc | No new findings. The test is gated, skips without env, uses a per-run password suffix, opens a fresh browser context, polls reset/confirmation email, and documents manual live-only checks. | No live-QA worker assigned until credentials are available. |
| Cross-reference ledger | audit ledger plus implementation/test/doc references | One P3 ledger-completeness gap: the review merge itself was not recorded. | Fixed in this doc-only update. |

## Fix Worker Assignment

No code fix workers were assigned because the accepted review output contained
no new code or test defects. The only worker scope was this doc-only ledger
merge:

- Ledger worker: `docs/audits/password-reset-flow-review-2026-05-12.md`.

Future live-evidence work, once credentials are available, should stay scoped
to `frontend/tests/e2e/password-reset.live.spec.ts`,
`docs/qa/password-reset-live-qa.md`, and this audit ledger. It should not touch
the frontend or backend implementation unless the live run finds a concrete
behavioral defect.

## Verification Run

- `pytest services/admin/tests/test_forgot_password_1086.py services/admin/tests/test_auth_routes_1333.py services/admin/tests/test_reset_password_token_scope.py -q`
- `npm run test:run -- src/__tests__/auth/password-reset.test.tsx src/__tests__/api/admin-proxy-auth.test.ts` (6 tests)
- `npm run test:e2e -- --config=playwright.password-reset-live.config.ts --reporter=line`

The live-QA Playwright command is expected to skip unless
`LIVE_PASSWORD_RESET_QA=true` and all required mailbox/Supabase/frontend
environment variables are present.
