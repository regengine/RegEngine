# Provisioning runbook: Cloudflare R2 object storage + Supabase Auth SMTP

Closes the hands-on remainder of **#2351** (R2 object storage) and **#2352**
(Supabase Auth SMTP → Resend). Both tickets are gated on cloud-console actions
that only an operator with the relevant accounts can perform — there is no code
left to write.

Decision memos: [`docs/decisions/2026-05-12-object-storage.md`](../decisions/2026-05-12-object-storage.md),
[`docs/decisions/2026-05-12-supabase-smtp.md`](../decisions/2026-05-12-supabase-smtp.md).

## Already done in the repo (do not redo)

- **Backend S3 client is wired.** `OBJECT_STORAGE_*` env vars are read in
  `services/shared/base_config.py`; `/v1/ingest/*` returns **503** with an
  `object_storage_disabled` warning until keys are set
  (`services/ingestion/main.py:68`). Provisioning is env-var-only.
- **Subprocessor disclosures exist.** Cloudflare R2 and Resend are both rows in
  `frontend/src/lib/trust-subprocessors.ts` (rendered by `/dpa` and `/trust`).
  The #2352 delta — naming Resend as Supabase Auth's SMTP transport — and the
  DPA effective-date bump (v1.2) ship in the PR that adds this runbook.

## Sequencing rule (DPA §4)

Deploy the disclosure change (DPA/Trust) **before** flipping any production
env var or Supabase setting. The customer-notice clock starts at engagement, so
the public disclosure must be live first. (Pre-production today: zero external
tenants, so this is procedural rather than an active compliance fire — but keep
the order.) Confirm the DPA effective date matches your actual deploy date
before merging.

---

## #2351 — Cloudflare R2

1. **Provision** (Cloudflare dashboard):
   - Create/sign in to the Cloudflare account.
   - Create buckets `regengine-ingest-raw-prod` and `regengine-ingest-processed-prod`.
   - Create an R2 API token scoped read+write to those buckets.
   - Note the S3 endpoint: `https://<account-id>.r2.cloudflarestorage.com`.

2. **Set Railway env vars** on the `RegEngine` service. Note the ticket's list
   omits the bucket-name vars — **set all six**, or ingested objects land in the
   `reg-engine-*-dev` defaults (`services/ingestion/app/config.py:25`):

   ```
   OBJECT_STORAGE_ACCESS_KEY_ID=<R2 access key>
   OBJECT_STORAGE_SECRET_ACCESS_KEY=<R2 secret>
   OBJECT_STORAGE_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
   OBJECT_STORAGE_REGION=auto
   RAW_DATA_BUCKET=regengine-ingest-raw-prod
   PROCESSED_DATA_BUCKET=regengine-ingest-processed-prod
   ```

3. **Verify:** next boot's Railway logs show no `object_storage_disabled`
   warning; `POST /v1/ingest/url` from an authed dev tenant returns 200 (not
   503); confirm an object lands in the R2 bucket.

4. Keep the 503 gate — it stays a useful failure mode if keys are ever cleared.

## #2352 — Supabase Auth SMTP → Resend

1. **Resend:** verify `auth.regengine.co` (preferred — isolates auth-mail
   reputation) or use the verified apex `auth@regengine.co`. Create a
   send-scoped Resend API key, separate from the app-level key.

2. **Deploy the disclosure first** (this PR): `/dpa` + `/trust` now name Resend
   as Supabase's SMTP transport.

3. **Supabase dashboard** → Project Settings → Auth → SMTP Settings → Enable
   Custom SMTP:
   - Host `smtp.resend.com`, Port `465` (TLS), Username `resend`
   - Password `<Resend API key>`
   - Sender `auth@auth.regengine.co` (or apex), Sender name `RegEngine`

4. **Verify:** trigger `resetPasswordForEmail` from `/forgot-password` with a
   test account; confirm the send event in the Resend dashboard and that the
   reset link still works end-to-end. Check the Resend plan's daily cap covers
   expected signup volume (Supabase's 3–4/hr default no longer applies).

## What Claude cannot do here

Creating cloud accounts, minting API tokens, and setting production
credentials/hosted settings are operator actions. Execute the console steps
above yourself; the code and disclosures are ready.
