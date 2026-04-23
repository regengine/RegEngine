# ============================================================
# UNSAFE ZONE: This file (1043 lines) mixes EDI X12 segment
# parsing (856/850/810/861), field mapping, CTE normalization,
# and validation in a single module. Fragile string parsing of
# EDI segments — changes to segment mapping risk silent data
# corruption in ingested events.
# Refactoring target — see PHASE 3.5 in REGENGINE_CODEBASE_REMEDIATION_PRD.md
# ============================================================
"""EDI inbound ingestion router.

Accepts partner-authenticated X12 documents and normalizes them into FSMA CTE
events through the existing webhook ingestion pipeline. Supports:
  - 856 (ASN / Ship Notice)
  - 850 (Purchase Order)
  - 810 (Invoice)
  - 861 (Receiving Advice)

Extracts shipment details, product identifiers, quantities, and locations
relevant to FSMA Critical Tracking Events.
"""

from __future__ import annotations

import importlib
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import ValidationError

from app.authz import require_permission
from app.format_extractors import is_edi_content
from app.shared.tenant_resolution import resolve_tenant_id
from app.shared.upload_limits import read_upload_with_limit, MAX_EDI_FILE_SIZE_BYTES
from app.webhook_compat import ingest_events
from app.webhook_models import (
    IngestEvent,
    WebhookCTEType,
    WebhookPayload,
)

from .constants import (
    _CTE_TYPE_BY_SET,
    _REQUIRED_856_SEGMENTS,
    _REQUIRED_SEGMENTS_BY_SET,
    _SUPPORTED_TRANSACTION_SETS,
)
from .dedup import check_and_record_interchange, verify_trading_partner_allowed
from .extractors import _extract_856_fields, _extract_fields_for_set
from .models import EDIIngestResponse
from .parser import _first_segment, _parse_x12_segments, _segment_id_set, _detect_transaction_set
from .utils import (
    _normalize_unit,
    _safe_float,
    _ship_timestamp_and_date,
    _valid_gln_or_none,
    _verify_partner_id,
)
from .validation import _validate_edi_as_fsma_event

logger = logging.getLogger("edi-ingestion")


def _record_edi_rejection(**kwargs):
    """Resolve the live rejection-log module before writing.

    Tests swap ``app.edi_ingestion`` modules in and out of ``sys.modules``.
    Looking up the recorder lazily keeps the route and the test helpers
    pointed at the same in-memory rejection store.
    """
    rejection_log = importlib.import_module("app.edi_ingestion.rejection_log")
    return rejection_log.record_edi_rejection(**kwargs)


def _decode_edi_bytes(raw_bytes: bytes) -> str:
    """Decode an EDI upload without silent data loss.

    #1170: the original implementation used ``errors="ignore"`` which
    silently dropped non-ASCII characters — "Distribuidora Española"
    became "Distribuidora Espaola" with no signal, breaking partner-
    name matching. An interim fix used ``errors="replace"`` which
    preserves byte count but still corrupts the data with U+FFFD
    (same bug class, just with a visible marker).

    The spec-honoring fix:

      1. Try ``utf-8`` strict. Modern partners send UTF-8 and
         non-ASCII names (ñ, é, ü) round-trip exactly.
      2. On ``UnicodeDecodeError`` fall back to ``latin-1`` strict
         (ISO-8859-1). X12.5/X12.6 explicitly name ISO-8859-1 as the
         Basic/Extended character set, so a partner sending latin-1
         is spec-compliant, not broken. ``latin-1`` is a total
         encoding (all 256 byte values map to code points) so strict
         decoding of arbitrary bytes never fails — we don't need a
         third fallback and we never silently drop bytes.
      3. If even latin-1 raises (only possible via future codec
         bugs), ``raise`` the underlying ``UnicodeDecodeError``. The
         upload endpoint catches it and returns HTTP 422 instead of
         persisting corrupted data.

    A WARN log fires whenever latin-1 fallback is used so an operator
    can spot encoding drift from a partner and update their config.
    """
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError as utf8_err:
        # Spec fallback: X12 Basic/Extended character set is ISO-8859-1.
        # latin-1 is total — every byte maps — so this is strict-safe.
        try:
            text = raw_bytes.decode("latin-1")
        except UnicodeDecodeError:
            # Should be unreachable for latin-1. Re-raise the original
            # UTF-8 error so the handler can reject the row loudly.
            raise utf8_err
        logger.warning(
            "edi_decode_fallback_latin1 bytes=%d utf8_err_pos=%d — "
            "partner is sending ISO-8859-1 (X12 Basic set); data is "
            "preserved verbatim but partner config should declare "
            "encoding explicitly",
            len(raw_bytes), utf8_err.start,
        )
        return text


def _edi_strict_mode() -> bool:
    """Return True when EDI FSMA validation failure MUST block persistence.

    #1174: default strict. EDI documents that fail FSMAEvent schema
    validation are refused with HTTP 422 rather than persisted with a
    ``failed`` flag that still pollutes the traceability graph. Set
    ``EDI_STRICT_MODE=false`` only during migrations. The per-request
    ``?strict=false`` query param follows the same convention.
    """
    explicit = os.getenv("EDI_STRICT_MODE")
    if explicit is None:
        return True
    return explicit.strip().lower() in {"1", "true", "yes", "on", "strict"}

router = APIRouter(prefix="/api/v1/ingest/edi", tags=["EDI Import"])

_resolve_tenant_id = resolve_tenant_id


def _enforce_envelope_integrity(
    extracted: dict[str, Any],
    sender_tenant_id: str,
    transaction_set: str,
) -> None:
    """Apply #1160 + #1165 envelope validation.

    - Reject on ISA/GS sender/receiver mismatch (X12 tenant-smuggling).
    - Reject on GS sender not in tenant's allowed trading-partner list.
    - Check ISA13 against the interchange dedup cache and return 409
      idempotent-replay on retransmission.
    """
    # #1160: envelope mismatch between ISA and GS — caller tried to
    # smuggle a different trading-partner identity.
    if extracted.get("envelope_mismatch"):
        logger.warning(
            "edi_envelope_mismatch tenant=%s isa_sender=%s gs_sender=%s "
            "isa_receiver=%s gs_receiver=%s",
            sender_tenant_id,
            extracted.get("isa_sender_id"),
            extracted.get("gs_sender_id"),
            extracted.get("isa_receiver_id"),
            extracted.get("gs_receiver_id"),
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "edi_envelope_mismatch",
                "message": (
                    "ISA and GS envelope sender/receiver IDs disagree. "
                    "This interchange is rejected to prevent tenant smuggling."
                ),
                "isa_sender_id": extracted.get("isa_sender_id"),
                "gs_sender_id": extracted.get("gs_sender_id"),
            },
        )

    # #1160: enforce trading-partner allowlist per tenant (permissive
    # if the env var is unset — no-op until explicitly configured).
    if not verify_trading_partner_allowed(
        tenant_id=sender_tenant_id,
        gs_sender_id=extracted.get("gs_sender_id"),
    ):
        logger.warning(
            "edi_trading_partner_denied tenant=%s gs_sender=%s",
            sender_tenant_id, extracted.get("gs_sender_id"),
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "trading_partner_not_allowed",
                "message": (
                    "GS sender id is not in the tenant's allowed trading "
                    "partner list."
                ),
                "gs_sender_id": extracted.get("gs_sender_id"),
            },
        )

    # #1165: retransmission dedup on ISA13.
    is_duplicate, _prev = check_and_record_interchange(
        sender_id=extracted.get("sender_id"),
        receiver_id=extracted.get("receiver_id"),
        isa13=extracted.get("isa13"),
    )
    if is_duplicate:
        logger.info(
            "edi_retransmission_detected tenant=%s sender=%s isa13=%s set=%s",
            sender_tenant_id,
            extracted.get("sender_id"),
            extracted.get("isa13"),
            transaction_set,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "error": "duplicate_interchange",
                "message": (
                    "Interchange control number (ISA13) already processed. "
                    "This is an idempotent replay — no events were ingested."
                ),
                "isa13": extracted.get("isa13"),
                "idempotent_replay": True,
            },
        )


@router.post(
    "",
    response_model=EDIIngestResponse,
    status_code=201,
    summary="Ingest X12 856 ASN",
    description=(
        "Partner-authenticated EDI inbound route for X12 856 Ship Notice/Manifest "
        "documents. Validates required segments, extracts shipping KDEs, and "
        "persists as FSMA shipping CTE events."
    ),
)
async def ingest_edi_856(
    file: UploadFile = File(..., description="X12 EDI file (856 ASN)"),
    traceability_lot_code: str = Form(..., description="FSMA Traceability Lot Code"),
    tenant_id: Optional[str] = Form(None, description="Optional tenant override"),
    source: str = Form("edi_856_inbound", description="Source system identifier"),
    product_description: Optional[str] = Form(None, description="Optional product description override"),
    quantity_override: Optional[float] = Form(None, gt=0, description="Optional quantity override"),
    unit_of_measure_override: Optional[str] = Form(None, description="Optional unit override"),
    ship_from_location_override: Optional[str] = Form(None, description="Optional ship-from override"),
    ship_to_location_override: Optional[str] = Form(None, description="Optional ship-to override"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    x_partner_id: Optional[str] = Header(default=None, alias="X-Partner-ID"),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
    _auth=Depends(require_permission("edi.ingest")),
) -> EDIIngestResponse:
    sender_tenant_id = _resolve_tenant_id(tenant_id, x_tenant_id, x_regengine_api_key)
    if not sender_tenant_id:
        raise HTTPException(status_code=400, detail="Sender tenant context required")

    _verify_partner_id(x_partner_id)

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Empty EDI payload")

    if not is_edi_content(raw_bytes):
        raise HTTPException(status_code=400, detail="Unsupported EDI payload format")

    # #1170: fail loud on undecodable bytes rather than corrupt silently.
    try:
        raw_text = _decode_edi_bytes(raw_bytes)
    except UnicodeDecodeError as exc:
        logger.warning(
            "edi_decode_failed_856 tenant=%s bytes=%d pos=%d",
            sender_tenant_id, len(raw_bytes), exc.start,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "edi_decode_failed",
                "message": (
                    "EDI payload is not valid UTF-8 or ISO-8859-1 (X12 Basic "
                    "set). The document is rejected rather than persisted "
                    "with corrupted names. Re-upload with a spec-compliant "
                    "encoding."
                ),
                "byte_position": exc.start,
            },
        )
    segments = _parse_x12_segments(raw_text)
    if not segments:
        raise HTTPException(status_code=400, detail="Unable to parse EDI segments")

    transaction_set = (_first_segment(segments, "ST") or ["", ""])[1]
    if transaction_set != "856":
        raise HTTPException(status_code=400, detail="Only X12 856 is currently supported")

    present_segments = _segment_id_set(segments)
    missing_segments = sorted(_REQUIRED_856_SEGMENTS - present_segments)
    if missing_segments:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "EDI 856 missing required segments",
                "missing_segments": missing_segments,
            },
        )

    extracted = _extract_856_fields(segments)

    # #1160 + #1165: envelope mismatch / allowlist / ISA13 dedup.
    _enforce_envelope_integrity(extracted, sender_tenant_id, "856")

    timestamp, ship_date = _ship_timestamp_and_date(
        extracted.get("ship_date_raw"),
        extracted.get("ship_time_raw"),
    )

    quantity = quantity_override if quantity_override is not None else extracted.get("quantity")
    resolved_quantity = _safe_float(str(quantity) if quantity is not None else None, fallback=1.0)
    resolved_unit = _normalize_unit(unit_of_measure_override or extracted.get("unit_of_measure"))

    ship_from_name = (
        ship_from_location_override
        or extracted.get("ship_from_name")
        or "Unknown ship-from"
    )
    ship_to_name = (
        ship_to_location_override
        or extracted.get("ship_to_name")
        or "Unknown ship-to"
    )

    product_name = (
        product_description
        or extracted.get("product_description")
        or "EDI 856 Shipment"
    )

    ship_from_gln_raw = extracted.get("ship_from_gln")
    ship_to_gln_raw = extracted.get("ship_to_gln")
    ship_from_gln = _valid_gln_or_none(ship_from_gln_raw)
    ship_to_gln = _valid_gln_or_none(ship_to_gln_raw)

    kdes: dict[str, Any] = {
        "ship_date": ship_date,
        "ship_from_location": ship_from_name,
        "ship_to_location": ship_to_name,
        "ship_from_gln": ship_from_gln or ship_from_gln_raw,
        "ship_to_gln": ship_to_gln or ship_to_gln_raw,
        "reference_document_number": extracted.get("reference_document_number"),
        "carrier": extracted.get("carrier"),
        "asn_number": extracted.get("asn_number"),
        "edi_transaction_set": "856",
        "edi_control_number": extracted.get("control_number"),
        # Canonical trading-partner id (GS first, ISA fallback) per #1160.
        "edi_sender_id": extracted.get("sender_id"),
        "edi_receiver_id": extracted.get("receiver_id"),
        # Raw envelope values for audit traceability.
        "edi_isa_sender_id": extracted.get("isa_sender_id"),
        "edi_gs_sender_id": extracted.get("gs_sender_id"),
        "edi_isa13": extracted.get("isa13"),
        "edi_gs_control_number": extracted.get("gs_control_number"),
        "partner_id": x_partner_id,
        "immediate_previous_source": ship_from_name,
    }

    event = IngestEvent(
        cte_type=WebhookCTEType.SHIPPING,
        traceability_lot_code=traceability_lot_code,
        product_description=product_name,
        quantity=resolved_quantity,
        unit_of_measure=resolved_unit,
        location_gln=ship_from_gln,
        location_name=ship_from_name,
        timestamp=timestamp,
        kdes={k: v for k, v in kdes.items() if v is not None and v != ""},
    )

    payload = WebhookPayload(
        source=source,
        events=[event],
        tenant_id=sender_tenant_id,
    )
    ingestion_result = await ingest_events(
        payload,
        x_regengine_api_key=x_regengine_api_key,
    )

    return EDIIngestResponse(
        sender_tenant_id=sender_tenant_id,
        partner_id=x_partner_id,
        traceability_lot_code=traceability_lot_code,
        extracted={
            "asn_number": extracted.get("asn_number"),
            "quantity": resolved_quantity,
            "unit_of_measure": resolved_unit,
            "ship_from_location": ship_from_name,
            "ship_to_location": ship_to_name,
            "reference_document_number": extracted.get("reference_document_number"),
        },
        ingestion_result=ingestion_result,
    )


def _build_ingest_event_for_set(
    transaction_set: str,
    extracted: dict[str, Any],
    traceability_lot_code: str,
    product_description_override: str | None,
    quantity_override: float | None,
    unit_override: str | None,
    location_override: str | None,
) -> IngestEvent:
    """Build an IngestEvent from extracted EDI fields for any supported set."""
    cte_type = _CTE_TYPE_BY_SET.get(transaction_set, WebhookCTEType.SHIPPING)

    # Resolve quantity
    quantity = quantity_override if quantity_override is not None else extracted.get("quantity")
    resolved_quantity = _safe_float(str(quantity) if quantity is not None else None, fallback=1.0)
    resolved_unit = _normalize_unit(unit_override or extracted.get("unit_of_measure"))

    # Resolve product description
    product_name = (
        product_description_override
        or extracted.get("product_description")
        or f"EDI {transaction_set} Item"
    )

    # Resolve location (varies by document type)
    location_name = location_override
    location_gln = None
    if transaction_set in ("856", "850"):
        location_name = location_name or extracted.get("ship_from_name") or extracted.get("seller_name") or "Unknown"
        location_gln = _valid_gln_or_none(extracted.get("ship_from_gln") or extracted.get("seller_gln"))
    elif transaction_set == "810":
        location_name = location_name or extracted.get("seller_name") or "Unknown"
        location_gln = _valid_gln_or_none(extracted.get("seller_gln"))
    elif transaction_set == "861":
        location_name = location_name or extracted.get("receiving_location_name") or "Unknown"
        location_gln = _valid_gln_or_none(extracted.get("receiving_location_gln"))

    # Resolve timestamp
    date_field_map = {
        "856": ("ship_date_raw", "ship_time_raw"),
        "850": ("po_date_raw", None),
        "810": ("invoice_date_raw", None),
        "861": ("receive_date_raw", None),
    }
    date_field, time_field = date_field_map.get(transaction_set, (None, None))
    timestamp, event_date = _ship_timestamp_and_date(
        extracted.get(date_field) if date_field else None,
        extracted.get(time_field) if time_field else None,
    )

    # Build KDEs
    kdes: dict[str, Any] = {
        "edi_transaction_set": transaction_set,
        "edi_control_number": extracted.get("control_number"),
        # Canonical trading-partner id (GS first, ISA fallback) per #1160.
        "edi_sender_id": extracted.get("sender_id"),
        "edi_receiver_id": extracted.get("receiver_id"),
        # Raw envelope values for audit / forensic traceability.
        "edi_isa_sender_id": extracted.get("isa_sender_id"),
        "edi_gs_sender_id": extracted.get("gs_sender_id"),
        "edi_isa13": extracted.get("isa13"),
        "edi_gs_control_number": extracted.get("gs_control_number"),
        "reference_document_number": extracted.get("reference_document_number"),
        "event_date": event_date,
    }

    if transaction_set == "856":
        kdes.update({
            "ship_from_location": extracted.get("ship_from_name"),
            "ship_to_location": extracted.get("ship_to_name"),
            "ship_from_gln": extracted.get("ship_from_gln"),
            "ship_to_gln": extracted.get("ship_to_gln"),
            "carrier": extracted.get("carrier"),
            "asn_number": extracted.get("asn_number"),
        })
    elif transaction_set == "850":
        kdes.update({
            "po_number": extracted.get("po_number"),
            "buyer_name": extracted.get("buyer_name"),
            "seller_name": extracted.get("seller_name"),
            "buyer_gln": extracted.get("buyer_gln"),
            "seller_gln": extracted.get("seller_gln"),
            "unit_price": extracted.get("unit_price"),
        })
    elif transaction_set == "810":
        kdes.update({
            "invoice_number": extracted.get("invoice_number"),
            "po_number": extracted.get("po_number"),
            "buyer_name": extracted.get("buyer_name"),
            "seller_name": extracted.get("seller_name"),
            "total_amount": extracted.get("total_amount"),
        })
    elif transaction_set == "861":
        kdes.update({
            "receiving_advice_number": extracted.get("receiving_advice_number"),
            "po_number": extracted.get("po_number"),
            "ship_from_location": extracted.get("ship_from_name"),
            "receiving_location": extracted.get("receiving_location_name"),
            "receiving_location_gln": extracted.get("receiving_location_gln"),
            "condition_code": extracted.get("condition_code"),
        })

    return IngestEvent(
        cte_type=cte_type,
        traceability_lot_code=traceability_lot_code,
        product_description=product_name,
        quantity=resolved_quantity,
        unit_of_measure=resolved_unit,
        location_gln=location_gln,
        location_name=location_name,
        timestamp=timestamp,
        kdes={k: v for k, v in kdes.items() if v is not None and v != ""},
    )


@router.post(
    "/document",
    response_model=EDIIngestResponse,
    status_code=201,
    summary="Ingest X12 EDI document (856/850/810/861)",
    description=(
        "Unified EDI inbound route that auto-detects the transaction set "
        "(856 ASN, 850 Purchase Order, 810 Invoice, 861 Receiving Advice) "
        "and extracts FSMA-relevant KDEs for CTE creation."
    ),
)
async def ingest_edi_document(
    file: UploadFile = File(..., description="X12 EDI file"),
    traceability_lot_code: str = Form(..., description="FSMA Traceability Lot Code"),
    tenant_id: Optional[str] = Form(None, description="Optional tenant override"),
    source: str = Form("edi_inbound", description="Source system identifier"),
    product_description: Optional[str] = Form(None, description="Optional product description override"),
    quantity_override: Optional[float] = Form(None, gt=0, description="Optional quantity override"),
    unit_of_measure_override: Optional[str] = Form(None, description="Optional unit override"),
    location_override: Optional[str] = Form(None, description="Optional location name override"),
    strict: bool = Query(
        default=True,
        description=(
            "FSMA validation mode (#1174). ``true`` (default): schema "
            "failures return HTTP 422 and nothing is persisted. "
            "``false``: advisory — the rejection is written to the EDI "
            "rejection log (separate from the canonical FSMA stream) "
            "and the response returns ``status='rejected'`` with a "
            "rejection_id. The invalid event is NEVER inserted into "
            "the canonical ingest pipeline, so the FSMA 204 audit trail "
            "stays clean. Set only for test or migration scenarios. "
            "Global env default ``EDI_STRICT_MODE=false`` also disables "
            "strict mode."
        ),
    ),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    x_partner_id: Optional[str] = Header(default=None, alias="X-Partner-ID"),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
    _auth=Depends(require_permission("edi.ingest")),
) -> EDIIngestResponse:
    """Ingest any supported X12 EDI document type."""
    sender_tenant_id = _resolve_tenant_id(tenant_id, x_tenant_id, x_regengine_api_key)
    if not sender_tenant_id:
        raise HTTPException(status_code=400, detail="Sender tenant context required")

    _verify_partner_id(x_partner_id)

    raw_bytes = await read_upload_with_limit(file, max_bytes=MAX_EDI_FILE_SIZE_BYTES, label="EDI file")
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Empty EDI payload")

    if not is_edi_content(raw_bytes):
        raise HTTPException(status_code=400, detail="Unsupported EDI payload format")

    # #1170: fail loud on undecodable bytes rather than corrupt silently.
    try:
        raw_text = _decode_edi_bytes(raw_bytes)
    except UnicodeDecodeError as exc:
        logger.warning(
            "edi_decode_failed_document tenant=%s bytes=%d pos=%d",
            sender_tenant_id, len(raw_bytes), exc.start,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "edi_decode_failed",
                "message": (
                    "EDI payload is not valid UTF-8 or ISO-8859-1 (X12 Basic "
                    "set). The document is rejected rather than persisted "
                    "with corrupted names. Re-upload with a spec-compliant "
                    "encoding."
                ),
                "byte_position": exc.start,
            },
        )
    segments = _parse_x12_segments(raw_text)
    if not segments:
        raise HTTPException(status_code=400, detail="Unable to parse EDI segments")

    transaction_set = _detect_transaction_set(segments)
    if not transaction_set:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported or unrecognized transaction set. Supported: {sorted(_SUPPORTED_TRANSACTION_SETS)}",
        )

    required_segments = _REQUIRED_SEGMENTS_BY_SET.get(transaction_set, set())
    present_segments = _segment_id_set(segments)
    missing_segments = sorted(required_segments - present_segments)
    if missing_segments:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"EDI {transaction_set} missing required segments",
                "missing_segments": missing_segments,
            },
        )

    extracted = _extract_fields_for_set(transaction_set, segments)

    # #1160 + #1165: envelope mismatch / allowlist / ISA13 dedup.
    _enforce_envelope_integrity(extracted, sender_tenant_id, transaction_set)

    # #1174: FSMA validation is fail-closed by default. A schema failure
    # returns HTTP 422 with per-field errors and nothing is persisted.
    # ``?strict=false`` and ``EDI_STRICT_MODE=false`` (env) both down-
    # grade to advisory mode — the event is NOT persisted into the
    # canonical ingest stream (that would pollute the FSMA 204
    # traceability graph). Instead the rejection is recorded via
    # ``record_edi_rejection`` so the audit trail is preserved but kept
    # out of the valid-event surface. The caller receives a response
    # with ``status='rejected'`` and a rejection_id it can use to look
    # up the record.
    rejection_record: dict[str, Any] | None = None
    try:
        _validate_edi_as_fsma_event(
            extracted, transaction_set, traceability_lot_code, sender_tenant_id,
        )
        extracted["fsma_validation_status"] = "passed"
    except ValidationError as ve:
        strict_effective = strict and _edi_strict_mode()
        if strict_effective:
            logger.warning(
                "edi_fsma_validation_rejected set=%s tlc=%s errors=%d",
                transaction_set, traceability_lot_code, len(ve.errors()),
            )
            # Record on the strict path too — the canonical stream is
            # untouched either way, but auditors still need the trail.
            _record_edi_rejection(
                tenant_id=sender_tenant_id,
                transaction_set=transaction_set,
                traceability_lot_code=traceability_lot_code,
                errors=ve.errors(),
                extracted=extracted,
                partner_id=x_partner_id,
                source=source,
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "fsma_validation_failed",
                    "transaction_set": transaction_set,
                    "tlc": traceability_lot_code,
                    "message": (
                        "EDI document failed FSMAEvent schema validation. "
                        "No events were persisted. Pass ?strict=false or "
                        "set EDI_STRICT_MODE=false only for migration "
                        "windows — failed rows are written to the EDI "
                        "rejection log, never the canonical FSMA stream."
                    ),
                    "errors": ve.errors(),
                },
            )
        # Advisory mode: record the rejection separately and short-
        # circuit before the canonical write. We do NOT call
        # ``ingest_events`` — that would put the invalid event into the
        # audit trail with ``fsma_validation_status=failed``, which is
        # exactly the pollution #1174 is meant to stop.
        extracted["fsma_validation_status"] = "failed"
        rejection_record = _record_edi_rejection(
            tenant_id=sender_tenant_id,
            transaction_set=transaction_set,
            traceability_lot_code=traceability_lot_code,
            errors=ve.errors(),
            extracted=extracted,
            partner_id=x_partner_id,
            source=source,
        )
    except ImportError:
        logger.debug("shared.schemas not available — skipping FSMA validation")
        extracted["fsma_validation_status"] = "unknown"

    if rejection_record is not None:
        # Rejected in advisory mode: respond 201 (document was accepted
        # for audit) but signal that nothing reached the canonical
        # stream. ``ingestion_result`` is omitted deliberately so
        # downstream readers don't mistake the rejection for a valid
        # event.
        return EDIIngestResponse(
            status="rejected",
            document_type=f"X12_{transaction_set}",
            sender_tenant_id=sender_tenant_id,
            partner_id=x_partner_id,
            traceability_lot_code=traceability_lot_code,
            extracted={
                "transaction_set": transaction_set,
                "quantity": extracted.get("quantity"),
                "unit_of_measure": extracted.get("unit_of_measure"),
                "product_description": extracted.get("product_description"),
                "reference_document_number": extracted.get("reference_document_number"),
                "fsma_validation_status": extracted.get("fsma_validation_status"),
            },
            ingestion_result=None,
            rejection={
                "rejection_id": rejection_record["rejection_id"],
                "reason": rejection_record["reason"],
                "recorded_at": rejection_record["recorded_at"],
                "error_count": len(rejection_record["errors"]),
            },
        )

    event = _build_ingest_event_for_set(
        transaction_set=transaction_set,
        extracted=extracted,
        traceability_lot_code=traceability_lot_code,
        product_description_override=product_description,
        quantity_override=quantity_override,
        unit_override=unit_of_measure_override,
        location_override=location_override,
    )

    payload = WebhookPayload(
        source=f"{source}_{transaction_set}" if source == "edi_inbound" else source,
        events=[event],
        tenant_id=sender_tenant_id,
    )
    ingestion_result = await ingest_events(
        payload,
        x_regengine_api_key=x_regengine_api_key,
    )

    return EDIIngestResponse(
        document_type=f"X12_{transaction_set}",
        sender_tenant_id=sender_tenant_id,
        partner_id=x_partner_id,
        traceability_lot_code=traceability_lot_code,
        extracted={
            "transaction_set": transaction_set,
            "quantity": extracted.get("quantity"),
            "unit_of_measure": extracted.get("unit_of_measure"),
            "product_description": extracted.get("product_description"),
            "reference_document_number": extracted.get("reference_document_number"),
            "fsma_validation_status": extracted.get("fsma_validation_status"),
        },
        ingestion_result=ingestion_result,
    )
