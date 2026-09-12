"""Orchestration for the inbound-email ingestion pipeline.

``process_inbound_email`` ties together: idempotent-replay lookup, tenant
resolution from the recipient address, per-attachment size/type/base64
validation, reuse of ``app.csv_templates.ingest_csv`` for CSV parsing, and
persistence of one audit row per email — see ``DESIGN_email-ingestion.md``
sections 6-8.

No duplicated CSV-parsing logic: ``app.csv_templates.ingest_csv`` is an
ordinary ``async def`` FastAPI route function (not a bare-bones helper) —
like ``webhook_compat.ingest_events``, it can be called directly as a plain
function, bypassing HTTP/DI, by supplying every parameter it would otherwise
get from ``Depends``/``Form``/``Header``. This means every existing CSV
validation rule (CTE-type detection, UOM normalization, date parsing,
lot-code integrity warnings, KDE completeness, the 500-row cap) applies to
emailed CSVs automatically and stays a single source of truth.
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import logging
from email.utils import getaddresses
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, UploadFile
from shared.pii import mask_email
from shared.tenant_context import set_tenant_guc
from sqlalchemy import text

from ..authz import IngestionPrincipal
from ..csv_templates import ingest_csv
from ..shared.upload_limits import MAX_CSV_FILE_SIZE_BYTES, sanitize_upload_filename
from . import tenant_lookup
from .schemas import AttachmentResult, InboundEmailResult, PostmarkAttachment, PostmarkInboundPayload

logger = logging.getLogger("email-ingest.service")

# Postmark/Outlook commonly mislabel CSV as the Excel MIME type, so both are
# accepted alongside the two literal CSV content types.
_ALLOWED_ATTACHMENT_CONTENT_TYPES = {"text/csv", "application/csv", "application/vnd.ms-excel"}


# ---------------------------------------------------------------------------
# Recipient extraction
# ---------------------------------------------------------------------------


def _first_recipient(payload: PostmarkInboundPayload) -> Optional[str]:
    """Recipient extraction precedence: ``OriginalRecipient`` > ``ToFull`` > ``To``.

    A single email can be addressed to several recipients; Postmark's
    ``OriginalRecipient`` documents which of the inbound stream's addresses
    this delivery matched, so it's authoritative when present. ``ToFull`` is
    the structured fallback; a bare ``To`` header is parsed with
    ``email.utils.getaddresses`` (handles ``"Name" <addr>, addr2`` shapes) as
    the last resort, using the first address that resolves.
    """
    if payload.OriginalRecipient and payload.OriginalRecipient.strip():
        return payload.OriginalRecipient.strip()

    if payload.ToFull:
        for entry in payload.ToFull:
            addr = entry.get("Email") or entry.get("email")
            if addr and str(addr).strip():
                return str(addr).strip()

    if payload.To:
        for _, addr in getaddresses([payload.To]):
            if addr:
                return addr.strip()

    return None


# ---------------------------------------------------------------------------
# Audit persistence (SECURITY DEFINER functions from migration v121)
# ---------------------------------------------------------------------------


def get_inbound_email_audit_by_message_id(db, message_id: str) -> Optional[Dict[str, Any]]:
    """Idempotency read: does an audit row for this ``message_id`` already exist?

    Checked first in ``process_inbound_email`` — before any attachment
    processing — so a provider redelivery (e.g. our process crashed after
    committing CSV rows but before returning 200) replays the previously
    recorded summary instead of re-running CSV ingestion a second time.
    """
    row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — SECURITY DEFINER function, parameterized message_id
        text(
            """
            SELECT id, tenant_id, message_id, sender, recipient, subject, status,
                   rejection_reason, attachment_count, accepted_attachment_count,
                   rejected_attachment_count, details, received_at
            FROM fsma.get_inbound_email_audit_by_message_id(:p_message_id)
            """
        ),
        {"p_message_id": message_id},
    ).fetchone()
    if not row:
        return None
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id) if row.tenant_id else None,
        "message_id": row.message_id,
        "sender": row.sender,
        "recipient": row.recipient,
        "subject": row.subject,
        "status": row.status,
        "rejection_reason": row.rejection_reason,
        "attachment_count": row.attachment_count,
        "accepted_attachment_count": row.accepted_attachment_count,
        "rejected_attachment_count": row.rejected_attachment_count,
        "details": row.details if isinstance(row.details, list) else json.loads(row.details or "[]"),
        "received_at": row.received_at,
    }


def record_inbound_email_audit(
    db,
    *,
    tenant_id: Optional[str],
    message_id: str,
    sender: str,
    recipient: str,
    subject: Optional[str],
    status: str,
    rejection_reason: Optional[str],
    attachment_count: int,
    accepted_count: int,
    rejected_count: int,
    details: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Insert one audit row via the SECURITY DEFINER write function.

    ``ON CONFLICT (message_id) DO NOTHING`` in the underlying function means
    this returns ``None`` on the (rare) race between two concurrent
    deliveries of the same message — the caller should treat that as "someone
    else recorded it" and, if it needs the row, re-read it with
    ``get_inbound_email_audit_by_message_id``.
    """
    row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — SECURITY DEFINER function, parameterized inputs
        text(
            """
            SELECT id, message_id, status, attachment_count,
                   accepted_attachment_count, rejected_attachment_count
            FROM fsma.record_inbound_email_audit(
                :p_tenant_id, :p_message_id, :p_sender, :p_recipient, :p_subject,
                :p_status, :p_rejection_reason, :p_attachment_count,
                :p_accepted_count, :p_rejected_count, :p_details::jsonb
            )
            """
        ),
        {
            "p_tenant_id": tenant_id,
            "p_message_id": message_id,
            "p_sender": sender,
            "p_recipient": recipient,
            "p_subject": subject,
            "p_status": status,
            "p_rejection_reason": rejection_reason,
            "p_attachment_count": attachment_count,
            "p_accepted_count": accepted_count,
            "p_rejected_count": rejected_count,
            "p_details": json.dumps(details, default=str),
        },
    ).fetchone()
    db.commit()
    if not row:
        return None
    return {
        "id": str(row.id),
        "message_id": row.message_id,
        "status": row.status,
        "attachment_count": row.attachment_count,
        "accepted_attachment_count": row.accepted_attachment_count,
        "rejected_attachment_count": row.rejected_attachment_count,
    }


def _result_from_audit_row(row: Dict[str, Any]) -> InboundEmailResult:
    """Rebuild the response body from a previously persisted audit row (idempotent replay)."""
    attachments = [
        AttachmentResult(
            name=d.get("name", ""),
            status=d.get("status", "rejected"),
            reason=d.get("reason"),
            rows_accepted=d.get("rows_accepted", 0),
            rows_rejected=d.get("rows_rejected", 0),
        )
        for d in row.get("details") or []
    ]
    return InboundEmailResult(
        message_id=row["message_id"],
        status=row["status"],
        tenant_id=row.get("tenant_id"),
        rejection_reason=row.get("rejection_reason"),
        attachments=attachments,
    )


# ---------------------------------------------------------------------------
# Attachment handling
# ---------------------------------------------------------------------------


async def _ingest_attachment_csv(tenant_id: str, name: str, raw: bytes) -> AttachmentResult:
    """Hand decoded CSV bytes to the existing ingest path (no reparsing here)."""
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
            # NOT None: webhook_router_v2._verify_api_key_present (invoked
            # deep inside ingest_csv -> webhook_compat.ingest_events) is a
            # presence-only check on this header -- "if not
            # x_regengine_api_key: raise HTTPException(401)" -- it never
            # validates the value. Passing None here means every single
            # real attachment gets 401'd and reported as "rejected" before
            # ever reaching CTEPersistence. Real authorization for this
            # call already happened via verify_inbound_email_auth's Basic
            # Auth gate plus the explicit `principal` constructed above;
            # this sentinel only satisfies the unrelated defense-in-depth
            # presence check for a caller that has no X-RegEngine-API-Key
            # header to forward.
            x_regengine_api_key="email-inbound-internal",
            x_tenant_id=None,
        )
    except HTTPException as exc:
        detail = exc.detail
        reason = detail.get("message") if isinstance(detail, dict) else str(detail)
        return AttachmentResult(name=name, status="rejected", reason=reason)
    except Exception:
        # Anything else escaping the reused pipeline (e.g. a non-UTF-8 CSV
        # -- csv_templates.ingest_csv's `content.decode("utf-8-sig")` isn't
        # wrapped in a try/except -- or a transient failure inside
        # webhook_compat.ingest_events) must not blow up the whole email.
        # An uncaught exception here would skip the audit-row write in
        # process_inbound_email entirely, and a Postmark retry would then
        # replay -- and thus double-ingest -- every attachment that already
        # succeeded earlier in this same request's loop.
        logger.exception("inbound_email_attachment_ingest_failed name=%s", name)
        return AttachmentResult(name=name, status="rejected", reason="ingestion_failed")
    return AttachmentResult(
        name=name,
        status="accepted" if response.accepted else "rejected",
        rows_accepted=response.accepted,
        rows_rejected=response.rejected,
    )


async def _process_one_attachment(tenant_id: str, attachment: PostmarkAttachment) -> AttachmentResult:
    """Apply the size/type/base64 checks from the design's §6 before reuse."""
    safe_name = sanitize_upload_filename(attachment.Name, fallback="attachment.csv")

    content_type = (attachment.ContentType or "").strip().lower()
    is_csv_extension = Path(safe_name).suffix.lower() == ".csv"
    is_csv_content_type = content_type in _ALLOWED_ATTACHMENT_CONTENT_TYPES
    if not is_csv_extension and not is_csv_content_type:
        return AttachmentResult(
            name=safe_name,
            status="rejected",
            reason=f"unsupported_attachment_type: {safe_name} ({attachment.ContentType})",
        )

    try:
        raw = base64.b64decode(attachment.Content, validate=True)
    except (binascii.Error, ValueError):
        logger.warning("inbound_email_attachment_invalid_base64 name=%s", safe_name)
        return AttachmentResult(name=safe_name, status="rejected", reason="invalid_base64_content")

    if len(raw) > MAX_CSV_FILE_SIZE_BYTES:
        return AttachmentResult(
            name=safe_name,
            status="rejected",
            reason=(
                f"{safe_name} exceeds maximum attachment size of "
                f"{MAX_CSV_FILE_SIZE_BYTES // (1024 * 1024)} MB"
            ),
        )

    return await _ingest_attachment_csv(tenant_id, safe_name, raw)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def process_inbound_email(db_session, payload: PostmarkInboundPayload) -> InboundEmailResult:
    # Idempotency guard: a provider retry on the same MessageID replays the
    # recorded summary instead of re-running CSV ingestion a second time.
    existing = get_inbound_email_audit_by_message_id(db_session, payload.MessageID)
    if existing:
        return _result_from_audit_row(existing)

    recipient = _first_recipient(payload)
    tenant_id = tenant_lookup.lookup_tenant_by_inbound_address(db_session, recipient) if recipient else None

    if tenant_id is None:
        logger.warning(
            "inbound_email_unmapped_recipient recipient=%s message_id=%s",
            mask_email(recipient or ""),
            payload.MessageID,
        )
        record_inbound_email_audit(
            db_session,
            tenant_id=None,
            message_id=payload.MessageID,
            sender=payload.From,
            recipient=recipient or "",
            subject=payload.Subject,
            status="rejected",
            rejection_reason="unmapped_recipient",
            attachment_count=len(payload.Attachments),
            accepted_count=0,
            rejected_count=0,
            details=[],
        )
        return InboundEmailResult(
            message_id=payload.MessageID,
            status="rejected",
            rejection_reason="unmapped_recipient",
        )

    set_tenant_guc(db_session, tenant_id)
    results: List[AttachmentResult] = []
    for attachment in payload.Attachments:
        results.append(await _process_one_attachment(tenant_id, attachment))

    accepted = sum(1 for r in results if r.status == "accepted")
    rejected = sum(1 for r in results if r.status == "rejected")
    status = "rejected" if payload.Attachments and accepted == 0 else ("partial" if rejected else "accepted")

    record_inbound_email_audit(
        db_session,
        tenant_id=tenant_id,
        message_id=payload.MessageID,
        sender=payload.From,
        recipient=recipient,
        subject=payload.Subject,
        status=status,
        rejection_reason=None,
        attachment_count=len(payload.Attachments),
        accepted_count=accepted,
        rejected_count=rejected,
        details=[r.model_dump() for r in results],
    )
    return InboundEmailResult(
        message_id=payload.MessageID,
        status=status,
        tenant_id=tenant_id,
        attachments=results,
    )
