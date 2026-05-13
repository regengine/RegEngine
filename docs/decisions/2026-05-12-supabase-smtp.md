# Supabase Auth SMTP — Decision Memo

- **Date:** 2026-05-12
- **Issue:** regengine/RegEngine#2312
- **Status:** Proposed — awaiting founder approval
- **Author:** Research pass via session worktree `wt-2026-05-12/i2312`

## TL;DR

Route Supabase Auth's outbound mail (password reset only, today) through our
existing Resend account via `GOTRUE_SMTP_*` env vars on the
`admin` Railway service's Supabase project. Net cost: one verified
`auth.regengine.co` sender + ~10 minutes of Supabase dashboard config. Removes
the built-in mailer's ~3–4 emails/hour ceiling and the opaque upstream
sub-processor disclosure on the DPA.

## Current state

Supabase Auth is configured with no `GOTRUE_SMTP_*` overrides. Outbound mail
therefore goes through Supabase's **built-in shared mailer**, which:

- Caps at roughly **3–4 emails per hour, per project** (Supabase documents this
  as a development-only fallback).
- Routes through an undocumented upstream provider (historically AWS SES; not
  contractually pinned). This shows up on our DPA today as a vague
  "Auth-side transactional email via Supabase's default mailer" line
  (`frontend/src/app/dpa/page.tsx:56`, mirrored at `trust/page.tsx:356`).
- Surfaces deliverability complaints (spam-folder hits, slow throttling) when
  multiple users hit password-reset in the same hour.

### Mail-triggering Supabase flows in the codebase

| Flow | File | Triggers Supabase mailer? |
|------|------|---------------------------|
| Password reset | `frontend/src/app/forgot-password/ForgotPasswordClient.tsx:49` (`resetPasswordForEmail`) | **Yes** |
| Magic link / OTP send | _not implemented_ | No |
| Email-confirm at signup | `services/admin/app/auth/signup_router.py:132` uses `admin.create_user({..., email_confirm: True})` — no confirmation email sent | No |
| Team invites | `services/admin/app/invite_routes.py:47` (`_send_invite_email` via Resend) | No — already on Resend |
| OTP verify | `frontend/src/app/auth/verify/VerifyClient.tsx:48` (`verifyOtp`) — _consumes_, doesn't send | No |

**Only the password-reset flow currently depends on Supabase's built-in
mailer.** That keeps the blast radius small but does not change the
disclosure or ceiling problem.

### Existing Resend integration

Resend is already a contracted paid sub-processor, used by `admin` for:

- `RESEND_API_KEY` / `RESEND_FROM_EMAIL` — sender defaults to
  `onboarding@regengine.co` (`services/admin/app/invite_routes.py:61`).
- Routes: team invites (`invite_routes.py`), tool-verification emails
  (`tool_verification_routes.py:289,449`), GDPR erasure receipts
  (`test_lead_erasure_1095.py`).
- Disclosed on the DPA at `frontend/src/app/dpa/page.tsx:79–83` for
  "Transactional email delivery (account, billing, and compliance alerts)."

**Verified domain:** the apex `regengine.co` is verified with Resend (sends
from `onboarding@regengine.co` succeed today). A separate subdomain
(`auth.regengine.co`) is the conventional choice for Supabase Auth so that
its reputation, SPF, and DMARC are isolated from product transactional mail,
and so that the From address visually distinguishes auth flows.

## Options

### Option A — Route Supabase Auth through Resend SMTP (recommended)

Add `GOTRUE_SMTP_*` overrides on the Supabase project (configured in the
Supabase dashboard, **not** on a Railway service — Supabase Auth runs inside
the Supabase project, not on Railway). The Railway side is unchanged.

**Concrete configuration (Supabase Dashboard → Project Settings → Auth → SMTP
Settings):**

| Variable | Value |
|----------|-------|
| `GOTRUE_SMTP_HOST` | `smtp.resend.com` |
| `GOTRUE_SMTP_PORT` | `465` (TLS) |
| `GOTRUE_SMTP_USER` | `resend` |
| `GOTRUE_SMTP_PASS` | `${RESEND_SMTP_API_KEY}` (new Resend API key scoped to SMTP-send) |
| `GOTRUE_SMTP_ADMIN_EMAIL` | `auth@auth.regengine.co` |
| `GOTRUE_SMTP_SENDER_NAME` | `RegEngine` |
| `GOTRUE_MAILER_AUTOCONFIRM` | unchanged (`false`) |

Prerequisites:

1. Verify `auth.regengine.co` in Resend (DNS: 2 SPF/DKIM CNAMEs + one DMARC
   TXT — same flow as `regengine.co` verification).
2. Mint a new Resend API key, named `supabase-auth-smtp`, with "Sending
   access" scoped to the new subdomain.
3. Paste config into Supabase Dashboard. (No Railway service env vars to
   update — Supabase Auth is hosted by Supabase.)
4. Send a test password reset and confirm headers show `via resend.com`.

**DPA / Trust Center delta:**

- Update `SUBPROCESSORS[Supabase].purpose` in
  `frontend/src/app/dpa/page.tsx:56` and the matching row in
  `frontend/src/app/trust/page.tsx:356` from
  > "...and Auth-side transactional email (signup confirmation, password
  > reset, magic link) via Supabase's default mailer"
  to
  > "Authentication, user database (PostgreSQL), and row-level security
  > enforcement. Auth-side transactional email (password reset) is delivered
  > via Resend (see Resend row below)."
- Update `SUBPROCESSORS[Resend].purpose` to add
  "...and Supabase Auth password-reset emails sent from
  `auth.regengine.co`."

### Option B — Keep the built-in mailer; document the risk

No config change. Update the DPA copy to explicitly call out that Supabase's
default mailer relays through an upstream provider whose identity Supabase
controls, and that we accept a ~3–4 emails/hour throughput cap on
password-reset. Add an internal runbook note that any future flow that
expands Supabase-mailer usage (magic links, signup confirmations, password
changes at scale) requires re-opening this decision.

**DPA delta:**

- Update the Supabase row to add: "Supabase's default mailer relays through
  an upstream email provider whose identity is governed by Supabase's
  sub-processor list, not RegEngine's. Outbound volume is limited to
  Supabase's documented free-tier ceiling."

## Recommendation

**Option A.** No blocker surfaced in research:

- Only one mail-sending Supabase flow is wired up today (password reset),
  so the migration is low-risk.
- We already have Resend as a contracted paid sub-processor — no new
  vendor, no new DPA signature.
- The apex domain is verified, so subdomain verification is a 10-minute
  DNS exercise rather than a vendor-onboarding cycle.
- The trust-and-safety sweep on 2026-05-10
  (`project_trust_safety_sweep_2026_05_10.md`) explicitly flagged
  Supabase-mailer-upstream opacity as an open follow-up. Option A closes it.

The only real cost is the DNS round-trip to verify `auth.regengine.co`. If
that domain is already claimed for something else, fall back to sending
auth mail from a `auth@regengine.co` mailbox on the existing verified apex
(Resend allows multiple From addresses on one verified domain). That keeps
the option viable even if subdomain verification slips.

## Open questions for founder

1. Approve `auth.regengine.co` as the auth-mail sender subdomain, or prefer
   `auth@regengine.co` on the existing apex?
2. Approve minting a separate Resend API key for Supabase (vs. reusing the
   existing app key)? Recommend yes — blast-radius isolation.
3. Approve the DPA copy delta in this memo as the source of truth for the
   `dpa/page.tsx` and `trust/page.tsx` updates that ship alongside the config
   change?
