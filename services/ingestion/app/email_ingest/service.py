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
import re
from email.utils import getaddresses, parseaddr
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

# Strips control characters (including CR/LF) from a payload-derived value
# before it reaches a structured log line, same intent as
# ``sanitize_upload_filename`` for attachment names and ``mask_email`` for
# the recipient — applied here to Postmark's free-form ``MessageID``, which
# unlike those two fields has no length cap or character restriction on the
# wire.
_LOG_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]+")
_MAX_LOG_VALUE_CHARS = 200


def _sanitize_log_value(value: Optional[str]) -> str:
    cleaned = _LOG_CONTROL_CHARS_RE.sub("", str(value or ""))
    return cleaned[:_MAX_LOG_VALUE_CHARS]


def _sender_address(raw_from: str) -> str:
    """Extract the bare email address from Postmark's ``From`` header value.

    Postmark documents ``From`` as the full header value (which may be
    ``"Display Name" <addr@example.com>`` or a bare address);
    ``email.utils.parseaddr`` handles both shapes. Used only for the
    per-tenant sender-allowlist check in ``tenant_lookup`` — the raw
    ``payload.From`` is still what gets persisted to the audit row.
    """
    _, addr = parseaddr(raw_from or "")
    return addr.strip().lower()


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


def claim_inbound_email_audit(
    db,
    *,
    tenant_id: Optional[str],
    message_id: str,
    sender: str,
    recipient: str,
    subject: Optional[str],
    attachment_count: int,
) -> Optional[Dict[str, Any]]:
    """Atomically claim a ``message_id`` for processing (v122 claim-then-act).

    Inserts the audit row with ``status='processing'`` — this is the FIRST
    write ``process_inbound_email`` makes, before any attachment ever
    reaches ``_ingest_attachment_csv``. ``ON CONFLICT (message_id) DO
    NOTHING`` in the underlying function means this returns ``None`` when
    another request has already claimed (or fully processed) this exact
    ``message_id``; the caller must treat that as "do not run ingestion",
    not just "someone already recorded it" — closing the race where two
    concurrent deliveries of the same MessageID both read "no row yet" and
    both proceeded to double-persist CTE events (see
    ``DESIGN_email-ingestion.md`` section 13 item 4 / section 15).
    """
    row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — SECURITY DEFINER function, parameterized inputs
        text(
            """
            SELECT id, message_id, status
            FROM fsma.claim_inbound_email_audit(
                :p_tenant_id, :p_message_id, :p_sender, :p_recipient, :p_subject, :p_attachment_count
            )
            """
        ),
        {
            "p_tenant_id": tenant_id,
            "p_message_id": message_id,
            "p_sender": sender,
            "p_recipient": recipient,
            "p_subject": subject,
            "p_attachment_count": attachment_count,
        },
    ).fetchone()
    db.commit()
    if not row:
        return None
    return {"id": str(row.id), "message_id": row.message_id, "status": row.status}


def finalize_inbound_email_audit(
    db,
    *,
    message_id: str,
    tenant_id: Optional[str],
    status: str,
    rejection_reason: Optional[str],
    attachment_count: int,
    accepted_count: int,
    rejected_count: int,
    details: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Update a previously claimed audit row to its final outcome.

    Only applies while the row is still ``status='processing'`` (enforced in
    the SECURITY DEFINER function's ``WHERE`` clause), so this only ever acts
    on the row this same request's own ``claim_inbound_email_audit`` call
    produced — a stray double-finalize (there should never be one) is a
    silent no-op (``None`` returned) rather than corrupting another
    request's row.
    """
    row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — SECURITY DEFINER function, parameterized inputs
        text(
            """
            SELECT id, message_id, status, attachment_count,
                   accepted_attachment_count, rejected_attachment_count
            FROM fsma.finalize_inbound_email_audit(
                :p_message_id, :p_tenant_id, :p_status, :p_rejection_reason,
                :p_attachment_count, :p_accepted_count, :p_rejected_count, CAST(:p_details AS jsonb)
            )
            """
        ),
        {
            "p_message_id": message_id,
            "p_tenant_id": tenant_id,
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
        logger.warning("inbound_email_finalize_no_row message_id=%s", _sanitize_log_value(message_id))
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
            x_regengine_api_key="email-inbound-internal",  # pragma: allowlist secret
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

    # MIME parameters (e.g. "; charset=utf-8") describe the payload, they do
    # not change its type -- compare the bare media type only (RFC 2045 5.1).
    content_type = (attachment.ContentType or "").split(";")[0].strip().lower()
    is_csv_extension = Path(safe_name).suffix.lower() == ".csv"
    is_csv_content_type = content_type in _ALLOWED_ATTACHMENT_CONTENT_TYPES
    if not is_csv_extension and not is_csv_content_type:
        return AttachmentResult(
            name=safe_name,
            status="rejected",
            reason=f"unsupported_attachment_type: {safe_name} ({attachment.ContentType})",
        )

    try:
        content = attachment.Content
        if isinstance(content, str):
            # RFC 2045 encoders wrap base64 at 76 columns and forwarders may
            # preserve those line breaks; whitespace is never significant in
            # base64, so strip it before validating.
            content = "".join(content.split())
        raw = base64.b64decode(content, validate=True)
    except (binascii.Error, ValueError):
        logger.warning("inbound_email_attachment_invalid_base64 name=%s", safe_name)
        return AttachmentResult(name=safe_name, status="rejected", reason="invalid_base64_content")

    if len(raw) > MAX_CSV_FILE_SIZE_BYTES:
        return AttachmentResult(
            name=safe_name,
            status="rejected",
            reason=(f"{safe_name} exceeds maximum attachment size of {MAX_CSV_FILE_SIZE_BYTES // (1024 * 1024)} MB"),
        )

    return await _ingest_attachment_csv(tenant_id, safe_name, raw)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def process_inbound_email(db_session, payload: PostmarkInboundPayload) -> InboundEmailResult:
    # Idempotency guard: a provider retry on the same MessageID replays the
    # recorded summary instead of re-running CSV ingestion a second time.
    # A 'processing' row belongs to a request that is (or was, until it
    # crashed) still mid-flight -- it is not a finished result to replay.
    existing = get_inbound_email_audit_by_message_id(db_session, payload.MessageID)
    if existing is not None and existing["status"] != "processing":
        return _result_from_audit_row(existing)

    recipient = _first_recipient(payload)
    sender_address = _sender_address(payload.From)
    # v122: the recipient address alone is not a tenant boundary -- Postmark's
    # Basic-Auth webhook credential authenticates the transport only, not the
    # original sender, and forwards any internet sender's mail addressed to a
    # configured inbound address. The DB-backed lookup additionally requires
    # `sender_address` to match that tenant's `allowed_senders` allowlist.
    tenant_id = (
        tenant_lookup.lookup_tenant_by_inbound_address(db_session, recipient, sender_address) if recipient else None
    )

    # Claim-then-act (v122): this INSERT is the first write for this
    # message_id, made before any attachment touches CSV ingestion. Losing
    # the claim race means another request already owns (or has finished)
    # processing this exact MessageID.
    claim = claim_inbound_email_audit(
        db_session,
        tenant_id=tenant_id,
        message_id=payload.MessageID,
        sender=payload.From,
        recipient=recipient or "",
        subject=payload.Subject,
        attachment_count=len(payload.Attachments),
    )
    if claim is None:
        existing = get_inbound_email_audit_by_message_id(db_session, payload.MessageID)
        if existing is not None and existing["status"] != "processing":
            # The other request finished between our first read and this
            # claim attempt -- replay its recorded result.
            return _result_from_audit_row(existing)
        # Still mid-flight elsewhere. It is not safe to fabricate a result,
        # and not safe to run ingestion ourselves while another request
        # holds the claim, so surface a non-2xx -- exactly what Postmark's
        # own retry-on-non-2xx contract exists to recover from (see
        # router.py); the eventual retry will observe the finished row.
        raise HTTPException(
            status_code=409,
            detail={"message": "inbound_email_processing_in_progress", "message_id": payload.MessageID},
        )

    if tenant_id is None:
        logger.warning(
            "inbound_email_unmapped_recipient recipient=%s message_id=%s",
            mask_email(recipient or ""),
            _sanitize_log_value(payload.MessageID),
        )
        finalize_inbound_email_audit(
            db_session,
            message_id=payload.MessageID,
            tenant_id=None,
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

    # Review finding: everything from here to finalize_inbound_email_audit
    # below must never let an exception escape without finalizing the claim
    # row first. Each attachment's own ingestion errors are already caught
    # in _ingest_attachment_csv, but set_tenant_guc or finalize_inbound_
    # email_audit itself failing would otherwise leave this row stuck at
    # status='processing' forever: every future Postmark redelivery of the
    # same MessageID loses the claim race (line 402's INSERT conflicts),
    # sees the row still 'processing', and gets a permanent 409 -- the
    # email's CSV attachments are then never ingested. Finalizing as
    # 'rejected' on any unexpected failure trades that permanent hang for
    # a terminal, visible, auditable state (consistent with how
    # unmapped_recipient is handled above) and re-raises so Postmark still
    # sees a non-2xx.
    try:
        set_tenant_guc(db_session, tenant_id)
        results: List[AttachmentResult] = []
        for attachment in payload.Attachments:
            results.append(await _process_one_attachment(tenant_id, attachment))

        accepted = sum(1 for r in results if r.status == "accepted")
        rejected = sum(1 for r in results if r.status == "rejected")
        status = "rejected" if payload.Attachments and accepted == 0 else ("partial" if rejected else "accepted")

        finalize_inbound_email_audit(
            db_session,
            message_id=payload.MessageID,
            tenant_id=tenant_id,
            status=status,
            rejection_reason=None,
            attachment_count=len(payload.Attachments),
            accepted_count=accepted,
            rejected_count=rejected,
            details=[r.model_dump() for r in results],
        )
    except Exception:
        logger.exception(
            "inbound_email_processing_crashed message_id=%s",
            _sanitize_log_value(payload.MessageID),
        )
        # A DB-level failure above can leave db_session's transaction
        # aborted; SQLAlchemy refuses further statements on it until
        # rolled back, which would make this finalize call itself raise
        # and defeat the whole point of this handler.
        db_session.rollback()
        finalize_inbound_email_audit(
            db_session,
            message_id=payload.MessageID,
            tenant_id=tenant_id,
            status="rejected",
            rejection_reason="internal_error",
            attachment_count=len(payload.Attachments),
            accepted_count=0,
            rejected_count=0,
            details=[],
        )
        raise

    return InboundEmailResult(
        message_id=payload.MessageID,
        status=status,
        tenant_id=tenant_id,
        attachments=results,
    )
