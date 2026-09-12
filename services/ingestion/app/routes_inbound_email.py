"""Inbound email ingestion — Postmark Inbound Parse webhook.

Lets a supplier email FSMA 204 traceability data as a CSV attachment
instead of using the ``/api/v1/ingest/csv`` upload endpoint or the API
directly. Postmark receives mail for a domain/address a tenant has
registered, converts it to JSON, and POSTs it here.

Two concerns, two auth mechanisms:

* The webhook itself (``POST /api/v1/webhooks/inbound-email``) is called by
  Postmark, not by an authenticated RegEngine tenant, so it is protected by
  HTTP Basic Auth on the URL (Postmark's own supported mechanism —
  https://postmarkapp.com/support/article/800-ingest-an-email-with-inbound-processing)
  rather than an ``X-RegEngine-API-Key``.
* Which *tenant* an inbound email belongs to is resolved per-message from
  its recipient address via a registered mapping
  (``fsma.tenant_inbound_email_addresses`` / ``get_tenant_by_inbound_address``),
  the same "authenticated by a bound identifier rather than a caller
  credential" shape as ``supplier_portal.py``'s token-bound links. The
  address-registration endpoints below use the normal
  ``require_permission("webhooks.ingest")`` tenant auth so only a tenant's
  own credential can register or revoke *its* addresses.

CSV extraction reuses ``csv_templates.parse_csv_rows`` — the exact function
the ``/ingest/csv`` upload route uses — so an emailed attachment produces
identical ``IngestEvent``s to the same CSV uploaded directly.

A malformed or unrecognized email must never crash the webhook or silently
disappear: parsing/validation failures are recorded via
``inbound_email_rejection_log`` and the webhook still returns 200 so
Postmark does not endlessly retry a delivery that will never parse
differently. A transient failure (e.g. the database is unreachable) is
allowed to raise, so Postmark's retry schedule can succeed once the
transient condition clears — see Postmark's inbound-webhook retry docs.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import logging
import os
from email.utils import parseaddr
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from shared.database import get_db_safe
from shared.env import is_production
from shared.tenant_context import tenant_scope
from sqlalchemy import text

from .authz import IngestionPrincipal, require_permission
from .csv_templates import parse_csv_rows
from .inbound_email_rejection_log import list_inbound_email_rejections, record_inbound_email_rejection
from .shared.tenant_resolution import resolve_principal_tenant_id
from .shared.upload_limits import MAX_CSV_FILE_SIZE_BYTES
from .webhook_compat import ingest_events
from .webhook_models import WebhookPayload

logger = logging.getLogger("inbound-email-webhook")

router = APIRouter(prefix="/api/v1/webhooks/inbound-email", tags=["Inbound Email Webhook"])

_CSV_CONTENT_TYPE_HINTS = ("csv", "text/plain", "text/comma-separated-values")


# ---------------------------------------------------------------------------
# Basic Auth for the Postmark-facing webhook
# ---------------------------------------------------------------------------


def _postmark_credentials() -> Optional[tuple[str, str]]:
    user = os.getenv("POSTMARK_INBOUND_WEBHOOK_USER", "")
    password = os.getenv("POSTMARK_INBOUND_WEBHOOK_PASSWORD", "")
    if not user or not password:
        return None
    return user, password


async def _verify_postmark_basic_auth(
    authorization: Optional[str] = Header(default=None),
) -> None:
    """Require HTTP Basic Auth matching POSTMARK_INBOUND_WEBHOOK_USER/PASSWORD.

    Postmark supports embedding Basic Auth credentials directly in the
    registered webhook URL (https://user:pass@host/path), which is the
    mechanism this checks against.
    """
    configured = _postmark_credentials()
    if configured is None:
        if is_production():
            logger.error("inbound_email_webhook_not_configured")
            raise HTTPException(status_code=503, detail="Inbound email webhook is not configured")
        logger.warning("inbound_email_webhook_auth_skipped_dev_no_credentials_configured")
        return

    expected_user, expected_password = configured

    if not authorization or not authorization.startswith("Basic "):
        raise HTTPException(
            status_code=401,
            detail="Missing credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    try:
        decoded = base64.b64decode(authorization[len("Basic ") :], validate=True).decode("utf-8")
        provided_user, _, provided_password = decoded.partition(":")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        ) from None

    user_ok = hmac.compare_digest(provided_user, expected_user)
    password_ok = hmac.compare_digest(provided_password, expected_password)
    if not (user_ok and password_ok):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


# ---------------------------------------------------------------------------
# Tenant resolution: registered inbound address -> tenant_id
# ---------------------------------------------------------------------------


class TenantLookupUnavailable(RuntimeError):
    """The address→tenant lookup could not be performed at all (database
    unavailable, or the query itself errored) — distinct from a completed
    lookup that found no registered tenant. Callers must let this
    propagate rather than quarantine it as "unknown recipient": a DB blip
    is a transient condition Postmark should retry, not a reason to
    silently drop a legitimate supplier's email.
    """


def _db_get_tenant_by_inbound_address(address: str) -> Optional[str]:
    """Resolve a recipient address to a tenant_id.

    Returns None only when the lookup completed and found no tenant
    registered for that address. Raises TenantLookupUnavailable if the
    lookup itself could not be performed.
    """
    db = get_db_safe()
    if not db:
        raise TenantLookupUnavailable("database unavailable")
    try:
        row = db.execute(
            # nosemgrep: avoid-sqlalchemy-text — SECURITY DEFINER function, parameterized address
            text("SELECT tenant_id FROM fsma.get_tenant_by_inbound_address(:address)"),
            {"address": address},
        ).fetchone()
        return str(row[0]) if row else None
    except Exception as exc:
        db.rollback()
        logger.error("inbound_email_tenant_lookup_failed error=%s", str(exc))
        raise TenantLookupUnavailable(f"tenant lookup query failed: {exc}") from exc
    finally:
        db.close()


def _extract_recipient(payload: dict) -> Optional[str]:
    """Prefer Postmark's OriginalRecipient (the exact address mail was sent
    to before any alias/forwarding); fall back to the first address in To.
    """
    original = payload.get("OriginalRecipient")
    if original:
        _, addr = parseaddr(str(original))
        if addr:
            return addr
    to_field = payload.get("To") or ""
    first = str(to_field).split(",")[0]
    _, addr = parseaddr(first)
    return addr or None


def _find_csv_attachment(attachments: list[dict]) -> Optional[dict]:
    for att in attachments:
        name = str(att.get("Name") or "")
        content_type = str(att.get("ContentType") or "").lower()
        if name.lower().endswith(".csv") or any(hint in content_type for hint in _CSV_CONTENT_TYPE_HINTS):
            return att
    return None


# ---------------------------------------------------------------------------
# Address registration (tenant self-service, normal API-key auth)
# ---------------------------------------------------------------------------


class RegisterInboundAddressRequest(BaseModel):
    inbound_address: str = Field(..., min_length=3, description="Recipient address to route to this tenant")


class InboundAddressResponse(BaseModel):
    inbound_address: str
    tenant_id: str
    status: str


@router.post(
    "/addresses",
    response_model=InboundAddressResponse,
    summary="Register an inbound email address for this tenant",
    description="Emails sent to this address will be parsed as FSMA 204 CSV ingestion for this tenant.",
)
async def register_inbound_address(
    request: RegisterInboundAddressRequest,
    principal: IngestionPrincipal = Depends(require_permission("webhooks.ingest")),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> InboundAddressResponse:
    tenant_id = resolve_principal_tenant_id(None, x_tenant_id, principal.tenant_id)
    address = request.inbound_address.strip().lower()
    _, parsed_addr = parseaddr(address)
    if not parsed_addr or "@" not in parsed_addr:
        raise HTTPException(status_code=400, detail="inbound_address must be a valid email address")

    db = get_db_safe()
    if not db:
        raise HTTPException(status_code=503, detail="Address registration is temporarily unavailable")
    try:
        with tenant_scope(tenant_id):
            db.execute(
                # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
                text("""
                    INSERT INTO fsma.tenant_inbound_email_addresses (tenant_id, inbound_address, status)
                    VALUES (CAST(:tenant_id AS uuid), :address, 'active')
                    ON CONFLICT (LOWER(inbound_address)) DO UPDATE SET status = 'active'
                    WHERE fsma.tenant_inbound_email_addresses.tenant_id = CAST(:tenant_id AS uuid)
                """),
                {"tenant_id": tenant_id, "address": parsed_addr},
            )
            db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("inbound_email_address_register_failed error=%s", str(exc))
        raise HTTPException(status_code=409, detail="That address is already registered to another tenant") from None
    finally:
        db.close()

    return InboundAddressResponse(inbound_address=parsed_addr, tenant_id=tenant_id, status="active")


@router.get(
    "/rejections",
    summary="List quarantined inbound emails for this tenant",
    description="Emails that could not be parsed into FSMA 204 events, for manual review.",
)
async def list_rejections(
    principal: IngestionPrincipal = Depends(require_permission("webhooks.ingest")),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> dict:
    tenant_id = resolve_principal_tenant_id(None, x_tenant_id, principal.tenant_id)
    return {"tenant_id": tenant_id, "rejections": list_inbound_email_rejections(tenant_id)}


# ---------------------------------------------------------------------------
# The Postmark-facing webhook
# ---------------------------------------------------------------------------


@router.post(
    "",
    summary="Postmark Inbound Parse webhook",
    description=(
        "Receives Postmark's Inbound Parse JSON payload, resolves the owning tenant from the "
        "recipient address, and ingests any CSV attachment as FSMA 204 CTE events."
    ),
)
async def receive_inbound_email(
    request: Request,
    _auth: None = Depends(_verify_postmark_basic_auth),
) -> dict[str, Any]:
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("payload is not a JSON object")
    except Exception as exc:
        # Malformed JSON is a permanent, not transient, failure: record and
        # 200 so Postmark does not retry a body that will never parse.
        record_inbound_email_rejection(
            tenant_id=None,
            reason="invalid_json",
            detail=f"Could not parse webhook body as JSON: {exc}",
        )
        return {"status": "quarantined", "reason": "invalid_json"}

    sender = str(payload.get("From") or "") or None
    subject = str(payload.get("Subject") or "") or None
    recipient = _extract_recipient(payload)

    if not recipient:
        record_inbound_email_rejection(
            tenant_id=None,
            reason="missing_recipient",
            detail="Payload had no usable To/OriginalRecipient address",
            sender=sender,
            subject=subject,
        )
        return {"status": "quarantined", "reason": "missing_recipient"}

    tenant_id = _db_get_tenant_by_inbound_address(recipient)
    if not tenant_id:
        record_inbound_email_rejection(
            tenant_id=None,
            reason="unknown_recipient",
            detail=f"No tenant is registered for recipient address {recipient!r}",
            sender=sender,
            recipient=recipient,
            subject=subject,
        )
        return {"status": "quarantined", "reason": "unknown_recipient"}

    attachments = payload.get("Attachments") or []
    if not isinstance(attachments, list):
        attachments = []
    csv_attachment = _find_csv_attachment(attachments)
    if not csv_attachment:
        record_inbound_email_rejection(
            tenant_id=tenant_id,
            reason="no_csv_attachment",
            detail="Email had no CSV attachment to ingest",
            sender=sender,
            recipient=recipient,
            subject=subject,
        )
        return {"status": "quarantined", "reason": "no_csv_attachment"}

    try:
        raw_content = base64.b64decode(csv_attachment.get("Content") or "", validate=True)
    except (binascii.Error, ValueError) as exc:
        record_inbound_email_rejection(
            tenant_id=tenant_id,
            reason="attachment_decode_failed",
            detail=f"Attachment content was not valid base64: {exc}",
            sender=sender,
            recipient=recipient,
            subject=subject,
        )
        return {"status": "quarantined", "reason": "attachment_decode_failed"}

    if len(raw_content) > MAX_CSV_FILE_SIZE_BYTES:
        record_inbound_email_rejection(
            tenant_id=tenant_id,
            reason="attachment_too_large",
            detail=f"Attachment was {len(raw_content)} bytes (limit {MAX_CSV_FILE_SIZE_BYTES})",
            sender=sender,
            recipient=recipient,
            subject=subject,
        )
        return {"status": "quarantined", "reason": "attachment_too_large"}

    try:
        text_content = raw_content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        record_inbound_email_rejection(
            tenant_id=tenant_id,
            reason="attachment_decode_failed",
            detail=f"Attachment was not valid UTF-8 text: {exc}",
            sender=sender,
            recipient=recipient,
            subject=subject,
        )
        return {"status": "quarantined", "reason": "attachment_decode_failed"}

    events, parse_errors, kde_warnings = parse_csv_rows(text_content, fallback_cte=None)

    if not events:
        record_inbound_email_rejection(
            tenant_id=tenant_id,
            reason="no_valid_rows",
            detail="CSV attachment contained no rows that could be parsed into CTE events",
            sender=sender,
            recipient=recipient,
            subject=subject,
            errors=parse_errors,
        )
        return {"status": "quarantined", "reason": "no_valid_rows", "errors": parse_errors[:20]}

    if kde_warnings:
        logger.warning(
            "inbound_email_kde_warnings tenant=%s count=%d: %s",
            tenant_id,
            len(kde_warnings),
            "; ".join(kde_warnings[:5]),
        )

    payload_obj = WebhookPayload(source="inbound_email", events=events, tenant_id=tenant_id)

    # From here on, failures are database/persistence concerns, not data
    # concerns — let them raise so Postmark retries once the transient
    # condition (e.g. DB unavailable) clears, rather than swallowing them
    # into the quarantine log where they would silently look identical to a
    # permanently-unparseable email.
    with tenant_scope(tenant_id):
        result = await ingest_events(payload_obj, principal_tenant_id=tenant_id)

    if parse_errors:
        logger.warning(
            "inbound_email_partial_parse_errors tenant=%s count=%d: %s",
            tenant_id,
            len(parse_errors),
            "; ".join(parse_errors[:5]),
        )

    logger.info(
        "inbound_email_ingest_complete tenant=%s accepted=%d rejected=%d",
        tenant_id,
        result.accepted,
        result.rejected,
    )

    return {
        "status": "accepted",
        "tenant_id": tenant_id,
        "accepted": result.accepted,
        "rejected": result.rejected,
        "parse_errors": parse_errors[:20],
    }
