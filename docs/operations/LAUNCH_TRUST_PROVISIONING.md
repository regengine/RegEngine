# Launch Trust Provisioning Checklist

Date: 2026-05-19

This checklist covers the external operator steps behind the DPA and Trust
Center disclosures for object storage and Supabase Auth email. Do not commit
secrets, access keys, SMTP passwords, account IDs, or dashboard screenshots
containing secrets.

## Cloudflare R2 Object Storage

Decision source: [docs/decisions/2026-05-12-object-storage.md](../decisions/2026-05-12-object-storage.md)

Provisioning steps:

1. Create production buckets:
   - `regengine-ingest-raw-prod`
   - `regengine-ingest-processed-prod`
2. Create a scoped R2 API token with object read/write access only to those
   buckets.
3. Configure the production backend services that use object storage with:
   - `OBJECT_STORAGE_ACCESS_KEY_ID`
   - `OBJECT_STORAGE_SECRET_ACCESS_KEY`
   - `OBJECT_STORAGE_ENDPOINT_URL`
   - `OBJECT_STORAGE_REGION`
   - `RAW_DATA_BUCKET=regengine-ingest-raw-prod`
   - `PROCESSED_BUCKET=regengine-ingest-processed-prod`
4. Run an ingest smoke test that writes one small raw document and one
   normalized JSON artifact, then confirm both objects can be read back through
   the application path.
5. Confirm the DPA and Trust pages disclose Cloudflare R2 before enabling the
   production credentials for customer traffic.
6. Send the customary subprocessor change notice according to the customer DPA
   notice clause.

Rollback:

1. Remove or rotate the R2 API token.
2. Clear the `OBJECT_STORAGE_*`, `RAW_DATA_BUCKET`, and `PROCESSED_BUCKET`
   production variables.
3. Confirm object-storage-dependent endpoints fail closed with the configured
   storage-unavailable response instead of accepting uploads silently.

## Supabase Auth SMTP Via Resend

Decision source: [docs/decisions/2026-05-12-supabase-smtp.md](../decisions/2026-05-12-supabase-smtp.md)

Provisioning steps:

1. Verify `auth.regengine.co` in Resend. If subdomain verification is blocked,
   use `auth@regengine.co` on the already verified apex domain as the fallback.
2. Create a Resend API key named `supabase-auth-smtp` scoped to sending from
   the chosen auth sender.
3. In the Supabase project dashboard, configure Auth SMTP settings:
   - SMTP host: `smtp.resend.com`
   - SMTP port: `465`
   - SMTP user: `resend`
   - SMTP password: the scoped Resend SMTP API key
   - Sender name: `RegEngine`
   - Sender email: `auth@auth.regengine.co` or the approved fallback sender
4. Send a password reset to a controlled mailbox and confirm:
   - The message is delivered.
   - The sender matches the approved auth sender.
   - Headers show Resend as the SMTP transport.
   - The reset link lands on `/auth/callback?next=/reset-password`.
5. Confirm the DPA and Trust pages describe Supabase Auth password-reset email
   as delivered through Resend.

Rollback:

1. Disable custom SMTP in Supabase Auth or rotate the Resend SMTP key.
2. Send a controlled password reset and document whether Supabase falls back to
   its built-in mailer or returns a delivery error.
3. If the built-in mailer is re-enabled for customer traffic, update DPA/Trust
   disclosures before relying on it.

## Site contact and request-access forms

This path is the Next.js route `POST /api/contact`
(`frontend/src/app/api/contact/route.ts`). It is separate from the Supabase
Auth SMTP settings above. `/contact` and `/signup` both post here.
`/signup` renders the request-access form. It does not redirect to login.
A `plan` or `billing` query value is appended to the message when it matches
`^[a-z0-9][a-z0-9_-]{0,31}$`.

Delivery order:

1. When `CONTACT_WEBHOOK_URL` is set, the route POSTs the submission JSON
   there and does not call Resend. Redirects are not followed. A 3xx or any
   other non-2xx response is HTTP 502 `contact_delivery_failed`. A network
   error is HTTP 503 `contact_service_unavailable`.
2. When the webhook is unset and `RESEND_API_KEY` is set, the route POSTs to
   `https://api.resend.com/emails` with a 10 second timeout. The message goes
   to `christopher@regengine.co`. `reply_to` is the submitter. `from` is
   `RESEND_FROM_EMAIL`, or `RegEngine <onboarding@regengine.co>` when that
   variable is unset. The subject is `RegEngine request:` plus the company,
   or the name when the company is blank, with carriage returns and newlines
   removed and the subject cut at 150 characters.
3. When neither variable is set, the route returns HTTP 503
   `contact_service_unavailable` and does not claim the message was sent.

`source` on the request is accepted only as the exact value `signup`, which
is recorded as `regengine.co/signup`. Every other value, including a URL, is
recorded as `regengine.co/contact`. UTM fields are trimmed, lowercased, and
cut at 100 characters.

The form field `website` is a honeypot. A non-empty value returns HTTP 200
`{ "ok": true }` and is not delivered. The route also keeps an in-memory
counter of 5 submissions per IP per 10 minutes, per serverless instance. The
sixth is HTTP 429 with `Retry-After: 600`. Logs carry the submission id and
delivery shape. They do not include the name, email, company, or message.

```bash
curl -X POST "$SITE/api/contact" \
  -H "Content-Type: application/json" \
  -d '{"name":"Ada Lovelace","email":"ada@example.com","company":"Analytical Engines","message":"We need a workspace.","source":"signup"}'
```

A successful delivery returns `{ "ok": true }`. The form tells the visitor
the team will respond within one business day. The contact page also links
`mailto:christopher@regengine.co`. The signup form hides that link.
