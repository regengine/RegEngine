"""EDI inbound ingestion router.

Accepts partner-authenticated X12 856 (ASN) documents and normalizes them
into FSMA shipping CTE events through the existing webhook ingestion pipeline.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.format_extractors import is_edi_content
from app.webhook_compat import _verify_api_key, ingest_events
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


class EDIIngestResponse(BaseModel):
    """Response for EDI 856 ingestion requests."""

    status: str = "accepted"
    parser_name: str = "edi_parser"
    document_type: str = "X12_856"
    sender_tenant_id: str
    partner_id: Optional[str] = None
    traceability_lot_code: str
    extracted: dict[str, Any] = Field(default_factory=dict)
    ingestion_result: IngestResponse


def _get_db_session():
    from shared.database import SessionLocal

    return SessionLocal()


def _resolve_tenant_id(
    explicit_tenant_id: Optional[str],
    x_tenant_id: Optional[str],
    x_regengine_api_key: Optional[str],
) -> Optional[str]:
    if explicit_tenant_id:
        return explicit_tenant_id
    if x_tenant_id:
        return x_tenant_id
    if not x_regengine_api_key:
        return None

    db = _get_db_session()
    try:
        row = db.execute(
            text(
                """
                SELECT tenant_id
                FROM api_keys
                WHERE key_hash = encode(sha256(:raw::bytea), 'hex')
                LIMIT 1
                """
            ),
            {"raw": x_regengine_api_key},
        ).fetchone()
        if row and row[0]:
            return str(row[0])
    except Exception as exc:
        logger.warning("edi_tenant_lookup_failed error=%s", str(exc))
    finally:
        db.close()

    return None


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
    _: None = Depends(_verify_api_key),
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

    kdes: dict[str, Any] = {
        "ship_date": ship_date,
        "ship_from_location": ship_from_name,
        "ship_to_location": ship_to_name,
        "ship_from_gln": ship_from_gln_raw,
        "ship_to_gln": ship_to_gln_raw,
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
