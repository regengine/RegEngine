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

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text

from app.authz import require_permission
from app.format_extractors import is_edi_content
from app.shared.tenant_resolution import resolve_tenant_id
from app.shared.upload_limits import read_upload_with_limit, MAX_EDI_FILE_SIZE_BYTES
from app.webhook_compat import ingest_events
from app.webhook_models import (
    IngestEvent,
    IngestResponse,
    VALID_UNITS_OF_MEASURE,
    WebhookCTEType,
    WebhookPayload,
)

logger = logging.getLogger("edi-ingestion")

router = APIRouter(prefix="/api/v1/ingest/edi", tags=["EDI Import"])

_X12_UOM_MAP = {
    "CA": "cases",
    "CAS": "cases",
    "LB": "lbs",
    "LBR": "lbs",
    "KG": "kg",
    "EA": "each",
    "UN": "units",
    "PL": "pallets",
    "CTN": "cartons",
    "BOX": "boxes",
    "PC": "pieces",
    "PK": "pieces",
}

_FROM_ENTITY_CODES = {"SF", "SU", "SH"}
_TO_ENTITY_CODES = {"ST", "BT", "OB"}
_REQUIRED_856_SEGMENTS = {"ISA", "GS", "ST", "BSN", "HL", "SE", "GE", "IEA"}


_SUPPORTED_TRANSACTION_SETS = {"856", "850", "810", "861"}

_REQUIRED_850_SEGMENTS = {"ISA", "GS", "ST", "BEG", "SE", "GE", "IEA"}
_REQUIRED_810_SEGMENTS = {"ISA", "GS", "ST", "BIG", "SE", "GE", "IEA"}
_REQUIRED_861_SEGMENTS = {"ISA", "GS", "ST", "BRA", "SE", "GE", "IEA"}

_REQUIRED_SEGMENTS_BY_SET: dict[str, set[str]] = {
    "856": _REQUIRED_856_SEGMENTS,
    "850": _REQUIRED_850_SEGMENTS,
    "810": _REQUIRED_810_SEGMENTS,
    "861": _REQUIRED_861_SEGMENTS,
}

_CTE_TYPE_BY_SET: dict[str, WebhookCTEType] = {
    "856": WebhookCTEType.SHIPPING,
    "850": WebhookCTEType.SHIPPING,
    "810": WebhookCTEType.SHIPPING,
    "861": WebhookCTEType.RECEIVING,
}


class EDIIngestResponse(BaseModel):
    """Response for EDI ingestion requests."""

    status: str = "accepted"
    parser_name: str = "edi_parser"
    document_type: str = "X12_856"
    sender_tenant_id: str
    partner_id: Optional[str] = None
    traceability_lot_code: str
    extracted: dict[str, Any] = Field(default_factory=dict)
    ingestion_result: IngestResponse


_resolve_tenant_id = resolve_tenant_id


def _verify_partner_id(x_partner_id: Optional[str]) -> None:
    required = os.getenv("EDI_REQUIRE_PARTNER_ID", "").lower() in {"1", "true", "yes"}
    if required and not x_partner_id:
        raise HTTPException(status_code=400, detail="X-Partner-ID header required for EDI ingest")

    allowlist_raw = os.getenv("EDI_PARTNER_ALLOWLIST", "")
    allowlist = {item.strip() for item in allowlist_raw.split(",") if item.strip()}
    if allowlist and x_partner_id and x_partner_id not in allowlist:
        raise HTTPException(status_code=403, detail="Partner not authorized for EDI ingest")


def _parse_x12_segments(content: str) -> list[list[str]]:
    compact = content.replace("\n", "").replace("\r", "")
    element_sep = compact[3] if len(compact) > 3 and compact[3].strip() else "*"
    segment_term = compact[105] if len(compact) > 105 and compact[105].strip() else "~"
    raw_segments = compact.split(segment_term)

    segments: list[list[str]] = []
    for segment in raw_segments:
        cleaned = segment.strip()
        if not cleaned:
            continue
        parts = [part.strip() for part in cleaned.split(element_sep)]
        if parts and parts[0]:
            segments.append(parts)
    return segments


def _segment_id_set(segments: list[list[str]]) -> set[str]:
    return {segment[0].upper() for segment in segments if segment}


def _first_segment(segments: list[list[str]], segment_id: str) -> Optional[list[str]]:
    wanted = segment_id.upper()
    for segment in segments:
        if segment and segment[0].upper() == wanted:
            return segment
    return None


def _normalize_unit(unit_value: Optional[str]) -> str:
    if not unit_value:
        return "units"

    x12_code = re.sub(r"[^A-Za-z]", "", unit_value).upper()
    mapped = _X12_UOM_MAP.get(x12_code, unit_value.strip().lower())
    if mapped not in VALID_UNITS_OF_MEASURE:
        return "units"
    return mapped


def _safe_float(value: Optional[str], fallback: float = 1.0) -> float:
    if value is None:
        return fallback
    try:
        parsed = float(value)
        if parsed > 0:
            return parsed
    except (TypeError, ValueError):
        pass
    return fallback


def _valid_gln_or_none(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    clean = re.sub(r"\D", "", value)
    if len(clean) != 13:
        return None

    total = sum(
        int(digit) * (3 if index % 2 else 1)
        for index, digit in enumerate(reversed(clean[:-1]))
    )
    expected = (10 - (total % 10)) % 10
    return clean if int(clean[-1]) == expected else None


def _extract_856_fields(segments: list[list[str]]) -> dict[str, Any]:
    data: dict[str, Any] = {
        "sender_id": None,
        "receiver_id": None,
        "control_number": None,
        "asn_number": None,
        "ship_date_raw": None,
        "ship_time_raw": None,
        "ship_from_name": None,
        "ship_from_gln": None,
        "ship_to_name": None,
        "ship_to_gln": None,
        "quantity": None,
        "unit_of_measure": None,
        "product_description": None,
        "reference_document_number": None,
        "carrier": None,
    }

    isa = _first_segment(segments, "ISA")
    if isa:
        data["sender_id"] = isa[6] if len(isa) > 6 else None
        data["receiver_id"] = isa[8] if len(isa) > 8 else None

    st = _first_segment(segments, "ST")
    if st and len(st) > 2:
        data["control_number"] = st[2]

    bsn = _first_segment(segments, "BSN")
    if bsn:
        data["asn_number"] = bsn[2] if len(bsn) > 2 else None
        data["ship_date_raw"] = bsn[3] if len(bsn) > 3 else None
        data["ship_time_raw"] = bsn[4] if len(bsn) > 4 else None

    for segment in segments:
        if not segment:
            continue
        seg_id = segment[0].upper()

        if seg_id == "N1":
            entity_code = segment[1].upper() if len(segment) > 1 else ""
            name = segment[2] if len(segment) > 2 and segment[2] else None
            location_id = segment[4] if len(segment) > 4 and segment[4] else None

            if entity_code in _FROM_ENTITY_CODES:
                data["ship_from_name"] = data["ship_from_name"] or name
                data["ship_from_gln"] = data["ship_from_gln"] or location_id
            elif entity_code in _TO_ENTITY_CODES:
                data["ship_to_name"] = data["ship_to_name"] or name
                data["ship_to_gln"] = data["ship_to_gln"] or location_id

        elif seg_id == "SN1":
            if len(segment) > 2 and segment[2]:
                data["quantity"] = _safe_float(segment[2], fallback=1.0)
            if len(segment) > 3 and segment[3]:
                data["unit_of_measure"] = segment[3]

        elif seg_id == "PID":
            if len(segment) > 5 and segment[5]:
                data["product_description"] = data["product_description"] or segment[5]

        elif seg_id == "LIN":
            for idx in range(1, len(segment) - 1):
                qualifier = segment[idx].upper()
                if qualifier in {"SK", "UP", "EN", "VP", "BP"} and segment[idx + 1]:
                    data["product_description"] = data["product_description"] or segment[idx + 1]
                    break

        elif seg_id == "REF":
            if len(segment) > 2 and segment[2]:
                qualifier = segment[1].upper() if len(segment) > 1 else ""
                if qualifier in {"BM", "SI", "CN", "PO", "PK"}:
                    data["reference_document_number"] = (
                        data["reference_document_number"] or segment[2]
                    )

        elif seg_id == "TD5":
            # Favor carrier name/code if present in routing details.
            for candidate in segment[2:]:
                if candidate:
                    data["carrier"] = data["carrier"] or candidate
                    if data["carrier"]:
                        break

    if not data["reference_document_number"]:
        data["reference_document_number"] = data["asn_number"]

    return data


def _ship_timestamp_and_date(ship_date_raw: Optional[str], ship_time_raw: Optional[str]) -> tuple[str, str]:
    now = datetime.now(timezone.utc)

    if not ship_date_raw:
        return now.isoformat(), now.date().isoformat()

    clean_date = re.sub(r"\D", "", ship_date_raw)
    if len(clean_date) != 8:
        return now.isoformat(), now.date().isoformat()

    clean_time = re.sub(r"\D", "", ship_time_raw or "")
    if len(clean_time) >= 4:
        hh = int(clean_time[:2])
        mm = int(clean_time[2:4])
    else:
        hh = 0
        mm = 0

    try:
        parsed = datetime(
            year=int(clean_date[:4]),
            month=int(clean_date[4:6]),
            day=int(clean_date[6:8]),
            hour=hh,
            minute=mm,
            tzinfo=timezone.utc,
        )
    except ValueError:
        return now.isoformat(), now.date().isoformat()

    # Keep webhook model bounds to avoid stale/future rejection.
    if parsed < now - timedelta(days=90) or parsed > now + timedelta(hours=24):
        return now.isoformat(), parsed.date().isoformat()

    return parsed.isoformat(), parsed.date().isoformat()


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

    raw_text = raw_bytes.decode("utf-8", errors="ignore")
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
        "edi_sender_id": extracted.get("sender_id"),
        "edi_receiver_id": extracted.get("receiver_id"),
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


# ---------------------------------------------------------------------------
# Extractors for additional EDI transaction sets
# ---------------------------------------------------------------------------


def _extract_850_fields(segments: list[list[str]]) -> dict[str, Any]:
    """Extract fields from X12 850 Purchase Order."""
    data: dict[str, Any] = {
        "sender_id": None,
        "receiver_id": None,
        "control_number": None,
        "po_number": None,
        "po_date_raw": None,
        "buyer_name": None,
        "buyer_gln": None,
        "seller_name": None,
        "seller_gln": None,
        "quantity": None,
        "unit_of_measure": None,
        "product_description": None,
        "unit_price": None,
        "reference_document_number": None,
    }

    isa = _first_segment(segments, "ISA")
    if isa:
        data["sender_id"] = isa[6] if len(isa) > 6 else None
        data["receiver_id"] = isa[8] if len(isa) > 8 else None

    st = _first_segment(segments, "ST")
    if st and len(st) > 2:
        data["control_number"] = st[2]

    beg = _first_segment(segments, "BEG")
    if beg:
        data["po_number"] = beg[3] if len(beg) > 3 else None
        data["po_date_raw"] = beg[5] if len(beg) > 5 else None

    data["reference_document_number"] = data["po_number"]

    total_quantity = 0.0
    for segment in segments:
        if not segment:
            continue
        seg_id = segment[0].upper()

        if seg_id == "N1":
            entity_code = segment[1].upper() if len(segment) > 1 else ""
            name = segment[2] if len(segment) > 2 and segment[2] else None
            location_id = segment[4] if len(segment) > 4 and segment[4] else None
            if entity_code in {"BY", "BT"}:
                data["buyer_name"] = data["buyer_name"] or name
                data["buyer_gln"] = data["buyer_gln"] or location_id
            elif entity_code in {"SE", "SU", "VN"}:
                data["seller_name"] = data["seller_name"] or name
                data["seller_gln"] = data["seller_gln"] or location_id

        elif seg_id == "PO1":
            if len(segment) > 2 and segment[2]:
                total_quantity += _safe_float(segment[2], fallback=0.0)
            if len(segment) > 3 and segment[3]:
                data["unit_of_measure"] = data["unit_of_measure"] or segment[3]
            if len(segment) > 4 and segment[4]:
                data["unit_price"] = data["unit_price"] or segment[4]
            # Product identifier in qualifier/value pairs
            for idx in range(6, len(segment) - 1, 2):
                qualifier = segment[idx].upper() if segment[idx] else ""
                if qualifier in {"SK", "UP", "EN", "VP", "BP", "IN"} and segment[idx + 1]:
                    data["product_description"] = data["product_description"] or segment[idx + 1]
                    break

        elif seg_id == "PID":
            if len(segment) > 5 and segment[5]:
                data["product_description"] = data["product_description"] or segment[5]

    if total_quantity > 0:
        data["quantity"] = total_quantity

    return data


def _extract_810_fields(segments: list[list[str]]) -> dict[str, Any]:
    """Extract fields from X12 810 Invoice."""
    data: dict[str, Any] = {
        "sender_id": None,
        "receiver_id": None,
        "control_number": None,
        "invoice_number": None,
        "invoice_date_raw": None,
        "po_number": None,
        "buyer_name": None,
        "buyer_gln": None,
        "seller_name": None,
        "seller_gln": None,
        "quantity": None,
        "unit_of_measure": None,
        "product_description": None,
        "total_amount": None,
        "reference_document_number": None,
    }

    isa = _first_segment(segments, "ISA")
    if isa:
        data["sender_id"] = isa[6] if len(isa) > 6 else None
        data["receiver_id"] = isa[8] if len(isa) > 8 else None

    st = _first_segment(segments, "ST")
    if st and len(st) > 2:
        data["control_number"] = st[2]

    big = _first_segment(segments, "BIG")
    if big:
        data["invoice_date_raw"] = big[1] if len(big) > 1 else None
        data["invoice_number"] = big[2] if len(big) > 2 else None
        data["po_number"] = big[4] if len(big) > 4 and big[4] else None

    data["reference_document_number"] = data["invoice_number"]

    total_quantity = 0.0
    for segment in segments:
        if not segment:
            continue
        seg_id = segment[0].upper()

        if seg_id == "N1":
            entity_code = segment[1].upper() if len(segment) > 1 else ""
            name = segment[2] if len(segment) > 2 and segment[2] else None
            location_id = segment[4] if len(segment) > 4 and segment[4] else None
            if entity_code in {"BY", "BT", "RI"}:
                data["buyer_name"] = data["buyer_name"] or name
                data["buyer_gln"] = data["buyer_gln"] or location_id
            elif entity_code in {"SE", "SU", "VN", "SF"}:
                data["seller_name"] = data["seller_name"] or name
                data["seller_gln"] = data["seller_gln"] or location_id

        elif seg_id == "IT1":
            if len(segment) > 2 and segment[2]:
                total_quantity += _safe_float(segment[2], fallback=0.0)
            if len(segment) > 3 and segment[3]:
                data["unit_of_measure"] = data["unit_of_measure"] or segment[3]
            for idx in range(6, len(segment) - 1, 2):
                qualifier = segment[idx].upper() if segment[idx] else ""
                if qualifier in {"SK", "UP", "EN", "VP", "IN"} and segment[idx + 1]:
                    data["product_description"] = data["product_description"] or segment[idx + 1]
                    break

        elif seg_id == "PID":
            if len(segment) > 5 and segment[5]:
                data["product_description"] = data["product_description"] or segment[5]

        elif seg_id == "TDS":
            if len(segment) > 1 and segment[1]:
                try:
                    data["total_amount"] = float(segment[1]) / 100.0
                except (ValueError, TypeError):
                    pass

        elif seg_id == "REF":
            if len(segment) > 2 and segment[2]:
                qualifier = segment[1].upper() if len(segment) > 1 else ""
                if qualifier in {"PO", "VN", "IV"}:
                    if qualifier == "PO":
                        data["po_number"] = data["po_number"] or segment[2]

    if total_quantity > 0:
        data["quantity"] = total_quantity

    return data


def _extract_861_fields(segments: list[list[str]]) -> dict[str, Any]:
    """Extract fields from X12 861 Receiving Advice."""
    data: dict[str, Any] = {
        "sender_id": None,
        "receiver_id": None,
        "control_number": None,
        "receiving_advice_number": None,
        "receive_date_raw": None,
        "po_number": None,
        "ship_from_name": None,
        "ship_from_gln": None,
        "receiving_location_name": None,
        "receiving_location_gln": None,
        "quantity": None,
        "unit_of_measure": None,
        "product_description": None,
        "reference_document_number": None,
        "condition_code": None,
    }

    isa = _first_segment(segments, "ISA")
    if isa:
        data["sender_id"] = isa[6] if len(isa) > 6 else None
        data["receiver_id"] = isa[8] if len(isa) > 8 else None

    st = _first_segment(segments, "ST")
    if st and len(st) > 2:
        data["control_number"] = st[2]

    bra = _first_segment(segments, "BRA")
    if bra:
        data["receiving_advice_number"] = bra[2] if len(bra) > 2 else None
        data["receive_date_raw"] = bra[3] if len(bra) > 3 else None

    data["reference_document_number"] = data["receiving_advice_number"]

    total_quantity = 0.0
    for segment in segments:
        if not segment:
            continue
        seg_id = segment[0].upper()

        if seg_id == "N1":
            entity_code = segment[1].upper() if len(segment) > 1 else ""
            name = segment[2] if len(segment) > 2 and segment[2] else None
            location_id = segment[4] if len(segment) > 4 and segment[4] else None
            if entity_code in _FROM_ENTITY_CODES:
                data["ship_from_name"] = data["ship_from_name"] or name
                data["ship_from_gln"] = data["ship_from_gln"] or location_id
            elif entity_code in _TO_ENTITY_CODES:
                data["receiving_location_name"] = data["receiving_location_name"] or name
                data["receiving_location_gln"] = data["receiving_location_gln"] or location_id

        elif seg_id == "RCD":
            if len(segment) > 2 and segment[2]:
                total_quantity += _safe_float(segment[2], fallback=0.0)
            if len(segment) > 3 and segment[3]:
                data["unit_of_measure"] = data["unit_of_measure"] or segment[3]
            if len(segment) > 5 and segment[5]:
                data["condition_code"] = data["condition_code"] or segment[5]

        elif seg_id == "LIN":
            for idx in range(1, len(segment) - 1):
                qualifier = segment[idx].upper()
                if qualifier in {"SK", "UP", "EN", "VP", "BP"} and segment[idx + 1]:
                    data["product_description"] = data["product_description"] or segment[idx + 1]
                    break

        elif seg_id == "PID":
            if len(segment) > 5 and segment[5]:
                data["product_description"] = data["product_description"] or segment[5]

        elif seg_id == "REF":
            if len(segment) > 2 and segment[2]:
                qualifier = segment[1].upper() if len(segment) > 1 else ""
                if qualifier in {"PO", "BM", "SI"}:
                    if qualifier == "PO":
                        data["po_number"] = data["po_number"] or segment[2]
                    data["reference_document_number"] = (
                        data["reference_document_number"] or segment[2]
                    )

    if total_quantity > 0:
        data["quantity"] = total_quantity

    return data


# ---------------------------------------------------------------------------
# FSMAEvent validation for EDI-extracted data
# ---------------------------------------------------------------------------


def _validate_edi_as_fsma_event(
    extracted: dict[str, Any],
    transaction_set: str,
    tlc: str,
    tenant_id: str | None = None,
) -> dict | None:
    """Validate EDI-extracted data against the FSMAEvent Pydantic model.

    Returns the validated model dict on success, or None on failure.
    """
    try:
        from shared.schemas import FSMAEvent, FSMAEventType

        type_map = {
            "856": FSMAEventType.SHIPPING,
            "850": FSMAEventType.SHIPPING,
            "810": FSMAEventType.SHIPPING,
            "861": FSMAEventType.RECEIVING,
        }
        fsma_type = type_map.get(transaction_set, FSMAEventType.SHIPPING)

        # Resolve location GLN from whichever field is available
        location_gln = (
            extracted.get("ship_from_gln")
            or extracted.get("seller_gln")
            or extracted.get("receiving_location_gln")
            or extracted.get("buyer_gln")
        )

        source_gln = extracted.get("ship_from_gln") or extracted.get("seller_gln")
        dest_gln = (
            extracted.get("ship_to_gln")
            or extracted.get("buyer_gln")
            or extracted.get("receiving_location_gln")
        )

        event_time = datetime.now(timezone.utc).isoformat()
        for date_field in ("ship_date_raw", "po_date_raw", "invoice_date_raw", "receive_date_raw"):
            raw_date = extracted.get(date_field)
            if raw_date:
                clean = re.sub(r"\D", "", raw_date)
                if len(clean) == 8:
                    try:
                        dt = datetime(
                            year=int(clean[:4]), month=int(clean[4:6]), day=int(clean[6:8]),
                            tzinfo=timezone.utc,
                        )
                        event_time = dt.isoformat()
                        break
                    except ValueError:
                        pass

        doc_type_map = {
            "856": "EDI_856",
            "850": "EDI_850",
            "810": "EDI_810",
            "861": "EDI_861",
        }

        fsma_event = FSMAEvent(
            event_type=fsma_type,
            tlc=tlc,
            product_description=extracted.get("product_description") or f"EDI {transaction_set} Item",
            quantity=extracted.get("quantity"),
            unit_of_measure=extracted.get("unit_of_measure"),
            location_gln=_valid_gln_or_none(location_gln),
            event_time=event_time,
            source_gln=_valid_gln_or_none(source_gln),
            destination_gln=_valid_gln_or_none(dest_gln),
            reference_document_type=doc_type_map.get(transaction_set, f"EDI_{transaction_set}"),
            reference_document_number=extracted.get("reference_document_number"),
            tenant_id=tenant_id,
        )
        return fsma_event.model_dump()
    except (ValidationError, ImportError) as exc:
        logger.warning("edi_fsma_validation_failed set=%s error=%s", transaction_set, str(exc))
        return None


# ---------------------------------------------------------------------------
# Unified multi-document-type EDI endpoint
# ---------------------------------------------------------------------------


def _detect_transaction_set(segments: list[list[str]]) -> str | None:
    """Detect the X12 transaction set from parsed segments."""
    st = _first_segment(segments, "ST")
    if st and len(st) > 1:
        ts = st[1].strip()
        if ts in _SUPPORTED_TRANSACTION_SETS:
            return ts
    return None


def _extract_fields_for_set(transaction_set: str, segments: list[list[str]]) -> dict[str, Any]:
    """Dispatch to the correct field extractor based on transaction set."""
    if transaction_set == "856":
        return _extract_856_fields(segments)
    elif transaction_set == "850":
        return _extract_850_fields(segments)
    elif transaction_set == "810":
        return _extract_810_fields(segments)
    elif transaction_set == "861":
        return _extract_861_fields(segments)
    return {}


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
        "edi_sender_id": extracted.get("sender_id"),
        "edi_receiver_id": extracted.get("receiver_id"),
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

    raw_text = raw_bytes.decode("utf-8", errors="ignore")
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

    # Validate against FSMAEvent model
    fsma_validated = _validate_edi_as_fsma_event(
        extracted, transaction_set, traceability_lot_code, sender_tenant_id,
    )
    if fsma_validated:
        extracted["fsma_validation_status"] = "passed"
    else:
        extracted["fsma_validation_status"] = "failed"
        logger.warning(
            "edi_fsma_validation_warning set=%s tlc=%s",
            transaction_set, traceability_lot_code,
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
