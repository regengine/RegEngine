# Design: Inbound Email Ingestion

Status: proposed · Owner: ingestion service · Tracking: "Inbound email ingestion" feature
Branch: `feature/inbound-email-ingestion`

## 1. Problem

RegEngine's marketing claims compliance data "arrives by email, comes out
structured." Today the repo has outbound email only
(`services/ingestion/app/remediation/delivery.py` → Resend). There is no
inbound email endpoint anywhere (`grep -rl inbound` / `grep -rl postmark`
across the repo returns nothing relevant). This design adds a narrowly
scoped inbound pipeline: a provider webhook receives the email, we
authenticate the caller, resolve a tenant from the recipient address,
run any CSV attachment through the *existing* CSV ingestion path
(`app.csv_templates.ingest_csv`), and persist one audit row per email.

Provider contract: Postmark's inbound webhook JSON
(`From`, `Subject`, `TextBody`, `Attachments: [{Name, Content, ContentType}]`)
— chosen per spec because it avoids raw MIME parsing and is a realistic,
common provider shape (SendGrid Inbound Parse and Mailgun differ in field
names but have the same content shape).

## 2. New module: `services/ingestion/app/email_ingest/`

Mirrors the layout of `app/remediation/` (package with `router.py` +
`service.py` + `schemas.py`) rather than a single file, since the module
has auth, tenant resolution, orchestration, and schemas as distinct
concerns from the start.

```
services/ingestion/app/email_ingest/
  __init__.py
  auth.py        # Basic-Auth webhook gate
  schemas.py      # Postmark inbound payload + response models
  tenant_lookup.py  # recipient -> tenant_id resolution (DB-backed)
  service.py      # orchestration: attachments -> csv_templates.ingest_csv, audit persistence
  router.py       # POST /webhooks/email/inbound
```

Tests: `services/ingestion/tests/test_email_ingest_router.py`,
`services/ingestion/tests/test_email_ingest_service.py`.

## 3. Data model (new Alembic migration)

Next revision after `20260904_c6a120b4e901_v120_rule_citations.py` (the
latest on `origin/main` as of this branch), so:

`alembic/versions/20260912_<newhash>_v121_email_ingestion.py`
(`down_revision = "c6a120b4e901"`).

**Deviation from spec's example names**: the spec sketches
`ingestion.tenant_inbound_addresses`. Every existing RegEngine
compliance/ingestion table in this repo lives in the `fsma` schema
(`fsma.manifest_blobs`, `fsma.ingestion_runs`, `fsma.notification_outbox`,
etc. — there is no `ingestion` schema anywhere in `alembic/versions/`).
To match the actual convention this design uses `fsma.tenant_inbound_addresses`
and `fsma.inbound_email_audit` instead of inventing a new schema.

### 3.1 `fsma.tenant_inbound_addresses`

```sql
CREATE TABLE IF NOT EXISTS fsma.tenant_inbound_addresses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    inbound_address TEXT NOT NULL,        -- lowercased before insert/lookup
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ux_tenant_inbound_addresses_address UNIQUE (inbound_address)
);
CREATE INDEX IF NOT EXISTS idx_tenant_inbound_addresses_tenant
    ON fsma.tenant_inbound_addresses (tenant_id);
```

RLS: `ENABLE`/`FORCE ROW LEVEL SECURITY` with the standard
`tenant_id = get_tenant_context()` policy (`_tenant_rls` helper, same as
v095), so a tenant admin UI can list/manage its own mapped addresses later.
That alone can't serve the webhook's lookup, because at webhook-receipt
time there is no tenant context yet — same bootstrap problem v095 solved
for `fsma.remediation_tokens` (`get_remediation_token_by_hash`). Reuse
that exact shape:

```sql
CREATE POLICY inbound_address_lookup
    ON fsma.tenant_inbound_addresses
    FOR SELECT
    USING (
        inbound_address = NULLIF(current_setting('app.inbound_lookup_address', true), '')
    );

CREATE OR REPLACE FUNCTION fsma.get_tenant_by_inbound_address(p_address TEXT)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = fsma, public, pg_temp
AS $fn$
DECLARE
    v_tenant UUID;
BEGIN
    PERFORM set_config('app.inbound_lookup_address', lower(p_address), true);
    IF NULLIF(current_setting('app.tenant_id', true), '') IS NULL THEN
        PERFORM set_config('app.tenant_id', '00000000-0000-0000-0000-000000000000', true);
    END IF;
    SELECT tenant_id INTO v_tenant
    FROM fsma.tenant_inbound_addresses
    WHERE inbound_address = lower(p_address) AND is_active
    LIMIT 1;
    RETURN v_tenant;
END;
$fn$;

REVOKE ALL ON FUNCTION fsma.get_tenant_by_inbound_address(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fsma.get_tenant_by_inbound_address(TEXT) TO regengine;
```

`tenant_lookup.py`:

```python
def lookup_tenant_by_inbound_address(session: Session, address: str) -> Optional[str]:
    """Resolve a tenant_id from a recipient address via the SECURITY DEFINER
    bootstrap function (no tenant GUC is set yet when this runs)."""
    row = session.execute(
        text("SELECT fsma.get_tenant_by_inbound_address(:addr) AS tenant_id"),
        {"addr": address.strip().lower()},
    ).fetchone()
    session.commit()  # release the transaction-local GUCs set inside the function
    return str(row.tenant_id) if row and row.tenant_id else None
```

### 3.2 `fsma.inbound_email_audit`

One row per inbound email, independent of how many attachments it had.
`tenant_id` is **nullable** — an email to an unmapped recipient has no
tenant yet has to be auditable (point 5 of the spec: "compliance-adjacent
data, must be auditable"), and `message_id` is unique so a provider retry
(Postmark retries on non-2xx) is idempotent instead of re-running CSV
ingestion a second time.

```sql
CREATE TABLE IF NOT EXISTS fsma.inbound_email_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID,                       -- NULL when recipient could not be mapped
    message_id TEXT NOT NULL,
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    subject TEXT,
    status TEXT NOT NULL CHECK (status IN ('accepted', 'partial', 'rejected')),
    rejection_reason TEXT,                -- set when status='rejected' (e.g. unmapped_recipient)
    attachment_count INTEGER NOT NULL DEFAULT 0,
    accepted_attachment_count INTEGER NOT NULL DEFAULT 0,
    rejected_attachment_count INTEGER NOT NULL DEFAULT 0,
    details JSONB NOT NULL DEFAULT '[]'::jsonb,  -- per-attachment {name, status, reason, rows_accepted, rows_rejected}
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ux_inbound_email_audit_message_id UNIQUE (message_id)
);
CREATE INDEX IF NOT EXISTS idx_inbound_email_audit_tenant_received
    ON fsma.inbound_email_audit (tenant_id, received_at DESC);
```

Writes go through a SECURITY DEFINER function rather than a plain
tenant-scoped INSERT, because the unmapped-recipient case has no tenant
GUC to satisfy a `tenant_id = get_tenant_context()` FORCE RLS policy —
same reasoning as `seed_obligations_for_tenant` (v112) and
`get_remediation_token_by_hash` (v095):

```sql
CREATE OR REPLACE FUNCTION fsma.record_inbound_email_audit(
    p_tenant_id UUID, p_message_id TEXT, p_sender TEXT, p_recipient TEXT,
    p_subject TEXT, p_status TEXT, p_rejection_reason TEXT,
    p_attachment_count INT, p_accepted_count INT, p_rejected_count INT,
    p_details JSONB
) RETURNS TABLE (id UUID, message_id TEXT, status TEXT, attachment_count INT,
                  accepted_attachment_count INT, rejected_attachment_count INT)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fsma, public, pg_temp
AS $fn$
BEGIN
    RETURN QUERY
    INSERT INTO fsma.inbound_email_audit AS a
        (tenant_id, message_id, sender, recipient, subject, status,
         rejection_reason, attachment_count, accepted_attachment_count,
         rejected_attachment_count, details)
    VALUES (p_tenant_id, p_message_id, p_sender, p_recipient, p_subject, p_status,
            p_rejection_reason, p_attachment_count, p_accepted_count, p_rejected_count, p_details)
    ON CONFLICT (message_id) DO NOTHING
    RETURNING a.id, a.message_id, a.status, a.attachment_count,
              a.accepted_attachment_count, a.rejected_attachment_count;
END;
$fn$;

REVOKE ALL ON FUNCTION fsma.record_inbound_email_audit(UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, INT, INT, INT, JSONB) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fsma.record_inbound_email_audit(UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, INT, INT, INT, JSONB) TO regengine;
```

`service.py` reads back an existing row by `message_id` first (a second
small `fsma.get_inbound_email_audit_by_message_id(p_message_id TEXT)`
SECURITY DEFINER function, same shape) *before* doing any attachment
processing — this is the idempotency guard: if Postmark redelivers the
same `MessageID` (e.g. because our process crashed after committing CSV
rows but before returning 200), we return the previously recorded summary
instead of re-ingesting the CSV a second time. `ON CONFLICT DO NOTHING`
on the insert is the second layer, for the race between two concurrent
deliveries of the same message.

This table intentionally has no RLS-visible tenant read path wired up
in this slice (no admin-UI endpoint to list rows) — that's a natural
follow-up, not required by the spec's four test scenarios. `FORCE ROW
LEVEL SECURITY` is *not* enabled on `inbound_email_audit` (unlike every
other new fsma table in this repo) precisely because of the nullable
`tenant_id`; the SECURITY DEFINER write functions are the enforcement
boundary instead, matching the `get_remediation_token_by_hash` bootstrap
precedent for exactly the same "no tenant context yet" problem.

## 4. Postmark payload schema — `schemas.py`

```python
class PostmarkAttachment(BaseModel):
    Name: str
    Content: str          # base64
    ContentType: str
    ContentLength: Optional[int] = None
    model_config = ConfigDict(extra="ignore")

class PostmarkInboundPayload(BaseModel):
    MessageID: str
    From: str
    To: Optional[str] = None
    ToFull: Optional[List[Dict[str, Any]]] = None
    OriginalRecipient: Optional[str] = None
    Subject: Optional[str] = None
    TextBody: Optional[str] = None
    Attachments: List[PostmarkAttachment] = Field(default_factory=list)
    model_config = ConfigDict(extra="ignore")  # tolerate Cc/Headers/HtmlBody/etc.

class AttachmentResult(BaseModel):
    name: str
    status: str            # "accepted" | "rejected"
    reason: Optional[str] = None
    rows_accepted: int = 0
    rows_rejected: int = 0

class InboundEmailResult(BaseModel):
    message_id: str
    status: str             # "accepted" | "partial" | "rejected"
    tenant_id: Optional[str] = None
    rejection_reason: Optional[str] = None
    attachments: List[AttachmentResult] = Field(default_factory=list)
```

Recipient extraction prefers `OriginalRecipient` (Postmark's documented
field for "which of the inbound stream's addresses this was sent to"),
then the first address in `ToFull`, then falls back to parsing `To` with
`email.utils.getaddresses` — a single email can be addressed to several
recipients; we use the first one that maps to a tenant.

## 5. Auth — `auth.py`

`grep`'d precedent: `webhook_router_v2/security.py` (`_verify_webhook_signature`,
HMAC over the raw body, secret from `WEBHOOK_HMAC_SECRET`) and
`services/shared/webhook_security.py` (HMAC + `hmac.compare_digest`,
env-configured secret, secret-rotation via a `_PREVIOUS` env var). Postmark's
inbound webhook, unlike Stripe/GitHub-style webhooks, does not sign its
POST body — the provider's own documented mechanism for securing an
inbound-parse endpoint is HTTP Basic Auth via credentials embedded in the
webhook URL Postmark is configured with. Per the spec, this design uses
Basic Auth (the real contract for this specific provider) but keeps every
other convention from the HMAC precedent: an env-configured secret,
`hmac.compare_digest` for a timing-safe comparison, a `logger.warning` on
each failure mirroring `webhook_signature_mismatch`, and a small
`email_inbound_auth_configured()` health helper mirroring
`webhook_hmac_configured()`.

```python
# services/ingestion/app/email_ingest/auth.py
import base64, hmac, logging, os
from fastapi import Header, HTTPException
from typing import Optional

logger = logging.getLogger("email-ingest.auth")

def _configured_credentials() -> Optional[tuple[str, str]]:
    user = os.getenv("EMAIL_INBOUND_BASIC_AUTH_USER", "").strip()
    password = os.getenv("EMAIL_INBOUND_BASIC_AUTH_PASSWORD", "").strip()
    return (user, password) if user and password else None

def email_inbound_auth_configured() -> bool:
    """Public helper for /health — mirrors webhook_hmac_configured()."""
    return _configured_credentials() is not None

async def verify_inbound_email_auth(
    authorization: Optional[str] = Header(default=None),
) -> None:
    creds = _configured_credentials()
    if creds is None:
        # Unlike WEBHOOK_HMAC_SECRET's fail-open migration ramp, this gate
        # fails CLOSED when unset: this endpoint writes compliance data
        # straight into ingestion, so there is no safe "skip auth" mode.
        logger.error("email_inbound_auth_not_configured")
        raise HTTPException(status_code=401, detail="Inbound email auth not configured")

    if not authorization or not authorization.lower().startswith("basic "):
        raise HTTPException(status_code=401, detail="Missing credentials",
                             headers={"WWW-Authenticate": "Basic"})
    try:
        decoded = base64.b64decode(authorization.split(" ", 1)[1], validate=True).decode("utf-8")
        user, _, password = decoded.partition(":")
    except Exception:
        logger.warning("email_inbound_auth_malformed_header")
        raise HTTPException(status_code=401, detail="Invalid credentials",
                             headers={"WWW-Authenticate": "Basic"})

    expected_user, expected_password = creds
    ok = hmac.compare_digest(user, expected_user) & hmac.compare_digest(password, expected_password)
    if not ok:
        logger.warning("email_inbound_auth_mismatch")
        raise HTTPException(status_code=401, detail="Invalid credentials",
                             headers={"WWW-Authenticate": "Basic"})
```

(`&` instead of `and` so both `compare_digest` calls always run — avoids a
username-existence timing side-channel; the calls are cheap so the
non-short-circuit is free.)

New env vars (documented in the migration's module docstring and in
whatever `.env.example` covers `WEBHOOK_HMAC_SECRET` today, not modified
by this change since none exists in-repo for that var either):
`EMAIL_INBOUND_BASIC_AUTH_USER`, `EMAIL_INBOUND_BASIC_AUTH_PASSWORD`.

## 6. Attachment security — reused in `service.py`

- **Size**: reuse `shared.upload_limits.MAX_CSV_FILE_SIZE_BYTES` (5 MB) as
  the cap on *decoded* attachment bytes — same ceiling the existing
  `/api/v1/ingest/csv` endpoint enforces, so an emailed CSV can't buy a
  bigger allowance than an uploaded one. Checked after `base64.b64decode`,
  before anything touches the DB.
- **Type allowlist**: CSV only. Reject when neither the sanitized
  filename's extension is `.csv` nor `ContentType` is one of
  `{"text/csv", "application/csv", "application/vnd.ms-excel"}` (Postmark/
  Outlook commonly mislabel CSV as the Excel MIME type). Reject reason is
  returned per-attachment (`unsupported_attachment_type: <name> (<content_type>)`)
  rather than silently dropped, per spec point 6.
- **No path traversal**: the attachment `Name` is never used as a
  filesystem path — it only ever becomes the in-memory `UploadFile.filename`
  passed to `ingest_csv` (which never writes to disk using the client
  filename) and a logged/audited string. It is still run through
  `shared.upload_limits.sanitize_upload_filename` before being stored in
  `details` / logs, for defense in depth and consistent behavior with
  every other upload path in this repo.
- **No code execution**: attachment bytes are only ever decoded and handed
  to `csv.DictReader` (via the reused `ingest_csv`) — never `eval`'d,
  never passed to a shell, never unzipped (no archive types are in the
  allowlist).
- **Malformed base64**: `base64.b64decode(content, validate=True)` — a
  `binascii.Error` becomes a per-attachment rejection
  (`invalid_base64_content`), not a 500.
- **Whole-email size**: Postmark's own inbound payload cap is 10 MB
  (documented provider limit); FastAPI's `PostmarkInboundPayload` is
  parsed from the JSON body FastAPI already reads via
  `RequestSizeLimitMiddleware` (referenced in
  `shared/upload_limits.read_request_body_with_limit`'s docstring) — no
  new body-size middleware is needed, but the router explicitly sets a
  request-level cap via that same middleware's existing configuration
  (confirm `RequestSizeLimitMiddleware` default covers webhook routes;
  if the mounted default is smaller than 10 MB it needs a path-specific
  override — flagged as an implementation-time check, not core to this
  design).

## 7. CSV reuse — no duplicated parsing logic

`app.csv_templates.ingest_csv` is an ordinary `async def` FastAPI route
function (not a bare-bones helper) — like `webhook_compat.ingest_events`,
it can be called directly as a plain function, bypassing HTTP/DI, by
supplying every parameter it would otherwise get from `Depends`/`Form`/
`Header`. `service.py` does exactly that instead of re-implementing CSV
parsing, row validation, KDE injection, or CTE persistence:

```python
from app.csv_templates import ingest_csv
from app.authz import IngestionPrincipal
from fastapi import UploadFile
import io

async def _ingest_attachment_csv(tenant_id: str, name: str, raw: bytes) -> AttachmentResult:
    principal = IngestionPrincipal(
        key_id="email-ingest",
        scopes=["webhooks.ingest"],
        tenant_id=tenant_id,
        auth_mode="email_inbound",
    )
    upload = UploadFile(io.BytesIO(raw), filename=name, size=len(raw))
    try:
        response = await ingest_csv(
            file=upload,
            cte_type=None,
            source="email_inbound",
            tenant_id=tenant_id,
            principal=principal,
            x_regengine_api_key=None,
            x_tenant_id=None,
        )
    except HTTPException as exc:
        return AttachmentResult(name=name, status="rejected", reason=str(exc.detail))
    return AttachmentResult(
        name=name,
        status="accepted" if response.accepted else "rejected",
        rows_accepted=response.accepted,
        rows_rejected=response.rejected,
    )
```

This means every existing CSV validation rule (CTE-type detection, UOM
normalization, date parsing, lot-code integrity warnings, KDE
completeness, the 500-row cap) applies to emailed CSVs automatically and
stays a single source of truth. `source="email_inbound"` flows straight
through to `CTEPersistence.store_event`'s `source` column, so accepted
events are distinguishable from portal/API/CSV-upload ingestion in
existing queries without any schema change.

## 8. Orchestration — `service.py`

```python
async def process_inbound_email(db_session, payload: PostmarkInboundPayload) -> InboundEmailResult:
    existing = get_inbound_email_audit_by_message_id(db_session, payload.MessageID)
    if existing:
        return _result_from_audit_row(existing)   # idempotent replay

    recipient = _first_recipient(payload)  # OriginalRecipient -> ToFull -> To
    tenant_id = lookup_tenant_by_inbound_address(db_session, recipient) if recipient else None

    if tenant_id is None:
        logger.warning("inbound_email_unmapped_recipient recipient=%s message_id=%s",
                        mask_email(recipient or ""), payload.MessageID)
        record_inbound_email_audit(db_session, tenant_id=None, message_id=payload.MessageID,
                                    sender=payload.From, recipient=recipient or "",
                                    subject=payload.Subject, status="rejected",
                                    rejection_reason="unmapped_recipient",
                                    attachment_count=len(payload.Attachments),
                                    accepted_count=0, rejected_count=0, details=[])
        return InboundEmailResult(message_id=payload.MessageID, status="rejected",
                                   rejection_reason="unmapped_recipient")

    set_tenant_guc(db_session, tenant_id)
    results: list[AttachmentResult] = []
    for attachment in payload.Attachments:
        results.append(await _process_one_attachment(tenant_id, attachment))

    accepted = sum(1 for r in results if r.status == "accepted")
    rejected = sum(1 for r in results if r.status == "rejected")
    status = "rejected" if payload.Attachments and accepted == 0 else (
        "partial" if rejected else "accepted"
    )
    record_inbound_email_audit(db_session, tenant_id=tenant_id, message_id=payload.MessageID,
                                sender=payload.From, recipient=recipient, subject=payload.Subject,
                                status=status, rejection_reason=None,
                                attachment_count=len(payload.Attachments),
                                accepted_count=accepted, rejected_count=rejected,
                                details=[r.model_dump() for r in results])
    return InboundEmailResult(message_id=payload.MessageID, status=status, tenant_id=tenant_id,
                               attachments=results)
```

`_process_one_attachment` applies the size/type/base64 checks from §6
before ever calling `_ingest_attachment_csv`.

## 9. Router — `router.py`

```python
router = APIRouter(prefix="/webhooks/email", tags=["Inbound Email"])

@router.post(
    "/inbound",
    response_model=InboundEmailResult,
    dependencies=[Depends(verify_inbound_email_auth)],
    summary="Postmark inbound-parse webhook",
)
async def receive_inbound_email(
    payload: PostmarkInboundPayload,
    db_session=Depends(get_db_session),
):
    if db_session is None:
        # Genuine transient failure — the only case this endpoint 5xxs on,
        # so Postmark's retry-on-5xx actually helps instead of hammering
        # a dead DB with duplicate CSV ingestion.
        raise HTTPException(status_code=503, detail="Database unavailable")
    return await process_inbound_email(db_session, payload)
```

Every rejection path (unmapped recipient, oversized/wrong-type/undecodable
attachment, zero valid CSV rows) returns **200** with a structured body —
matching spec point 3 ("reject/log-and-200 ... provider webhooks retry on
5xx"). Only a missing/invalid `Authorization` header (401) and DB
unavailability (503) are non-200, both of which are things a retry either
should trigger (transient DB outage) or an operator needs to fix (auth
misconfiguration) rather than something Postmark endlessly retrying would
paper over.

## 10. Mounting in `services/ingestion/main.py`

Follows the existing `_router_enabled(name)` feature-flag convention
(same as `remediation`, `csv`, etc.):

```python
_VALID_ROUTER_NAMES = {
    ...,
    "email_ingest",   # add to the set around line 171-221
}
```

```python
# Inbound Email Ingestion (Postmark inbound-parse webhook)
if _router_enabled("email_ingest"):
    from app.email_ingest.router import router as email_ingest_router

    app.include_router(email_ingest_router, tags=["Inbound Email"])
```

Not added to `_COMPLIANCE_ROUTERS` — unlike `remediation`/`fda_export`,
disabling inbound email cannot corrupt or hide already-ingested
compliance data; it only stops accepting a new input channel.

## 11. Config / env vars introduced

| Env var | Purpose | Required in prod |
|---|---|---|
| `EMAIL_INBOUND_BASIC_AUTH_USER` | Basic-Auth username the webhook must present | yes (fail-closed if unset) |
| `EMAIL_INBOUND_BASIC_AUTH_PASSWORD` | Basic-Auth password | yes (fail-closed if unset) |

No new third-party dependency: `base64`, `binascii`, `email.utils`, `csv`,
`io` are all stdlib; DB access reuses `shared.database.get_db_session` and
`shared.tenant_context.set_tenant_guc`, already in `requirements.lock`.

## 12. Tests — `services/ingestion/tests/test_email_ingest_router.py`

Style follows `test_csv_templates_1342.py` / `test_stripe_webhooks_1342.py`
(monkeypatch-based, `FastAPI()` + `TestClient`, `app.dependency_overrides`
for `get_db_session`, no live DB). `tenant_lookup.lookup_tenant_by_inbound_address`
and `service.record_inbound_email_audit` /
`service.get_inbound_email_audit_by_message_id` are monkeypatched directly
(same pattern `test_csv_templates_1342.py` uses for `ingest_events`), and
`app.csv_templates.ingest_csv` is monkeypatched to return a canned
`CsvIngestResponse` for the "valid CSV" case so the test never touches
`CTEPersistence`/Postgres.

Required scenarios (spec point 7):

1. **Valid CSV attachment, end-to-end (mocked)** — Basic Auth present and
   correct, recipient maps to a tenant (mocked), one `.csv` attachment,
   `ingest_csv` mocked to report `accepted=2, rejected=0` → 200,
   `status="accepted"`, one audit-record call with `status="accepted"`.
2. **Unmapped recipient rejected safely** — Basic Auth correct,
   `lookup_tenant_by_inbound_address` mocked to return `None` → 200,
   `status="rejected"`, `rejection_reason="unmapped_recipient"`, and the
   audit-record call is asserted to have been made with `tenant_id=None`
   (never a 500).
3. **Oversized / wrong-type attachment rejected** — two sub-cases: (a) a
   `.pdf`/`ContentType="application/pdf"` attachment → per-attachment
   `status="rejected"`, `reason` mentions `unsupported_attachment_type`;
   (b) a `.csv` attachment whose base64-decoded size exceeds
   `MAX_CSV_FILE_SIZE_BYTES` → `reason` mentions the size limit. Both
   assert overall response is still 200 and `ingest_csv` is never called
   for the rejected attachment (proves the size/type gate runs before the
   reuse boundary, not after).
4. **Auth-missing request rejected** — no `Authorization` header (and,
   separately, a wrong-credentials header) → 401, and `process_inbound_email`
   / `ingest_csv` are asserted never called (proves auth is a hard gate
   before any DB or ingestion work).

`services/ingestion/tests/test_email_ingest_service.py` covers
`service.py` unit-level: recipient extraction precedence
(`OriginalRecipient` > `ToFull` > `To`), the idempotent-replay short
circuit when `get_inbound_email_audit_by_message_id` returns a row, and
the `accepted`/`partial`/`rejected` status rollup math for mixed
attachment outcomes (e.g. 2 accepted + 1 rejected → `"partial"`; 0
attachments → `"accepted"` since an email with only a `TextBody` and no
attachments isn't a failure).

Run via (per repo convention, root of the worktree):

```
cd /home/user/wt-email-ingestion
source /home/user/RegEngine/venv/bin/activate
pytest services/ingestion/tests/test_email_ingest_router.py services/ingestion/tests/test_email_ingest_service.py -v
```

## 13. Deviations from the spec, and why

1. **Schema name**: `fsma.*` instead of the spec's example `ingestion.*`
   — no `ingestion` schema exists anywhere in `alembic/versions/`; every
   comparable table (`manifest_blobs`, `remediation_cases`,
   `notification_outbox`, `ingestion_runs`) lives in `fsma`. Using
   `ingestion.tenant_inbound_addresses` would be the first table in a
   brand-new schema for no benefit.
2. **Auth mechanism is HTTP Basic, not HMAC**, even though every existing
   *webhook* auth pattern in this repo (`webhook_router_v2/security.py`,
   `shared/webhook_security.py`) is HMAC-over-body. This is what the spec
   itself asks for, and it matches Postmark's actual inbound-webhook
   contract (Postmark does not sign inbound POSTs; its documented
   security mechanism for an inbound-parse endpoint is Basic Auth via the
   webhook URL). The *style* is still reused: env-configured secret,
   `hmac.compare_digest`, structured warning logs on failure, and a
   `..._configured()` health helper mirroring `webhook_hmac_configured()`.
   One deliberate divergence from the `WEBHOOK_HMAC_SECRET` precedent:
   that gate fails **open** (skips verification) when the secret is
   unset, to support a migration ramp; this gate fails **closed**
   (401s every request) when unset, because there is no safe unauthenticated
   mode for an endpoint that writes directly into compliance ingestion —
   flagging this explicitly since it's a one-line change in `auth.py` if
   a ramp period is wanted instead.
3. **Audit table has a nullable `tenant_id` and skips `FORCE ROW LEVEL
   SECURITY`**, unlike every other new `fsma` table in this repo's recent
   migrations. This is required by point 5's own requirement that
   unmapped-recipient emails still be audited, combined with the FORCE-RLS
   convention's `tenant_id = get_tenant_context()` policy having no
   value to compare against for those rows. The SECURITY DEFINER
   write/read functions (mirroring the `get_remediation_token_by_hash`
   and `seed_obligations_for_tenant` precedents already in this repo) are
   the enforcement boundary instead of a table-level policy.
4. **Idempotency via a unique `message_id`** was not explicitly requested
   by the spec but is added because point 3's own justification
   ("provider webhooks retry on 5xx") implies retries are expected
   behavior this endpoint must handle safely; without it, a retry after a
   crash between "CSV rows committed" and "200 returned" would double-
   ingest CTE events. This is the smallest change that closes that gap
   (one unique index + a read-before-process check), not a full outbox/
   claim system like `remediation/delivery.py`'s (which solves a
   different problem — draining a queue under concurrent workers).

   **Known residual gap, found in self-review**: the `message_id` guard is
   read-then-act, not claim-then-act — two genuinely *concurrent* deliveries
   of the same `MessageID` both read "no existing audit row" before either
   has written one, so both proceed to run CSV ingestion independently.
   `ON CONFLICT (message_id) DO NOTHING` on the audit insert only prevents a
   second *audit row*; it does nothing to stop the CTE events themselves
   from being persisted twice by the two racing requests. Closing that
   fully would need a claim row inserted *before* attachment processing
   starts (and a schema change, since `status` is `CHECK`-constrained to
   `accepted|partial|rejected`, not e.g. `processing`) — out of scope for
   this slice; sequential redelivery after a crash (the scenario point 3
   actually motivates) is what the current guard covers.

5. **`_ingest_attachment_csv` passes a non-empty sentinel for
   `x_regengine_api_key`, not `None`** (fixed in self-review — see git log).
   `app.csv_templates.ingest_csv` forwards this header, unmodified, into
   `webhook_compat.ingest_events`, whose very first statement is
   `webhook_router_v2._verify_api_key_present` — a presence-only check
   ("if not x_regengine_api_key: raise HTTPException(401)", per its own
   docstring it never validates the value). Passing `None` — the literal
   value used by an unauthenticated caller with no header at all — meant
   every real attachment was unconditionally 401'd before ever reaching
   CTEPersistence, silently reported back as a per-attachment "rejected"
   result. This was not caught by `test_email_ingest_service.py` because
   its `_ingest_attachment_csv` happy-path test monkeypatches
   `ingest_csv` itself, bypassing the real call chain entirely; a new test
   exercises the real `ingest_csv` (only its `ingest_events` call
   stubbed) to catch a regression here. Real authorization for this call
   already happens via `verify_inbound_email_auth`'s Basic-Auth gate plus
   the explicitly-constructed `principal` — the sentinel only satisfies
   this unrelated defense-in-depth header check.

6. **`_ingest_attachment_csv` now catches `Exception`, not just
   `HTTPException`** (fixed in self-review). The reused
   `app.csv_templates.ingest_csv` has at least one un-guarded call
   (`content.decode("utf-8-sig")`, for a non-UTF-8 attachment — plausible
   for a real Excel/Outlook-authored CSV) that can raise a plain
   exception rather than an `HTTPException`. Uncaught, that exception
   would previously propagate out of `process_inbound_email` before the
   email-level audit row is written, producing an unhandled 500 for the
   *whole* email (not just the one bad attachment) with **no audit
   trail** — violating point 5's "must be auditable" requirement — and,
   on the resulting Postmark retry, causing every attachment that had
   already been accepted earlier in the same request's loop to be
   re-ingested (the idempotency guard in point 4 above only helps once an
   audit row exists; it does nothing for a mid-request crash that leaves
   no row at all). The handler now logs the exception and returns a
   per-attachment "rejected" result instead, matching section 9's stated
   intent that only auth failure and total DB unavailability are non-200.

## 14. Out of scope (explicitly not built here)

- No admin/tenant-facing CRUD endpoint for
  `fsma.tenant_inbound_addresses` (rows are seeded directly for now, e.g.
  via a one-off `INSERT` or a follow-up admin endpoint) — the spec asks
  only for the mapping table and the webhook, not tenant self-service UI.
- No SendGrid/Mailgun adapters — Postmark's shape only, per spec.
- No non-CSV attachment formats (PDF/XLSX ingestion) — CSV-only allowlist
  per spec point 6.
- No outbound acknowledgement email to the sender on rejection — spec
  asks for log-and-200, not a reply.

## 15. Security hardening (post-review, migration v122)

An independent security review of this branch found two real gaps before
it shipped anywhere; both are closed in `alembic/versions/20260912_d14f8a2b9c31_v122_email_ingestion_hardening.py`
plus the corresponding `service.py`/`tenant_lookup.py` changes.

1. **No sender authentication (high).** Sections 3.1 and 14 above describe
   tenant resolution purely from the recipient address, with inbound
   addresses "seeded directly ... e.g. via a one-off `INSERT`" and no
   stated entropy requirement. Postmark's Basic-Auth webhook credential
   authenticates the transport ("this call came from Postmark"), not the
   original email's sender — Postmark forwards *any* internet sender's
   mail addressed to a configured inbound address using that same shared
   credential. Combined, the entire cross-tenant boundary reduced to
   "knows/guesses one string," and once ingested, `source="email_inbound"`
   events went through the same merkle-chained `CTEPersistence` path as
   authenticated API/portal submissions.

   Fix: `fsma.tenant_inbound_addresses` gains `allowed_senders TEXT[]`.
   `fsma.get_tenant_by_inbound_address` now takes the email's `From`
   address as a second argument and only resolves a tenant when the sender
   matches an allowlist entry (`user@example.com` verbatim, or `@example.com`
   as a domain suffix). **A row with an empty allowlist authorizes no
   sender at all** — fail closed, not fail open — so every already-seeded
   v121 row (all of which predate this column) denies every sender until
   an operator explicitly populates it. `tenant_lookup.lookup_tenant_by_inbound_address`
   and `service.process_inbound_email` were updated accordingly
   (`service._sender_address` extracts the bare address from `payload.From`
   via `email.utils.parseaddr`, same shape as `_first_recipient`'s
   reliance on `email.utils`).

   Deliberately NOT built as part of this fix: an admin/tenant-facing UI to
   manage `allowed_senders` (same "seeded directly for now" scoping as
   section 14 already accepts for the table as a whole), and a
   quarantine/human-review queue for accepted email-sourced events beyond
   the `source="email_inbound"` tag `CTEPersistence` already carries. Both
   are reasonable follow-ups flagged by the review but are separate,
   larger pieces of work from "authenticate the sender."

2. **Read-then-act idempotency race (medium).** Documented as a known
   residual gap in section 13 item 4 above: two genuinely concurrent
   deliveries of the same `MessageID` could both observe "no audit row
   yet" (via `get_inbound_email_audit_by_message_id`) before either had
   written one, so both proceeded to run `_ingest_attachment_csv` against
   the same CSV — `ON CONFLICT (message_id) DO NOTHING` on the old
   single-statement `record_inbound_email_audit` only deduplicated the
   *audit row*, after the fact, not the CTE events themselves.

   Fix: claim-then-act, mirroring the `NotificationOutboxDrainer._claim()`
   pattern already used by `app/remediation/delivery.py` for the identical
   "make double-processing structurally impossible" problem (an atomic
   `UPDATE ... WHERE status = 'queued' ...` there; an atomic
   `INSERT ... ON CONFLICT DO NOTHING` here, since the audit row doesn't
   exist yet at claim time). `status` gains a `'processing'` value.
   `fsma.claim_inbound_email_audit` inserts the row as `status='processing'`
   — the *first* write `process_inbound_email` makes, before any attachment
   reaches CSV ingestion; losing that race (`NULL` back from `ON CONFLICT
   DO NOTHING`) means another request already owns this exact `MessageID`,
   so this request must not run ingestion at all. `fsma.finalize_inbound_email_audit`
   then updates that same row to its real outcome, guarded by
   `status = 'processing'` so it only ever touches the row its own claim
   produced. `fsma.record_inbound_email_audit` is removed; nothing else
   called it.

   A request that loses the claim race re-reads the audit row: if the
   winner has since finished, the loser replays that recorded result
   (unchanged idempotent-replay behavior); if the winner is still mid-flight,
   the loser returns **409** rather than fabricate a result or double-run
   ingestion — Postmark's own retry-on-non-2xx contract (section 9) is
   exactly the mechanism that recovers from that 409 once the winner
   commits.

   A session-level `pg_advisory_lock` (rather than a claim row) was
   considered and rejected: `services/scheduler/app/distributed.py`'s own
   comments document a real production incident class where a session-level
   advisory lock held across multiple commits leaked onto a pooled
   connection when it wasn't released on every exit path (#2882). This
   endpoint's `db_session` is an ordinary per-request pooled session, not
   the dedicated long-lived connection `distributed.py` manages specifically
   to make that pattern safe, so the claim-row approach (already proven
   safe under pooling by `remediation/delivery.py`) was used instead.
   `pg_advisory_xact_lock` (used elsewhere in this repo for chain-append
   races, e.g. `cte_persistence/writes.py`) was also considered and
   rejected for this specific function: it releases at the next `COMMIT`,
   and `process_inbound_email`'s own control flow already commits more than
   once before attachment processing finishes (`tenant_lookup`'s bootstrap
   lookup commits to release its transaction-local GUCs), so a
   transaction-scoped lock taken up front would already be gone by the time
   CSV ingestion runs.

3. **Unsanitized `MessageID` in a log line (low).** `payload.MessageID` was
   interpolated into `logger.warning(...)` unlike every other
   payload-derived value in this module (`sanitize_upload_filename` for
   attachment names, `mask_email` for the recipient). Fixed with a small
   `service._sanitize_log_value` helper (strips control characters
   including CR/LF, caps length at 200 chars) applied to `MessageID`
   wherever it reaches a log line.
