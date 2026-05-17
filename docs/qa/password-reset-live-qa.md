# Password Reset Live QA

This is an opt-in live QA artifact for the Supabase-backed password reset flow. Normal CI must not set `LIVE_PASSWORD_RESET_QA=true`; without it, the test skips cleanly.

## Command

```bash
cd frontend
LIVE_PASSWORD_RESET_QA=true \
LIVE_PASSWORD_RESET_QA_FRONTEND_URL=https://your-regengine-frontend.example \
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co \
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key \
LIVE_PASSWORD_RESET_QA_EMAIL=existing-user@example.com \
LIVE_PASSWORD_RESET_QA_NEW_PASSWORD='DedicatedQaUserNewPassword1!' \
LIVE_PASSWORD_RESET_QA_PASSWORD_RUN_ID="$(date +%Y%m%d%H%M%S)" \
LIVE_PASSWORD_RESET_QA_MAILBOX_FETCH_COMMAND='path/to/mailbox-fetch-command' \
npm run test:e2e -- --config=playwright.password-reset-live.config.ts
```

Use a dedicated disposable QA user. The test changes that user's password to
`LIVE_PASSWORD_RESET_QA_NEW_PASSWORD` plus `-LIVE_PASSWORD_RESET_QA_PASSWORD_RUN_ID`.
When `LIVE_PASSWORD_RESET_QA_PASSWORD_RUN_ID` is omitted, the test generates a
per-run value so repeated runs do not fail the current-password reuse check.

## Mailbox fetch contract

The test intentionally does not assume Gmail, Mailosaur, IMAP, or another provider. Provide `LIVE_PASSWORD_RESET_QA_MAILBOX_FETCH_COMMAND`; Playwright runs it repeatedly for up to 60 seconds.

The command receives:

- `LIVE_PASSWORD_RESET_QA_EMAIL`: mailbox/user under test
- `LIVE_PASSWORD_RESET_QA_SINCE_ISO`: ISO timestamp to filter messages after
- `LIVE_PASSWORD_RESET_QA_MESSAGE_KIND`: `password_reset` or `password_changed_confirmation`

It must print JSON to stdout, either an array or an object with `messages`:

```json
{
  "messages": [
    {
      "subject": "Reset your password",
      "text": "Plain text email body with links",
      "html": "<a href=\"https://...\">Reset</a>",
      "receivedAt": "2026-05-12T18:25:00.000Z"
    }
  ]
}
```

## Automated coverage

- Existing-user reset request displays the "Check your inbox" UX.
- Password reset email arrives within 60 seconds.
- Reset link opens in a fresh Playwright browser context with no existing session.
- Password can be updated from the fresh context.
- Confirmation email arrives after the successful update.
- Reusing the same link in another fresh context shows expired/invalid-link UX.

## Manual/live-only checks

- True expiry: lower the Supabase recovery link TTL for a staging project, or wait beyond the configured TTL, then confirm the expired-link UX remains clear.
- Successive requests: issue two reset emails before using either link and record whether Supabase allows only the latest link or all unexpired links.
- Token/email binding: verify Supabase Auth logs or recovery session metadata show the token was accepted only for `LIVE_PASSWORD_RESET_QA_EMAIL`.
- Existing-session invalidation: keep a separate authenticated browser session open before the reset, complete the reset, then confirm whether that existing session remains valid according to the intended production policy.
