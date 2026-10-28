# ============================================================
# UNSAFE ZONE: This file (1043 lines) mixes EDI X12 segment
# parsing (856/850/810/861/944/945), field mapping, CTE normalization,
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
  - 944 (Warehouse Stock Transfer Receipt Advice)
  - 945 (Warehouse Shipping Advice)

Extracts shipment details, product identifiers, quantities, and locations
relevant to FSMA Critical Tracking Events.
"""

from __future__ import annotations

import importlib
import logging
import os
from collections.abc import Callable
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import ValidationError
from shared.fsma_validation import is_location_description_complete

from ..authz import IngestionPrincipal, require_permission
from ..format_extractors import is_edi_content
from ..shared.tenant_resolution import resolve_principal_tenant_id, resolve_tenant_id
from ..shared.upload_limits import MAX_EDI_FILE_SIZE_BYTES, read_upload_with_limit
from ..webhook_compat import ingest_events
from ..webhook_models import (
    IngestEvent,
    WebhookCTEType,
    WebhookPayload,
)
from .constants import (
    _CTE_TYPE_BY_SET,
    _QUANTITY_ELEMENT_INDEX_BY_SET,
    _QUANTITY_SEGMENT_BY_SET,
    _REQUIRED_856_SEGMENTS,
    _REQUIRED_SEGMENTS_BY_SET,
    _SUPPORTED_TRANSACTION_SETS,
)
from .dedup import check_and_record_interchange, verify_trading_partner_allowed
from .extractors import _extract_856_fields, _extract_fields_for_set
from .models import EDIIngestResponse
from .parser import (
    _count_segments,
    _declared_transaction_set_count,
    _detect_transaction_set,
    _first_segment,
    _parse_x12_segments,
    _segment_id_set,
    _split_transaction_sets,
)
from .utils import (
    _normalize_unit,
    _resolve_unit_code,
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
            len(raw_bytes),
            utf8_err.start,
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


def _positive_float_or_none(value: Any) -> float | None:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _valid_unit_or_none(value: Any) -> str | None:
    # #2978: share one lookup with ``_normalize_unit`` so the fail-closed
    # gate and the coercing path can never disagree on which X12
    # element-355 codes they recognize.
    return _resolve_unit_code(value)


def _legacy_856_placeholder_errors(
    *,
    extracted: dict[str, Any],
    product_description_override: str | None,
    quantity_override: float | None,
    unit_override: str | None,
    ship_from_override: str | None,
    ship_to_override: str | None,
) -> list[dict[str, Any]]:
    """Find missing 856 KDEs that the legacy route used to synthesize."""
    errors: list[dict[str, Any]] = []

    def _add(field: str, placeholder: str, message: str) -> None:
        errors.append(
            {
                "loc": [field],
                "msg": message,
                "type": "missing_required_kde",
                "placeholder_blocked": placeholder,
            }
        )

    # Each SN1 is its own CTE. A zero or non-numeric line must fail here
    # even when a sibling line is valid, or the route would synthesize 1.0
    # for that line alone.
    lines = extracted.get("line_items") or [{}]
    for line in lines:
        raw_quantity = line.get("quantity")
        if quantity_override is None and _positive_float_or_none(raw_quantity) is None:
            _add(
                "quantity",
                "1.0",
                "EDI 856 is missing a positive SN1 quantity; refusing to synthesize quantity=1.0.",
            )

        raw_unit = line.get("unit_of_measure")
        unit_candidate = unit_override if unit_override is not None else raw_unit
        if _valid_unit_or_none(unit_candidate) is None:
            unit_message = (
                "EDI 856 is missing SN1 unit of measure; refusing to synthesize unit_of_measure='units'."
                if not (unit_candidate and str(unit_candidate).strip())
                else ("EDI 856 has an invalid unit of measure; refusing to synthesize unit_of_measure='units'.")
            )
            _add(
                "unit_of_measure",
                "units",
                unit_message,
            )

        if not (product_description_override or line.get("product_description")):
            _add(
                "product_description",
                "EDI 856 Shipment",
                "EDI 856 is missing product identification/description; refusing to synthesize a generic product.",
            )

    if not (ship_from_override or extracted.get("ship_from_name")):
        _add(
            "ship_from_location",
            "Unknown ship-from",
            "EDI 856 is missing ship-from location; refusing to synthesize an unknown location.",
        )

    if not (ship_to_override or extracted.get("ship_to_name")):
        _add(
            "ship_to_location",
            "Unknown ship-to",
            "EDI 856 is missing ship-to location; refusing to synthesize an unknown location.",
        )

    if not extracted.get("ship_date_raw"):
        _add(
            "ship_date",
            "current date",
            "EDI 856 is missing BSN ship date; refusing to synthesize the current date.",
        )

    return errors


def _reject_legacy_856_placeholders(
    *,
    errors: list[dict[str, Any]],
    sender_tenant_id: str,
    traceability_lot_code: str,
    extracted: dict[str, Any],
    partner_id: str | None,
    source: str,
) -> None:
    rejection_record = _record_edi_rejection(
        tenant_id=sender_tenant_id,
        transaction_set="856",
        traceability_lot_code=traceability_lot_code,
        errors=errors,
        extracted=extracted,
        partner_id=partner_id,
        source=source,
    )
    raise HTTPException(
        status_code=422,
        detail={
            "error": "edi_856_missing_required_kdes",
            "message": (
                "EDI 856 is missing required FSMA KDEs. No events were "
                "persisted; fix the supplier document or provide explicit "
                "operator-reviewed overrides."
            ),
            "missing_kdes": [err["loc"][0] for err in errors],
            "rejection_id": rejection_record["rejection_id"],
            "errors": errors,
        },
    )


# Event-date field (and optional time field) per transaction set.
_EVENT_DATE_FIELDS: dict[str, tuple[str | None, str | None]] = {
    "856": ("ship_date_raw", "ship_time_raw"),
    "850": ("po_date_raw", None),
    "810": ("invoice_date_raw", None),
    "861": ("receive_date_raw", None),
    "944": ("receive_date_raw", None),
    "945": ("ship_date_raw", None),
}


def _preflight_event_date(
    *,
    transaction_set: str,
    extracted: dict[str, Any],
    sender_tenant_id: str,
    traceability_lot_code: str,
    partner_id: str | None,
    source: str,
) -> None:
    """Reject a bad EDI event date BEFORE the ISA13 is reserved.

    ``_enforce_envelope_integrity`` records the interchange control number,
    so a date rejection raised after it would make the corrected resend a
    409 replay. Run this first. Every rejection is written to the EDI
    rejection log with ``needs_review=True`` and its id is returned to the
    caller.
    """
    date_field, time_field = _EVENT_DATE_FIELDS.get(transaction_set, (None, None))
    if transaction_set in ("944", "945"):
        time_field = None
    try:
        _ship_timestamp_and_date(
            extracted.get(date_field) if date_field else None,
            extracted.get(time_field) if time_field else None,
        )
    except HTTPException as exc:
        if exc.status_code != 400 or not isinstance(exc.detail, dict):
            raise
        detail = dict(exc.detail)
        record = _record_edi_rejection(
            tenant_id=sender_tenant_id,
            transaction_set=transaction_set,
            traceability_lot_code=traceability_lot_code,
            errors=[
                {
                    "loc": [date_field or "event_date"],
                    "type": detail.get("error"),
                    "msg": detail.get("message"),
                    "input": detail.get("raw"),
                }
            ],
            extracted=extracted,
            partner_id=partner_id,
            source=source,
            reason=str(detail.get("error") or "invalid_edi_date"),
            needs_review=True,
        )
        detail["needs_review"] = True
        detail["rejection_id"] = record["rejection_id"]
        raise HTTPException(status_code=400, detail=detail) from exc


router = APIRouter(prefix="/api/v1/ingest/edi", tags=["EDI Import"])

_resolve_tenant_id = resolve_tenant_id
_resolve_principal_tenant_id = resolve_principal_tenant_id


def _enforce_envelope_integrity(
    extracted: dict[str, Any],
    sender_tenant_id: str,
    transaction_set: str,
    before_reserve: Callable[[], None] | None = None,
) -> None:
    """Apply #1160 + #1165 envelope validation.

    ``before_reserve`` runs after the envelope and allowlist checks and
    before the ISA13 is recorded. Content rejections (event dates) go
    there so a disallowed sender still gets 403 and a rejected document
    does not burn its interchange number.

    - Reject on ISA/GS sender/receiver mismatch (X12 tenant-smuggling).
    - Reject on GS sender not in tenant's allowed trading-partner list.
    - Check ISA13 against the interchange dedup cache and return 409
      idempotent-replay on retransmission.
    """
    # #1160: envelope mismatch between ISA and GS — caller tried to
    # smuggle a different trading-partner identity.
    if extracted.get("envelope_mismatch"):
        logger.warning(
            "edi_envelope_mismatch tenant=%s isa_sender=%s gs_sender=%s isa_receiver=%s gs_receiver=%s",
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
            sender_tenant_id,
            extracted.get("gs_sender_id"),
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "trading_partner_not_allowed",
                "message": ("GS sender id is not in the tenant's allowed trading partner list."),
                "gs_sender_id": extracted.get("gs_sender_id"),
            },
        )

    if before_reserve is not None:
        before_reserve()

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


def _enforce_interchange_structure(
    segments: list[list[str]],
    set_slices: list[list[list[str]]],
) -> None:
    """Validate the ST/SE framing of an interchange before extraction.

    #2976: nothing counted ST segments or looked at GE01, so a batched
    interchange whose functional group was truncated or mis-assembled
    parsed exactly as a well-formed single-set one. Two structural
    invariants are checked here:

    - every ST is closed by an SE (an unterminated transaction set would
      otherwise swallow the segments of everything that follows it);
    - GE01, the declared number of transaction sets in the functional
      group, agrees with the ST segments that actually arrived.
    """
    st_count = _count_segments(segments, "ST")
    se_count = _count_segments(segments, "SE")
    if st_count != se_count or len(set_slices) != st_count:
        logger.warning(
            "edi_unbalanced_transaction_sets st=%d se=%d slices=%d",
            st_count,
            se_count,
            len(set_slices),
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unbalanced_transaction_sets",
                "message": (
                    "Every X12 ST segment must be closed by a matching SE. "
                    "This interchange is rejected rather than parsed with "
                    "transaction-set boundaries guessed."
                ),
                "st_count": st_count,
                "se_count": se_count,
            },
        )

    declared = _declared_transaction_set_count(segments)
    if declared is not None and declared != st_count:
        logger.warning(
            "edi_transaction_set_count_mismatch declared=%d actual=%d",
            declared,
            st_count,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "transaction_set_count_mismatch",
                "message": (
                    "GE01 declares a different number of transaction sets than "
                    "the interchange contains. The batch is truncated or "
                    "mis-assembled; no events were ingested."
                ),
                "declared": declared,
                "actual": st_count,
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
    principal: IngestionPrincipal = Depends(require_permission("edi.ingest")),
) -> EDIIngestResponse:
    sender_tenant_id = _resolve_principal_tenant_id(tenant_id, x_tenant_id, principal.tenant_id)

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
            "edi_decode_failed_856 tenant=%s bytes=%d pos=%d",
            sender_tenant_id,
            len(raw_bytes),
            exc.start,
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

    # A bare ``ST`` segment parses to ``["ST"]`` (truthy) with no ST01;
    # indexing [1] raised IndexError -> HTTP 500. A missing ST01 is an
    # unsupported transaction set, so fail with 400 like any other.
    st_segment = _first_segment(segments, "ST") or []
    transaction_set = st_segment[1] if len(st_segment) > 1 else ""
    if transaction_set != "856":
        raise HTTPException(status_code=400, detail="Only X12 856 is currently supported")

    # #2976: this endpoint's contract is one ASN in, one shipping CTE out,
    # and it extracts from the flat segment list. A batched interchange
    # would silently merge every ST/SE pair into that single event, so it
    # is refused here rather than half-ingested. Use /document, which
    # emits one event per transaction set.
    set_slices = _split_transaction_sets(segments)
    _enforce_interchange_structure(segments, set_slices)
    if len(set_slices) > 1:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "multiple_transaction_sets",
                "message": (
                    "This endpoint accepts a single X12 856 transaction set. "
                    "POST batched interchanges to /api/v1/ingest/edi/document, "
                    "which emits one CTE per ST/SE pair."
                ),
                "transaction_set_count": len(set_slices),
            },
        )

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

    # Event-date rejections run after the allowlist and before the ISA13
    # is reserved, so a corrected resend is not refused as a 409 replay.
    _enforce_envelope_integrity(
        extracted,
        sender_tenant_id,
        "856",
        before_reserve=lambda: _preflight_event_date(
            transaction_set="856",
            extracted=extracted,
            sender_tenant_id=sender_tenant_id,
            traceability_lot_code=traceability_lot_code,
            partner_id=x_partner_id,
            source=source,
        ),
    )

    lines = extracted.get("line_items") or []
    if len(lines) > 1:
        supplied_overrides = [
            name
            for name, value in (
                ("product_description", product_description),
                ("quantity_override", quantity_override),
                ("unit_of_measure_override", unit_of_measure_override),
                ("ship_from_location_override", ship_from_location_override),
                ("ship_to_location_override", ship_to_location_override),
            )
            if value is not None
        ]
        if supplied_overrides:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "edi_overrides_with_multiple_line_items",
                    "message": "Field overrides cannot apply to multiple ASN lines. Resubmit without overrides.",
                    "overrides": supplied_overrides,
                    "event_count": len(lines),
                },
            )

    placeholder_errors = _legacy_856_placeholder_errors(
        extracted=extracted,
        product_description_override=product_description,
        quantity_override=quantity_override,
        unit_override=unit_of_measure_override,
        ship_from_override=ship_from_location_override,
        ship_to_override=ship_to_location_override,
    )
    if placeholder_errors:
        _reject_legacy_856_placeholders(
            errors=placeholder_errors,
            sender_tenant_id=sender_tenant_id,
            traceability_lot_code=traceability_lot_code,
            extracted=extracted,
            partner_id=x_partner_id,
            source=source,
        )

    timestamp, ship_date = _ship_timestamp_and_date(
        extracted.get("ship_date_raw"),
        extracted.get("ship_time_raw"),
    )

    ship_from_name = (
        ship_from_location_override if ship_from_location_override is not None else extracted.get("ship_from_name")
    )
    ship_to_name = ship_to_location_override if ship_to_location_override is not None else extracted.get("ship_to_name")

    ship_from_gln_raw = extracted.get("ship_from_gln")
    ship_to_gln_raw = extracted.get("ship_to_gln")
    ship_from_gln = _valid_gln_or_none(ship_from_gln_raw)

    if not lines:
        lines = [{}]
    events: list[IngestEvent] = []
    for line_index, line in enumerate(lines, start=1):
        quantity = quantity_override if quantity_override is not None else line.get("quantity")
        resolved_quantity = _safe_float(
            str(quantity) if quantity is not None else None, fallback=0.0 if quantity is not None else 1.0
        )
        resolved_unit = _normalize_unit(unit_of_measure_override or line.get("unit_of_measure"))
        product_name = product_description or line.get("product_description") or "EDI 856 Shipment"
        lot = line.get("lot_number")
        line_tlc = lot.strip() if isinstance(lot, str) and lot.strip() else traceability_lot_code
        kdes: dict[str, Any] = {
            "location_incomplete": not is_location_description_complete(name=ship_from_name, gln=ship_from_gln_raw),
            "ship_date": ship_date,
            "ship_from_name": extracted.get("ship_from_name"),
            "ship_to_name": extracted.get("ship_to_name"),
            "ship_from_location": ship_from_name,
            "ship_to_location": ship_to_name,
            "ship_from_gln": ship_from_gln_raw,
            "ship_to_gln": ship_to_gln_raw,
            "reference_document_number": extracted.get("reference_document_number"),
            "carrier": extracted.get("carrier"),
            "asn_number": extracted.get("asn_number"),
            "edi_transaction_set": "856",
            "edi_control_number": extracted.get("control_number"),
            "edi_line_index": line_index,
            "lot_number": lot.strip() if isinstance(lot, str) and lot.strip() else None,
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
        events.append(
            IngestEvent(
                cte_type=WebhookCTEType.SHIPPING,
                traceability_lot_code=line_tlc,
                product_description=product_name,
                quantity=resolved_quantity,
                unit_of_measure=resolved_unit,
                # A-2170: accept and flag incomplete EDI locations; preserve raw KDEs.
                location_gln=ship_from_gln,
                location_name=ship_from_name,
                timestamp=timestamp,
                kdes={
                    k: v
                    for k, v in kdes.items()
                    if k.endswith(("_gln", "_name", "_location")) or (v is not None and v != "")
                },
            )
        )

    payload = WebhookPayload(
        source=source,
        events=events,
        tenant_id=sender_tenant_id,
    )
    ingestion_result = await ingest_events(
        payload,
        principal_tenant_id=sender_tenant_id,
        x_regengine_api_key=x_regengine_api_key,
    )

    return EDIIngestResponse(
        sender_tenant_id=sender_tenant_id,
        partner_id=x_partner_id,
        traceability_lot_code=events[0].traceability_lot_code,
        extracted={
            "asn_number": extracted.get("asn_number"),
            "quantity": events[0].quantity,
            "unit_of_measure": events[0].unit_of_measure,
            "ship_from_location": ship_from_name,
            "ship_to_location": ship_to_name,
            "reference_document_number": extracted.get("reference_document_number"),
            "event_count": len(events),
        },
        ingestion_result=ingestion_result,
    )


def _quantity_element_present(transaction_set: str, segments: list[list[str]]) -> bool:
    """True when a line-item segment included the quantity element.

    #2974: a document with no quantity element keeps the historical 1.0
    default. An element that is present but blank, zero, or non-numeric
    must fail closed. Requiring a non-blank value treated ``SN1*1**CA``
    as "no element" and the route then stored quantity 1.0.

    The quantity element is not at index 2 on every set. 944 reads W0701
    (quantity received). 945 reads W1203 (units shipped, not ordered).
    """
    wanted = _QUANTITY_SEGMENT_BY_SET.get(transaction_set)
    if not wanted:
        return False
    index = _QUANTITY_ELEMENT_INDEX_BY_SET.get(transaction_set, 2)
    return any(segment and segment[0].upper() == wanted and len(segment) > index for segment in segments)


def _build_ingest_event_for_set(
    transaction_set: str,
    extracted: dict[str, Any],
    traceability_lot_code: str,
    product_description_override: str | None,
    quantity_override: float | None,
    unit_override: str | None,
    location_override: str | None,
    segments: list[list[str]] | None = None,
) -> IngestEvent:
    """Build an IngestEvent from extracted EDI fields for any supported set."""
    cte_type = _CTE_TYPE_BY_SET.get(transaction_set, WebhookCTEType.SHIPPING)

    # Resolve quantity
    quantity = quantity_override if quantity_override is not None else extracted.get("quantity")

    # #2974: the legacy 856 endpoint refuses to synthesize a quantity;
    # this unified route silently re-created the same placeholder via the
    # 1.0 fallback below. Fail closed when the document DID send a
    # quantity element that could not produce a positive value — a
    # document with no quantity element at all keeps the old default.
    if quantity is None and segments is not None and _quantity_element_present(transaction_set, segments):
        logger.warning(
            "edi_non_positive_quantity set=%s — refusing to synthesize quantity=1.0",
            transaction_set,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "edi_non_positive_quantity",
                "message": (
                    f"EDI {transaction_set} carries a line-item quantity that is zero or "
                    "non-numeric; refusing to synthesize quantity=1.0. Correct the "
                    "supplier document or supply an operator-reviewed quantity override."
                ),
                "transaction_set": transaction_set,
            },
        )

    resolved_quantity = _safe_float(
        str(quantity) if quantity is not None else None, fallback=0.0 if quantity is not None else 1.0
    )

    # #2978: an X12 unit that is PRESENT but unrecognized must not be
    # coerced to "units" — that persists a numerically-correct,
    # semantically-meaningless quantity KDE with nothing in the response
    # to signal it. Matches the legacy 856 endpoint's behaviour.
    raw_unit = unit_override or extracted.get("unit_of_measure")
    if raw_unit is not None and str(raw_unit).strip() and _valid_unit_or_none(raw_unit) is None:
        logger.warning(
            "edi_uom_unmapped set=%s raw=%r — refusing to coerce to units",
            transaction_set,
            str(raw_unit).strip(),
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "edi_unmapped_unit_of_measure",
                "message": (
                    "EDI unit of measure is not a recognized X12 element-355 code; "
                    "refusing to coerce it to unit_of_measure='units'. Correct the "
                    "supplier document or supply an operator-reviewed unit override."
                ),
                "transaction_set": transaction_set,
                "unit_of_measure": str(raw_unit).strip(),
            },
        )

    resolved_unit = _normalize_unit(raw_unit)

    # Resolve product description
    product_name = product_description_override or extracted.get("product_description") or f"EDI {transaction_set} Item"

    # Resolve location (varies by document type)
    location_name = location_override
    location_gln_raw = None
    if transaction_set in ("856", "850", "945"):
        location_name = next(
            (
                value
                for value in (location_name, extracted.get("ship_from_name"), extracted.get("seller_name"))
                if value is not None
            ),
            None,
        )
        location_gln_raw = (
            extracted.get("ship_from_gln")
            if extracted.get("ship_from_gln") is not None
            else extracted.get("seller_gln")
        )
    elif transaction_set == "810":
        location_name = location_name if location_name is not None else extracted.get("seller_name")
        location_gln_raw = extracted.get("seller_gln")
    elif transaction_set in ("861", "944"):
        location_name = location_name if location_name is not None else extracted.get("receiving_location_name")
        location_gln_raw = extracted.get("receiving_location_gln")

    location_gln = _valid_gln_or_none(location_gln_raw)

    # Resolve timestamp
    date_field, time_field = _EVENT_DATE_FIELDS.get(transaction_set, (None, None))
    if transaction_set in ("944", "945") and extracted.get("_event_timestamp"):
        timestamp, event_date = extracted["_event_timestamp"], extracted["_event_date"]
    else:
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
        kdes.update(
            {
                "ship_from_location": extracted.get("ship_from_name"),
                "ship_to_location": extracted.get("ship_to_name"),
                "ship_from_gln": extracted.get("ship_from_gln"),
                "ship_to_gln": extracted.get("ship_to_gln"),
                "carrier": extracted.get("carrier"),
                "asn_number": extracted.get("asn_number"),
                "lot_number": extracted.get("lot_number"),
                "edi_line_index": extracted.get("edi_line_index"),
            }
        )
    elif transaction_set == "850":
        kdes.update(
            {
                "po_number": extracted.get("po_number"),
                "buyer_name": extracted.get("buyer_name"),
                "seller_name": extracted.get("seller_name"),
                "buyer_gln": extracted.get("buyer_gln"),
                "seller_gln": extracted.get("seller_gln"),
                "unit_price": extracted.get("unit_price"),
            }
        )
    elif transaction_set == "810":
        kdes.update(
            {
                "invoice_number": extracted.get("invoice_number"),
                "po_number": extracted.get("po_number"),
                "buyer_name": extracted.get("buyer_name"),
                "seller_name": extracted.get("seller_name"),
                "total_amount": extracted.get("total_amount"),
            }
        )
    elif transaction_set == "861":
        kdes.update(
            {
                "receiving_advice_number": extracted.get("receiving_advice_number"),
                "po_number": extracted.get("po_number"),
                "ship_from_location": extracted.get("ship_from_name"),
                "receiving_location": extracted.get("receiving_location_name"),
                "receiving_location_gln": extracted.get("receiving_location_gln"),
                "condition_code": extracted.get("condition_code"),
                "lot_number": extracted.get("lot_number"),
                "edi_line_index": extracted.get("edi_line_index"),
            }
        )
    elif transaction_set == "944":
        kdes.update(
            {
                "receiving_advice_number": extracted.get("warehouse_receipt_number"),
                "po_number": extracted.get("po_number"),
                "ship_from_location": extracted.get("ship_from_name"),
                "receiving_location": extracted.get("receiving_location_name"),
                "receiving_location_gln": extracted.get("receiving_location_gln"),
                "lot_number": extracted.get("lot_number"),
                "warehouse_name": extracted.get("warehouse_name"),
                "warehouse_id": extracted.get("warehouse_id"),
                "depositor_name": extracted.get("depositor_name"),
                "depositor_id": extracted.get("depositor_id"),
                "gtin": extracted.get("gtin"),
                "upc": extracted.get("upc"),
            }
        )
    elif transaction_set == "945":
        kdes.update(
            {
                "ship_from_location": extracted.get("ship_from_name"),
                "ship_to_location": extracted.get("ship_to_name"),
                "ship_from_gln": extracted.get("ship_from_gln"),
                "ship_to_gln": extracted.get("ship_to_gln"),
                "lot_number": extracted.get("lot_number"),
                "warehouse_name": extracted.get("warehouse_name"),
                "depositor_name": extracted.get("depositor_name"),
                "depositor_id": extracted.get("depositor_id"),
                "po_number": extracted.get("po_number"),
                "gtin": extracted.get("gtin"),
                "upc": extracted.get("upc"),
                "shipment_id": extracted.get("shipment_id"),
                "quantity_ordered": extracted.get("quantity_ordered"),
            }
        )

    if transaction_set in ("944", "945"):
        kdes.update(
            {
                "edi_line_index": extracted.get("edi_line_index"),
                "edi_isa_receiver_id": extracted.get("isa_receiver_id"),
                "edi_gs_receiver_id": extracted.get("gs_receiver_id"),
                "reporting_code": extracted.get("reporting_code"),
                "depositor_order_number": extracted.get("depositor_order_number"),
                "shipment_id": extracted.get("shipment_id"),
                "agent_shipment_id": extracted.get("agent_shipment_id"),
                "warehouse_receipt_number": extracted.get("warehouse_receipt_number"),
                "warehouse_name": extracted.get("warehouse_name"),
                "warehouse_id": extracted.get("warehouse_id"),
                "warehouse_id_qualifier": extracted.get("warehouse_id_qualifier"),
                "warehouse_gln": extracted.get("warehouse_gln"),
                "depositor_name": extracted.get("depositor_name"),
                "depositor_id": extracted.get("depositor_id"),
                "depositor_id_qualifier": extracted.get("depositor_id_qualifier"),
                "ship_from_gln": extracted.get("ship_from_gln"),
                "ship_to_location": extracted.get("ship_to_name"),
                "ship_to_gln": extracted.get("ship_to_gln"),
                "bill_of_lading": extracted.get("bill_of_lading"),
                "reference_numbers": dict(extracted.get("reference_numbers") or {}),
                "g62_date_raw": extracted.get("g62_date_raw"),
                "g62_date_qualifier": extracted.get("g62_date_qualifier"),
                "receive_date_raw": extracted.get("receive_date_raw"),
                "ship_date_raw": extracted.get("ship_date_raw"),
                "reference_document": extracted.get("reference_document_number"),
                "tlc_source_reference": extracted.get("tlc_source_reference"),
            }
        )
        if transaction_set == "944":
            kdes["receive_date"] = event_date
            kdes["immediate_previous_source"] = extracted.get("ship_from_name") or extracted.get("ship_from_gln")
        else:
            kdes["ship_date"] = event_date
        if extracted.get("depositor_gln"):
            kdes["depositor_gln"] = extracted["depositor_gln"]

    kdes["location_incomplete"] = not is_location_description_complete(name=location_name, gln=location_gln_raw)
    # Retain even empty raw location values for audit evidence.
    kdes.update({key: value for key, value in extracted.items() if key.endswith(("_gln", "_name"))})

    return IngestEvent(
        cte_type=cte_type,
        traceability_lot_code=traceability_lot_code,
        product_description=product_name,
        quantity=resolved_quantity,
        unit_of_measure=resolved_unit,
        # A-2170: accept and flag incomplete EDI locations; preserve raw KDEs.
        location_gln=location_gln,
        location_name=location_name,
        timestamp=timestamp,
        kdes={
            k: v for k, v in kdes.items() if k.endswith(("_gln", "_name", "_location")) or (v is not None and v != "")
        },
    )


@router.post(
    "/document",
    response_model=EDIIngestResponse,
    status_code=201,
    summary="Ingest X12 EDI document (856/850/810/861/944/945)",
    description=(
        "Unified EDI inbound route that auto-detects the transaction set "
        "(856 ASN, 850 Purchase Order, 810 Invoice, 861 Receiving Advice, "
        "944 Warehouse Stock Transfer Receipt Advice, "
        "945 Warehouse Shipping Advice) "
        "and extracts FSMA-relevant KDEs for CTE creation."
    ),
)
async def ingest_edi_document(
    file: UploadFile = File(..., description="X12 EDI file"),
    traceability_lot_code: str = Form(
        ...,
        description="FSMA Traceability Lot Code for 856/850/810/861; required but ignored for 944/945 event TLCs, which use each line's lot code",
    ),
    tlc_source_reference: Optional[str] = Form(
        None, description="Optional TLC source reference copied to 944/945 KDEs"
    ),
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
    principal: IngestionPrincipal = Depends(require_permission("edi.ingest")),
) -> EDIIngestResponse:
    """Ingest any supported X12 EDI document type."""
    sender_tenant_id = _resolve_principal_tenant_id(tenant_id, x_tenant_id, principal.tenant_id)

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
            sender_tenant_id,
            len(raw_bytes),
            exc.start,
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

    # #2976: decompose the interchange into ST/SE transaction sets before
    # anything reads a body segment. Previously every extractor walked
    # the whole flat list and exactly one event was built, so a batched
    # file returned 201 while sets 2..N were dropped and their segments
    # bled into the survivor.
    set_slices = _split_transaction_sets(segments)
    _enforce_interchange_structure(segments, set_slices)

    slice_sets = [_detect_transaction_set(slice_segments) for slice_segments in set_slices]
    if any(slice_set is None for slice_set in slice_sets):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported or unrecognized transaction set. Supported: {sorted(_SUPPORTED_TRANSACTION_SETS)}",
        )
    if len(set(slice_sets)) > 1:
        # A functional group is pinned to one transaction set type by
        # GS01, so a mixed group is malformed — and the response contract
        # carries a single ``document_type``.
        raise HTTPException(
            status_code=422,
            detail={
                "error": "mixed_transaction_sets",
                "message": (
                    "One X12 functional group must carry a single transaction "
                    "set type. Split the interchange by document type."
                ),
                "transaction_sets": sorted(set(slice_sets)),
            },
        )

    extractions: list[dict[str, Any]] = []
    for slice_index, (slice_segments, slice_set) in enumerate(zip(set_slices, slice_sets)):
        required_segments = _REQUIRED_SEGMENTS_BY_SET.get(slice_set, set())
        present_segments = _segment_id_set(slice_segments)
        missing_segments = sorted(required_segments - present_segments)
        if missing_segments:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": f"EDI {slice_set} missing required segments",
                    "missing_segments": missing_segments,
                    "transaction_set_index": slice_index,
                },
            )
        extractions.append(_extract_fields_for_set(slice_set, slice_segments))

    extracted = extractions[0]

    # #1160 + #1165: validate and reserve the shared envelope once per
    # document, before validating any transaction set or warehouse line.
    def _preflight_all_sets() -> None:
        for slice_set, slice_extracted in zip(slice_sets, extractions):
            _preflight_event_date(
                transaction_set=slice_set,
                extracted=slice_extracted,
                sender_tenant_id=sender_tenant_id,
                traceability_lot_code=traceability_lot_code,
                partner_id=x_partner_id,
                source=source,
            )

    # Event-date rejections run after the allowlist and before the ISA13
    # is reserved, so a corrected resend is not refused as a 409 replay.
    _enforce_envelope_integrity(extracted, sender_tenant_id, transaction_set, before_reserve=_preflight_all_sets)

    # 856 SN1, 861 RCD, and warehouse W07/W12 lines are each one CTE.
    # ST/SE extraction and envelope handling stay at document scope, then
    # the shared header is copied onto each line.
    event_inputs: list[tuple[str, dict[str, Any], list[list[str]]]] = []
    first_event_indexes: list[int] = []
    for slice_set, slice_extracted, slice_segments in zip(slice_sets, extractions, set_slices):
        first_event_indexes.append(len(event_inputs))
        if slice_set in ("856", "861", "944", "945"):
            header = {key: value for key, value in slice_extracted.items() if key != "line_items"}
            if slice_set in ("944", "945"):
                header["tlc_source_reference"] = tlc_source_reference.strip() if tlc_source_reference else None
                date_field = "receive_date_raw" if slice_set == "944" else "ship_date_raw"
                header["_event_timestamp"], header["_event_date"] = _ship_timestamp_and_date(
                    header.get(date_field), None
                )
            # A header with no item segment still follows the same FSMA
            # validation/rejection path as a line missing its quantity.
            lines = slice_extracted["line_items"] or [{"quantity": None, "lot_number": None}]
            for line in lines:
                merged = {
                    **header,
                    **line,
                    "edi_line_index": len(event_inputs) + 1,
                }
                if slice_set in ("944", "945"):
                    # LT identifies one lot, so a header LT cannot be
                    # copied as a reference for unrelated lines.
                    merged["reference_numbers"] = {
                        key: value
                        for key, value in header["reference_numbers"].items()
                        if key != "LT" or value == line.get("lot_number")
                    }
                event_inputs.append((slice_set, merged, slice_segments))
        else:
            event_inputs.append((slice_set, slice_extracted, slice_segments))

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
    #
    # #2976: every transaction set is validated. If ANY set fails, the
    # whole interchange stays out of the canonical stream — a batch must
    # not half-land.
    rejection_record: dict[str, Any] | None = None
    for slice_set, slice_extracted, _ in event_inputs:
        try:
            validated = _validate_edi_as_fsma_event(
                slice_extracted,
                slice_set,
                traceability_lot_code,
                sender_tenant_id,
            )
            if slice_set in ("856", "861", "944", "945"):
                slice_extracted["traceability_lot_code"] = validated["tlc"]
            slice_extracted["fsma_validation_status"] = "passed"
        except ValidationError as ve:
            errors = ve.errors(include_context=False) if slice_set in ("856", "861", "944", "945") else ve.errors()
            strict_effective = strict and _edi_strict_mode()
            if strict_effective:
                logger.warning(
                    "edi_fsma_validation_rejected set=%s tlc=%s errors=%d",
                    slice_set,
                    traceability_lot_code,
                    len(errors),
                )
                # Record on the strict path too — the canonical stream is
                # untouched either way, but auditors still need the trail.
                _record_edi_rejection(
                    tenant_id=sender_tenant_id,
                    transaction_set=slice_set,
                    traceability_lot_code=traceability_lot_code,
                    errors=errors,
                    extracted=slice_extracted,
                    partner_id=x_partner_id,
                    source=source,
                )
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "fsma_validation_failed",
                        "transaction_set": slice_set,
                        "tlc": traceability_lot_code,
                        "message": (
                            "EDI document failed FSMAEvent schema validation. "
                            "No events were persisted. Pass ?strict=false or "
                            "set EDI_STRICT_MODE=false only for migration "
                            "windows — failed rows are written to the EDI "
                            "rejection log, never the canonical FSMA stream."
                        ),
                        "errors": errors,
                    },
                )
            # Advisory mode: record the rejection separately and short-
            # circuit before the canonical write. We do NOT call
            # ``ingest_events`` — that would put the invalid event into the
            # audit trail with ``fsma_validation_status=failed``, which is
            # exactly the pollution #1174 is meant to stop.
            slice_extracted["fsma_validation_status"] = "failed"
            recorded = _record_edi_rejection(
                tenant_id=sender_tenant_id,
                transaction_set=slice_set,
                traceability_lot_code=traceability_lot_code,
                errors=errors,
                extracted=slice_extracted,
                partner_id=x_partner_id,
                source=source,
            )
            rejection_record = rejection_record or recorded
        except ImportError:
            if slice_set in ("944", "945"):
                raise HTTPException(
                    status_code=503,
                    detail="Warehouse line validation is unavailable; no events were persisted.",
                )
            logger.debug("shared.schemas not available — skipping FSMA validation")
            slice_extracted["fsma_validation_status"] = "unknown"

    def _summarize(slice_set: str, slice_extracted: dict[str, Any]) -> dict[str, Any]:
        summary = {
            "transaction_set": slice_set,
            "control_number": slice_extracted.get("control_number"),
            "quantity": slice_extracted.get("quantity"),
            "unit_of_measure": slice_extracted.get("unit_of_measure"),
            "product_description": slice_extracted.get("product_description"),
            "reference_document_number": slice_extracted.get("reference_document_number"),
            "fsma_validation_status": slice_extracted.get("fsma_validation_status"),
        }
        if slice_set in ("856", "861", "944", "945"):
            summary.update(
                line_index=slice_extracted.get("edi_line_index"),
                traceability_lot_code=slice_extracted.get("traceability_lot_code"),
                lot_number=slice_extracted.get("lot_number"),
            )
        if slice_set in ("944", "945"):
            summary.update(
                gtin=slice_extracted.get("gtin"),
                upc=slice_extracted.get("upc"),
            )
            if slice_set == "945":
                summary["quantity_ordered"] = slice_extracted.get("quantity_ordered")
        return summary

    summaries = [_summarize(slice_set, item) for slice_set, item, _ in event_inputs]
    # Keep the first set's fields at the top level for callers written
    # against the single-transaction-set response, and expose the full
    # batch alongside them (#2976).
    extracted_summary: dict[str, Any] = dict(summaries[0])
    extracted_summary["transaction_set_count"] = len(slice_sets)
    extracted_summary["transaction_sets"] = [summaries[index] for index in first_event_indexes]
    if transaction_set in ("856", "861", "944", "945"):
        extracted_summary["event_count"] = len(summaries)
        extracted_summary["events"] = summaries
        extracted_summary["submitted_traceability_lot_code"] = traceability_lot_code

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
            extracted=extracted_summary,
            ingestion_result=None,
            rejection={
                "rejection_id": rejection_record["rejection_id"],
                "reason": rejection_record["reason"],
                "recorded_at": rejection_record["recorded_at"],
                "error_count": len(rejection_record["errors"]),
            },
        )

    # Review on #2991: scalar form overrides describe ONE shipment. Applying
    # them across a batch would overwrite each transaction set's distinct
    # extracted values with a single value -- reintroducing, through the
    # override path, exactly the cross-shipment field bleed #2976 fixes.
    # Refuse rather than silently collapse; a caller who means it can post
    # each transaction set separately.
    if len(slice_sets) > 1:
        _supplied_overrides = [
            name
            for name, value in (
                ("product_description", product_description),
                ("quantity_override", quantity_override),
                ("unit_of_measure_override", unit_of_measure_override),
                ("location_override", location_override),
            )
            if value is not None
        ]
        if _supplied_overrides:
            logger.warning(
                "edi_overrides_rejected_for_batch partner=%s sets=%d overrides=%s",
                x_partner_id,
                len(slice_sets),
                ",".join(_supplied_overrides),
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "edi_overrides_with_multiple_transaction_sets",
                    "message": (
                        "Field overrides apply to a single shipment, but this "
                        "interchange carries "
                        f"{len(slice_sets)} transaction sets. Applying one "
                        "override across all of them would overwrite each "
                        "set's own values. Post each transaction set "
                        "separately, or resubmit without overrides."
                    ),
                    "overrides": _supplied_overrides,
                    "transaction_set_count": len(slice_sets),
                },
            )

    if transaction_set in ("856", "861", "944", "945") and len(event_inputs) > len(slice_sets):
        supplied_overrides = [
            name
            for name, value in (
                ("product_description", product_description),
                ("quantity_override", quantity_override),
                ("unit_of_measure_override", unit_of_measure_override),
                ("location_override", location_override),
            )
            if value is not None
        ]
        if supplied_overrides:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "edi_overrides_with_multiple_line_items",
                    "message": "Field overrides cannot apply to multiple warehouse lines. Resubmit without overrides.",
                    "overrides": supplied_overrides,
                    "event_count": len(event_inputs),
                },
            )

    events = [
        _build_ingest_event_for_set(
            transaction_set=slice_set,
            extracted=slice_extracted,
            traceability_lot_code=slice_extracted.get("traceability_lot_code", traceability_lot_code),
            product_description_override=product_description,
            quantity_override=quantity_override,
            unit_override=unit_of_measure_override,
            location_override=location_override,
            segments=slice_segments,
        )
        for slice_set, slice_extracted, slice_segments in event_inputs
    ]

    payload = WebhookPayload(
        source=f"{source}_{transaction_set}" if source == "edi_inbound" else source,
        events=events,
        tenant_id=sender_tenant_id,
    )
    ingestion_result = await ingest_events(
        payload,
        principal_tenant_id=sender_tenant_id,
        x_regengine_api_key=x_regengine_api_key,
    )

    return EDIIngestResponse(
        document_type=f"X12_{transaction_set}",
        sender_tenant_id=sender_tenant_id,
        partner_id=x_partner_id,
        traceability_lot_code=(
            events[0].traceability_lot_code
            if transaction_set in ("856", "861", "944", "945")
            else traceability_lot_code
        ),
        extracted=extracted_summary,
        ingestion_result=ingestion_result,
    )
