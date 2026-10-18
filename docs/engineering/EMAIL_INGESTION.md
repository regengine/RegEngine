# Inbound email ingestion

Status: built, unit-tested, **not enabled in production**. This doc describes
what is actually implemented and checked in — see
[DESIGN_email-ingestion.md](../../DESIGN_email-ingestion.md) at the repo root
for the full design log and self-review history.

## What it does

A Postmark inbound-parse webhook lets a tenant email a CSV instead of
uploading it through the portal or calling the ingest API directly:

1. Postmark POSTs the parsed email as JSON to
   `POST /webhooks/email/inbound` ([router.py](../../services/ingestion/app/email_ingest/router.py)).
2. The request is authenticated with HTTP Basic Auth
   ([auth.py](../../services/ingestion/app/email_ingest/auth.py)) —
   `EMAIL_INBOUND_BASIC_AUTH_USER` / `EMAIL_INBOUND_BASIC_AUTH_PASSWORD`.
   This authenticates the transport ("this call came from Postmark"), not
   the original sender.
3. The recipient address (`OriginalRecipient` > `ToFull` > `To`) is
   resolved to a `tenant_id` via `fsma.get_tenant_by_inbound_address`, a
   SECURITY DEFINER lookup against `fsma.tenant_inbound_addresses`
   ([tenant_lookup.py](../../services/ingestion/app/email_ingest/tenant_lookup.py)).
   Since v122 that same lookup also checks the email's `From` address
   against that row's `allowed_senders` allowlist — the recipient address
   alone is not a tenant boundary, because Postmark will forward mail from
   *any* internet sender addressed to a configured inbound address using
   the same shared Basic-Auth credential.
4. Each `.csv` attachment is size/type-checked and handed to the existing
   `app.csv_templates.ingest_csv` path — the same CTE-type detection, UOM
   normalization, date parsing, and row cap that CSV uploads and the CSV
   API get. No parsing logic is duplicated for the email path.
5. One row per email is written to `fsma.inbound_email_audit` (status
   `accepted` / `partial` / `rejected`, per-attachment detail in `details`).
   A `message_id`-keyed claim-then-act insert (v122) makes retried and
   concurrent deliveries of the same Postmark `MessageID` safe: the first
   request to claim a `MessageID` runs ingestion, a second concurrent
   delivery gets `409` (Postmark's own retry-on-non-2xx contract recovers
   it), and a delivery that arrives after the first has finished replays
   the recorded result instead of re-ingesting.

Everything except a missing/invalid `Authorization` header (`401`), DB
unavailability (`503`), and a same-`MessageID` claim conflict (`409`)
returns HTTP `200` with a structured body — an unmapped recipient, a
disallowed sender, or a rejected attachment are all data-quality outcomes,
not transport errors, so they don't trigger Postmark retries.

## Configuration

| Env var | Purpose | Required in prod |
|---|---|---|
| `EMAIL_INBOUND_BASIC_AUTH_USER` | Basic-Auth username the webhook must present | yes — the endpoint 401s every request when unset (fails closed, no unauthenticated mode) |
| `EMAIL_INBOUND_BASIC_AUTH_PASSWORD` | Basic-Auth password | yes, same as above |

No new third-party dependency was added — `base64`, `binascii`,
`email.utils` are stdlib, and DB access reuses
`shared.database.get_db_session` / `shared.tenant_context.set_tenant_guc`,
already in `requirements.lock`.

## Rollout status: not live

`email_ingest` is a registered router name
([server/router_policy.py](../../server/router_policy.py)) but is **not**
in `PRODUCTION_ENABLED_ROUTERS`. Production's `ENABLED_ROUTERS` allowlist
must match that set exactly or the app refuses to boot, so this endpoint
cannot be exposed in production without both a code change to promote it
into that set and completing review of the Basic-Auth credential rollout
(tracked in [ROUTER_SURFACE.md](ROUTER_SURFACE.md)). In non-production
environments the router is mounted by default (it's on unless explicitly
named in `DISABLED_ROUTERS`).

## Known limitations

- **No admin or self-service provisioning.** There is no admin route,
  script, or seed helper that writes to `fsma.tenant_inbound_addresses`
  (the recipient-address → tenant mapping and its `allowed_senders`
  allowlist). Onboarding a tenant onto this channel today means someone
  manually inserting a row, e.g.:

  ```sql
  INSERT INTO fsma.tenant_inbound_addresses (tenant_id, inbound_address, allowed_senders)
  VALUES ('<tenant-uuid>', 'acme-inbound@yourdomain.example', ARRAY['supplier@acme.example', '@acme.example']);
  ```

  This is fine for local/dev testing but is a real gap for production
  onboarding — it is called out as explicitly out of scope in the design
  doc (section 14), not an oversight this doc is glossing over.
- **Sender check is an allowlist match, not sender verification.**
  `allowed_senders` matches the `From` address exactly or by `@domain`
  suffix against a plain-text array on the mapping row. RegEngine does not
  independently verify SPF/DKIM/DMARC on the original message — it trusts
  that Postmark accepted and relayed it faithfully. A row with an empty
  `allowed_senders` array authorizes no sender at all (fails closed), but
  a compromised or spoofed sender within an allowed `@domain` would pass.
- **Tests are unit-level and fully mocked; nothing here talks to a real
  mail provider.** `test_email_ingest_router.py`,
  `test_email_ingest_service.py`, `test_email_ingest_auth.py`,
  `test_email_ingest_tenant_lookup.py`, and
  `test_email_ingest_schemas.py` (under
  [services/ingestion/tests/](../../services/ingestion/tests/)) all run
  against a mocked DB session / monkeypatched collaborators, following the
  style of `test_stripe_plans_1342.py`. There is no live-Postgres
  integration test and no test that sends or receives an actual email —
  Postmark's webhook is exercised only via hand-built JSON payloads.
- **CSV attachments only.** PDF, XLSX, or any other attachment type is
  rejected outright by the content-type/extension check in
  [service.py](../../services/ingestion/app/email_ingest/service.py); this
  matches the design spec, it is not a partial implementation of a wider
  format list. The HTTP route `POST /api/v1/ingest/csv` does accept
  `.xlsx` (converted to CSV text before the same parser). That acceptance
  does not extend to this webhook. See
  [TRACEABILITY_FILE_INTAKE.md](TRACEABILITY_FILE_INTAKE.md).
- **No SendGrid/Mailgun support.** Only Postmark's inbound-parse JSON
  shape is modeled in [schemas.py](../../services/ingestion/app/email_ingest/schemas.py).
- **No reply to the sender.** A rejected or partially-rejected email gets
  no acknowledgement email back — the only record is the
  `fsma.inbound_email_audit` row and the webhook's (Postmark-ignored)
  JSON response body. There's no equivalent here to
  `services/ingestion/app/remediation/`'s outbound correction-link email.

## Running the tests

```bash
cd /home/user/wt-email-ingestion   # or wherever this worktree/repo lives
source venv/bin/activate
pytest services/ingestion/tests/test_email_ingest_router.py \
       services/ingestion/tests/test_email_ingest_service.py \
       services/ingestion/tests/test_email_ingest_auth.py \
       services/ingestion/tests/test_email_ingest_tenant_lookup.py \
       services/ingestion/tests/test_email_ingest_schemas.py -v
```

No Postgres, Redis, or network access is required for these — everything
is monkeypatched.
