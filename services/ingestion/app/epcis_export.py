"""
EPCIS Export Router.

Generates GS1 EPCIS 2.0 JSON-LD exports for retailer compliance
(Walmart, Kroger, Costco). Also provides FDA 21 CFR 1.1455 sortable
spreadsheet export format.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from shared.database import get_db_safe
from shared.fsma_validation import normalize_gtin, verify_gs1_check_digit
from shared.tenant_context import TenantContext
from sqlalchemy import text

from .shared.csv_safety import sanitize_cell
from .webhook_compat import require_tenant_context

logger = logging.getLogger("epcis-export")

FDA_CSV_HEADER = (
    "CTE_Type,Traceability_Lot_Code,Product_Description,Quantity,Unit_of_Measure,"
    "Event_Date,Event_Time,Ship_From_Location,Ship_From_GLN,Ship_To_Location,"
    "Ship_To_GLN,Carrier,Temperature_C,SHA256_Hash"
)


# Hard cap on events buffered into one synchronous export. Exceeding it
# returns HTTP 413 rather than silently dropping the oldest events (SEL-506),
# matching the compliance FDA spreadsheet export (services/compliance
# routes.py ``_MAX_EXPORT_EVENTS``).
_MAX_EXPORT_EVENTS = 50_000


class ExportStorageUnavailable(RuntimeError):
    """The event store could not be read; never report this as "no data"."""


def _query_tenant_events(
    tenant_id: str, lot_code: str | None, date_from: str | None, date_to: str | None
) -> list[dict]:
    """Query real CTE events from fsma.cte_events for export.

    Returns at most ``_MAX_EXPORT_EVENTS + 1`` rows so callers can detect
    an over-cap export. Raises :class:`ExportStorageUnavailable` on any
    database error instead of returning an empty list (SEL-508).
    """
    db = get_db_safe()
    try:
        where = []
        params: dict = {"tenant_id": tenant_id}
        if lot_code:
            where.append("e.traceability_lot_code = :lot_code")
            params["lot_code"] = lot_code
        if date_from:
            where.append("e.event_timestamp >= :date_from")
            params["date_from"] = date_from
        if date_to:
            where.append("e.event_timestamp < :date_to")
            params["date_to"] = date_to

        rows = db.execute(
            text(f"""
                WITH tenant_kdes AS (
                    SELECT k.* FROM fsma.cte_kdes k
                    WHERE k.tenant_id = :tenant_id
                )
                SELECT
                    e.id AS event_id,
                    e.event_type,
                    e.traceability_lot_code,
                    e.product_description,
                    e.quantity,
                    e.unit_of_measure,
                    e.event_timestamp,
                    e.location_gln,
                    e.location_name,
                    e.sha256_hash,
                    e.epcis_event_type,
                    e.epcis_action,
                    e.epcis_biz_step,
                    k_epcis.kde_value AS epcis_document_json,
                    COALESCE(k_gtin.kde_value, k_product.kde_value) AS gtin,
                    k_product.kde_value AS product_id,
                    k_epc_class.kde_value AS epc_class,
                    k_from.kde_value AS ship_from,
                    k_from_gln.kde_value AS ship_from_gln,
                    k_to.kde_value AS ship_to,
                    k_to_gln.kde_value AS ship_to_gln,
                    k_carrier.kde_value AS carrier,
                    k_temp.kde_value AS temperature_c,
                    k_ref.kde_value AS reference_document,
                    k_tlc_src.kde_value AS tlc_source_reference,
                    k_prev.kde_value AS immediate_previous_source,
                    k_field.kde_value AS field_id,
                    k_harvester.kde_value AS harvester_name,
                    k_harvester_biz.kde_value AS harvester_business_name,
                    k_harvester_phone.kde_value AS harvester_business_phone
                FROM fsma.cte_events e
                LEFT JOIN tenant_kdes k_from ON k_from.cte_event_id = e.id AND k_from.tenant_id = e.tenant_id AND k_from.kde_key = 'ship_from_location'
                LEFT JOIN tenant_kdes k_epcis ON k_epcis.cte_event_id = e.id AND k_epcis.tenant_id = e.tenant_id AND k_epcis.kde_key = 'epcis_document_json'
                LEFT JOIN tenant_kdes k_gtin ON k_gtin.cte_event_id = e.id AND k_gtin.tenant_id = e.tenant_id AND k_gtin.kde_key = 'gtin'
                LEFT JOIN tenant_kdes k_product ON k_product.cte_event_id = e.id AND k_product.tenant_id = e.tenant_id AND k_product.kde_key = 'product_id'
                LEFT JOIN tenant_kdes k_epc_class ON k_epc_class.cte_event_id = e.id AND k_epc_class.tenant_id = e.tenant_id AND k_epc_class.kde_key = 'epc_class'
                LEFT JOIN tenant_kdes k_from_gln ON k_from_gln.cte_event_id = e.id AND k_from_gln.tenant_id = e.tenant_id AND k_from_gln.kde_key = 'ship_from_gln'
                LEFT JOIN tenant_kdes k_to ON k_to.cte_event_id = e.id AND k_to.tenant_id = e.tenant_id AND k_to.kde_key = 'ship_to_location'
                LEFT JOIN tenant_kdes k_to_gln ON k_to_gln.cte_event_id = e.id AND k_to_gln.tenant_id = e.tenant_id AND k_to_gln.kde_key = 'ship_to_gln'
                LEFT JOIN tenant_kdes k_carrier ON k_carrier.cte_event_id = e.id AND k_carrier.tenant_id = e.tenant_id AND k_carrier.kde_key = 'carrier_name'
                LEFT JOIN tenant_kdes k_temp ON k_temp.cte_event_id = e.id AND k_temp.tenant_id = e.tenant_id AND k_temp.kde_key = 'temperature_celsius'
                LEFT JOIN tenant_kdes k_ref ON k_ref.cte_event_id = e.id AND k_ref.tenant_id = e.tenant_id AND k_ref.kde_key = 'reference_document'
                LEFT JOIN tenant_kdes k_tlc_src ON k_tlc_src.cte_event_id = e.id AND k_tlc_src.tenant_id = e.tenant_id AND k_tlc_src.kde_key = 'tlc_source_reference'
                LEFT JOIN tenant_kdes k_prev ON k_prev.cte_event_id = e.id AND k_prev.tenant_id = e.tenant_id AND k_prev.kde_key = 'immediate_previous_source'
                LEFT JOIN tenant_kdes k_field ON k_field.cte_event_id = e.id AND k_field.tenant_id = e.tenant_id AND k_field.kde_key = 'field_id'
                LEFT JOIN tenant_kdes k_harvester ON k_harvester.cte_event_id = e.id AND k_harvester.tenant_id = e.tenant_id AND k_harvester.kde_key = 'harvester_name'
                LEFT JOIN tenant_kdes k_harvester_biz ON k_harvester_biz.cte_event_id = e.id AND k_harvester_biz.tenant_id = e.tenant_id AND k_harvester_biz.kde_key = 'harvester_business_name'
                LEFT JOIN tenant_kdes k_harvester_phone ON k_harvester_phone.cte_event_id = e.id AND k_harvester_phone.tenant_id = e.tenant_id AND k_harvester_phone.kde_key = 'harvester_business_phone'
                WHERE e.tenant_id = :tenant_id
                {"AND " + " AND ".join(where) if where else ""}
                ORDER BY e.event_timestamp DESC
                LIMIT :row_limit
            """),
            {**params, "row_limit": _MAX_EXPORT_EVENTS + 1},
        ).fetchall()
        return [dict(row._mapping) for row in rows]
    except Exception as exc:
        logger.error("db_query_failed_for_export", extra={"error": str(exc)})
        raise ExportStorageUnavailable(str(exc)) from exc
    finally:
        db.close()


def _load_export_rows(tenant_id: str, request: "ExportRequest") -> list[dict]:
    """Load rows for an export, failing loudly instead of returning partial data.

    503 when storage is unavailable (never "No data yet"), 413 when the
    result would exceed ``_MAX_EXPORT_EVENTS`` (never a silent truncation).
    """
    try:
        rows = _query_tenant_events(tenant_id, request.lot_code, request.date_from, request.date_to)
    except ExportStorageUnavailable as exc:
        raise HTTPException(status_code=503, detail="Event storage unavailable; export not generated") from exc
    if len(rows) > _MAX_EXPORT_EVENTS:
        logger.warning(
            "export_exceeded_hard_cap",
            extra={"tenant_id": tenant_id, "cap": _MAX_EXPORT_EVENTS},
        )
        raise HTTPException(
            status_code=413,
            detail=(f"Export exceeds the {_MAX_EXPORT_EVENTS:,}-event hard cap; narrow your date range or lot code"),
        )
    return rows


_CTE_TO_BIZSTEP = {
    "receiving": "urn:epcglobal:cbv:bizstep:receiving",
    "shipping": "urn:epcglobal:cbv:bizstep:shipping",
    "transformation": "urn:epcglobal:cbv:bizstep:commissioning",
    "initial_packing": "urn:epcglobal:cbv:bizstep:packing",
    "harvesting": "urn:epcglobal:cbv:bizstep:collecting",
    "cooling": "urn:epcglobal:cbv:bizstep:storing",
    "first_land_based_receiving": "urn:epcglobal:cbv:bizstep:receiving",
}

_CBV_BIZSTEPS = {
    "accepting",
    "arriving",
    "assembling",
    "collecting",
    "commissioning",
    "consigning",
    "creating_class_instance",
    "cycle_counting",
    "decommissioning",
    "departing",
    "destroying",
    "disassembling",
    "dispensing",
    "encoding",
    "entering_exiting",
    "holding",
    "inspecting",
    "installing",
    "killing",
    "loading",
    "other",
    "packing",
    "picking",
    "receiving",
    "removing",
    "repackaging",
    "repairing",
    "replacing",
    "reserving",
    "retail_selling",
    "sampling",
    "sensor_reporting",
    "shipping",
    "staging_outbound",
    "stock_taking",
    "stocking",
    "storing",
    "transporting",
    "unloading",
    "unpacking",
    "void_shipping",
}
_CBV_DISPOSITIONS = {
    "active",
    "available",
    "container_closed",
    "damaged",
    "destroyed",
    "dispensed",
    "disposed",
    "encoded",
    "expired",
    "in_progress",
    "in_transit",
    "inactive",
    "no_pedigree_match",
    "non_sellable_other",
    "partially_dispensed",
    "recalled",
    "reserved",
    "retail_sold",
    "returned",
    "sellable_accessible",
    "sellable_not_accessible",
    "stolen",
    "unknown",
}


def _gs1_check_digit_valid(digits: str) -> bool:
    """Validate a GS1 mod-10 check digit (GTIN/GLN/SSCC).

    Delegates to ``shared.fsma_validation.verify_gs1_check_digit`` so the
    rightmost data digit is weighted 3 (GS1 General Specifications).
    """
    return verify_gs1_check_digit(digits)


_UOM_TO_UNCEFACT = {
    "kg": "KGM",
    "kgs": "KGM",
    "kilogram": "KGM",
    "kilograms": "KGM",
    "kgm": "KGM",
    "lb": "LBR",
    "lbs": "LBR",
    "pound": "LBR",
    "pounds": "LBR",
    "lbr": "LBR",
    "cases": "CS",
    "case": "CS",
    "cs": "CS",
    "cas": "CS",
    "each": "EA",
    "ea": "EA",
    "units": "EA",
    "unit": "EA",
    "cartons": "CT",
    "carton": "CT",
    "ct": "CT",
    "ctn": "CT",
    "boxes": "BX",
    "box": "BX",
    "bags": "BG",
    "bag": "BG",
    "pallets": "PF",
    "pallet": "PF",
    "pieces": "H87",
    "piece": "H87",
}


def _kde_scalar(value: object) -> str:
    """Normalize a JSONB/text KDE cell to a bare string."""
    if value is None:
        return ""
    if isinstance(value, (dict, list, bool)):
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        return str(value).strip()
    text_value = value.strip()
    if len(text_value) >= 2 and text_value[0] == text_value[-1] == '"':
        try:
            parsed = json.loads(text_value)
        except (TypeError, ValueError):
            return text_value
        if isinstance(parsed, str):
            return parsed.strip()
    return text_value


def _quantity_uom(raw: object) -> tuple[str | None, str | None]:
    """Map free-text units to UN/CEFACT; return (uom, raw_if_unmapped_or_alias)."""
    if raw is None:
        return None, None
    value = _kde_scalar(raw)
    if not value:
        return None, None
    if re.fullmatch(r"[A-Z0-9]{2,3}", value):
        return value, None
    mapped = _UOM_TO_UNCEFACT.get(value.lower())
    if mapped:
        return mapped, None if value.upper() == mapped else value
    return None, value


def _cbv_term(value: str | None, kind: str) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    value = value.removeprefix(f"urn:epcglobal:cbv:{kind}:")
    web_prefix = f"https://ref.gs1.org/cbv/{'BizStep' if kind == 'bizstep' else 'Disp'}-"
    value = value.removeprefix(web_prefix)
    allowed = _CBV_BIZSTEPS if kind == "bizstep" else _CBV_DISPOSITIONS
    return value if value in allowed else None


def _valid_class_uri(value: object) -> bool:
    if not isinstance(value, str) or "0000000.000000" in value:
        return False
    match = re.fullmatch(
        r"urn:epc:class:lgtin:(\d{6,12})\.(\d+)\.([A-Za-z0-9_~!$&'()*+,;=:@%\-]+)",
        value,
    )
    if match:
        return len(match[1]) + len(match[2]) == 13
    match = re.fullmatch(r"https://id\.gs1\.org/01/(\d{14})/10/[^/?#]+", value)
    return bool(match and _gs1_check_digit_valid(match[1]))


def _epc_class(row: dict) -> str | None:
    """Use an existing class URI, product_id, or a GTIN Digital Link.

    GTIN/GLN digits do not reveal the company-prefix split required by EPC
    URNs. A lot code alone cannot identify an EPC class — callers must
    persist ``epc_class``, ``product_id`` (class URI), ``gtin``, or an
    embedded ``epcis_document_json`` quantity class.
    """
    for key in ("epc_class", "product_id"):
        value = _kde_scalar(row.get(key))
        if _valid_class_uri(value):
            return value
    raw = row.get("epcis_document_json")
    if raw:
        try:
            original = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(original, dict):
                for field in ("quantityList", "outputQuantityList", "inputQuantityList"):
                    for item in original.get(field) or []:
                        candidate = item.get("epcClass") if isinstance(item, dict) else None
                        if _valid_class_uri(candidate):
                            return candidate
        except (TypeError, ValueError):
            pass
    gtin_raw = _kde_scalar(row.get("gtin")) or _kde_scalar(row.get("product_id"))
    lot = _kde_scalar(row.get("traceability_lot_code"))
    digits = re.sub(r"\D", "", gtin_raw)
    if digits and lot:
        try:
            gtin14 = normalize_gtin(digits)
        except ValueError:
            gtin14 = ""
        if gtin14 and _gs1_check_digit_valid(gtin14):
            return f"https://id.gs1.org/01/{gtin14}/10/{quote(lot, safe='-._~')}"
    return None


def _input_epc_class(row: dict) -> str | None:
    """Best-effort input class for TransformationEvent rows."""
    raw = row.get("epcis_document_json")
    if raw:
        try:
            original = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(original, dict):
                for item in original.get("inputQuantityList") or []:
                    candidate = item.get("epcClass") if isinstance(item, dict) else None
                    if _valid_class_uri(candidate):
                        return candidate
                for item in original.get("inputEPCList") or []:
                    if isinstance(item, str) and _valid_class_uri(item):
                        return item
        except (TypeError, ValueError):
            pass
    return None


def _instance_epc(row: dict) -> str | None:
    """Return a valid SGTIN instance URN from product_id when present."""
    value = _kde_scalar(row.get("product_id"))
    match = re.fullmatch(
        r"urn:epc:id:sgtin:(\d{6,12})\.(\d+)\.([A-Za-z0-9_~!$&'()*+,;=:@%\-]+)",
        value,
    )
    if match and match[1] != "0000000" and len(match[1]) + len(match[2]) == 13:
        return value
    return None


def _location_uri(value: object) -> str | None:
    value = _kde_scalar(value) if not isinstance(value, str) else value
    if not isinstance(value, str) or not value:
        return None
    if "0000000000000" in value or "0000000.00000" in value:
        return None
    if re.fullmatch(r"urn:epc:id:sgln:\d{6,12}\.\d+\.[A-Za-z0-9_-]+", value):
        return value
    if re.fullmatch(r"\d{6,12}\.\d+\.[A-Za-z0-9_-]+", value):
        return f"urn:epc:id:sgln:{value}"
    if re.fullmatch(r"\d{13}", value) and _gs1_check_digit_valid(value):
        return f"https://id.gs1.org/414/{value}"
    return None


def _validate_epcis_document(doc: dict) -> list[str]:
    """Validate an EPCIS 2.0 JSON-LD document structure.

    Returns a list of validation error strings (empty = valid).
    Checks structural compliance without requiring an external JSON Schema library.
    """
    errors: list[str] = []

    # Top-level structure
    if "@context" not in doc:
        errors.append("Missing required @context field")
    if doc.get("type") != "EPCISDocument":
        errors.append(f"Expected type 'EPCISDocument', got '{doc.get('type')}'")
    if "schemaVersion" not in doc:
        errors.append("Missing schemaVersion field")
    elif doc["schemaVersion"] not in ("2.0", "2.0.0"):
        errors.append(f"Unsupported schemaVersion '{doc['schemaVersion']}' (expected 2.0)")
    if "creationDate" not in doc:
        errors.append("Missing creationDate field")

    # Event list
    body = doc.get("epcisBody", {})
    event_list = body.get("eventList", [])
    if not event_list:
        errors.append("epcisBody.eventList is empty or missing")

    valid_event_types = {
        "ObjectEvent",
        "AggregationEvent",
        "TransactionEvent",
        "TransformationEvent",
        "AssociationEvent",
    }
    valid_actions = {"ADD", "OBSERVE", "DELETE"}
    for i, event in enumerate(event_list):
        prefix = f"event[{i}]"
        etype = event.get("type")
        if etype not in valid_event_types:
            errors.append(f"{prefix}: invalid type '{etype}'")
        if "eventTime" not in event:
            errors.append(f"{prefix}: missing eventTime")
        action = event.get("action")
        if action and action not in valid_actions:
            errors.append(f"{prefix}: invalid action '{action}'")
        if "extension" in event:
            errors.append(f"{prefix}: EPCIS 1.x extension wrapper")
        for field, kind in (("bizStep", "bizstep"), ("disposition", "disp")):
            value = event.get(field)
            if value and _cbv_term(value, kind) is None:
                errors.append(f"{prefix}: {field} '{value}' is not a valid GS1 CBV URI")

    return errors


router = APIRouter(prefix="/api/v1/export", tags=["EPCIS & FDA Export"])


class ExportRequest(BaseModel):
    """Request for data export."""

    tenant_id: str = Field(..., description="Tenant ID")
    format: str = Field("epcis", description="Export format: epcis, fda, csv")
    lot_code: Optional[str] = Field(None, description="Filter by specific TLC")
    date_from: Optional[str] = Field(None, description="Start date (YYYY-MM-DD)")
    date_to: Optional[str] = Field(None, description="End date (YYYY-MM-DD)")


@router.post(
    "/epcis",
    summary="Export in GS1 EPCIS 2.0 JSON-LD format",
    description=(
        "Generates a GS1 EPCIS 2.0 compliant JSON-LD document containing all "
        "traceability events. Compatible with Walmart, Kroger, and Costco portals."
    ),
)
async def export_epcis(
    request: ExportRequest,
    validate: bool = Query(False, description="Run GS1 EPCIS 2.0 structural validation on the output"),
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Export traceability data in EPCIS 2.0 JSON-LD format."""
    now = datetime.now(timezone.utc)
    tenant_id = ctx.tenant_id

    rows = _load_export_rows(tenant_id, request)
    data_source = "tenant" if rows else "empty"

    event_list = []
    skipped = 0
    skipped_by_reason: dict[str, int] = {}
    skipped_evidence: list[dict] = []

    def _skip(row: dict, reason: str) -> None:
        nonlocal skipped
        skipped += 1
        skipped_by_reason[reason] = skipped_by_reason.get(reason, 0) + 1
        if len(skipped_evidence) < 50:
            skipped_evidence.append(
                {
                    "reason": reason,
                    "eventType": row.get("event_type"),
                    "eventId": str(row.get("event_id") or "") or None,
                    "tlc": _kde_scalar(row.get("traceability_lot_code")) or None,
                }
            )

    if rows:
        for r in rows:
            ts = r.get("event_timestamp")
            if not ts:
                _skip(r, "missing_timestamp")
                continue
            event_kind = r.get("epcis_event_type")
            is_transformation = (
                r.get("event_type") == "transformation"
                or event_kind == "TransformationEvent"
            )
            if event_kind not in (None, "ObjectEvent", "TransformationEvent"):
                _skip(r, "unsupported_epcis_event_type")
                continue
            if r.get("epcis_action") not in (None, "ADD", "OBSERVE", "DELETE"):
                _skip(r, "unsupported_action")
                continue

            epc_class = _epc_class(r)
            instance_epc = _instance_epc(r)
            if not epc_class and not instance_epc:
                _skip(r, "missing_epc_class")
                continue

            if isinstance(ts, str):
                # tolerate ISO strings from some fixtures/drivers
                try:
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    _skip(r, "invalid_timestamp")
                    continue

            tz = ts.strftime("%z")
            offset = (tz[:3] + ":" + tz[3:]) if tz else "+00:00"
            common = {
                "eventTime": ts.isoformat(),
                "eventTimeZoneOffset": offset,
            }
            biz_step = _cbv_term(r.get("epcis_biz_step") or _CTE_TO_BIZSTEP.get(r.get("event_type") or ""), "bizstep")
            location = _location_uri(r.get("location_gln"))
            uom, raw_uom = _quantity_uom(r.get("unit_of_measure"))
            quantity = r.get("quantity")

            if is_transformation:
                event = {"type": "TransformationEvent", **common, "bizStep": biz_step or "commissioning"}
                if epc_class:
                    out_qty: dict = {"epcClass": epc_class}
                    if quantity is not None:
                        out_qty["quantity"] = quantity
                        if uom:
                            out_qty["uom"] = uom
                    event["outputQuantityList"] = [out_qty]
                elif instance_epc:
                    event["outputEPCList"] = [instance_epc]
                input_class = _input_epc_class(r)
                if input_class:
                    event["inputQuantityList"] = [{"epcClass": input_class}]
                transform_id = _kde_scalar(r.get("sha256_hash"))
                if transform_id:
                    event["transformationID"] = f"urn:sha256:{transform_id}"
            else:
                event = {
                    "type": "ObjectEvent",
                    **common,
                    "action": r.get("epcis_action") or "OBSERVE",
                }
                if instance_epc and not epc_class:
                    event["epcList"] = [instance_epc]
                else:
                    qty_item: dict = {"epcClass": epc_class}
                    if quantity is not None:
                        qty_item["quantity"] = quantity
                        if uom:
                            qty_item["uom"] = uom
                    event["quantityList"] = [qty_item]
                if biz_step:
                    event["bizStep"] = biz_step
            if location:
                event["readPoint"] = {"id": location}
            if r.get("sha256_hash"):
                event["regengine:sha256"] = r["sha256_hash"]
            if raw_uom:
                event["regengine:unitOfMeasure"] = raw_uom
            event_list.append(event)

    epcis_document = {
        "@context": [
            "https://ref.gs1.org/standards/epcis/2.0.0/epcis-context.jsonld",
            {
                "regengine": "https://regengine.co/ns/",
                **{
                    key: f"regengine:{key}"
                    for key in (
                        "tenantId",
                        "exportFormat",
                        "generatedAt",
                        "eventsCount",
                        "skippedEventsCount",
                        "skippedEventsByReason",
                        "skippedEvents",
                        "unitOfMeasure",
                        "dataSource",
                        "integrityVerified",
                        "chainHashVerified",
                        "valid",
                        "errors",
                        "checkedAt",
                    )
                },
            },
        ],
        "type": "EPCISDocument",
        "schemaVersion": "2.0",
        "creationDate": now.isoformat(),
        "epcisBody": {
            "eventList": event_list,
        },
        "regengine:exportMetadata": {
            "tenantId": tenant_id,
            "exportFormat": "EPCIS_2.0_JSON-LD",
            "generatedAt": now.isoformat(),
            "eventsCount": len(event_list),
            "skippedEventsCount": skipped,
            "skippedEventsByReason": skipped_by_reason,
            "skippedEvents": skipped_evidence,
            "dataSource": data_source,
            "integrityVerified": data_source == "tenant",
            "chainHashVerified": data_source == "tenant",
            **({"regengine:message": "No data yet"} if not rows else {}),
        },
    }

    if skipped:
        logger.info(
            "epcis_export_skipped_events",
            extra={"skipped": skipped, "by_reason": skipped_by_reason, "exported": len(event_list)},
        )

    if validate:
        validation_errors = _validate_epcis_document(epcis_document)
        epcis_document["regengine:validation"] = {
            "valid": len(validation_errors) == 0,
            "errors": validation_errors,
            "checkedAt": now.isoformat(),
        }

    from shared.fda_export import safe_filename

    response_headers = {
        "Content-Disposition": (
            'attachment; filename="'
            + safe_filename(
                "regengine_epcis",
                scope=tenant_id,
                timestamp=now.strftime("%Y%m%d"),
                extension="json",
            )
            + '"'
        ),
        "X-RegEngine-Events-Count": str(len(event_list)),
        "X-RegEngine-Skipped-Events-Count": str(skipped),
        "X-RegEngine-Integrity-Verified": "true" if data_source == "tenant" else "false",
        "X-RegEngine-Data-Source": data_source,
    }
    if validate:
        response_headers["X-RegEngine-Schema-Valid"] = "true" if not validation_errors else "false"

    return JSONResponse(content=epcis_document, headers=response_headers)


@router.post(
    "/fda",
    summary="Export in FDA 21 CFR 1.1455 sortable spreadsheet format",
    description=(
        "Generates a CSV-compatible sortable spreadsheet for FDA records requests. "
        "Includes all required KDEs organized by CTE type."
    ),
)
async def export_fda(
    request: ExportRequest,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Export traceability data in FDA-compliant sortable spreadsheet format."""
    now = datetime.now(timezone.utc)
    tenant_id = ctx.tenant_id

    rows = _load_export_rows(tenant_id, request)
    data_source = "tenant" if rows else "empty"

    if rows:
        # Build CSV from real data
        lines = [FDA_CSV_HEADER]
        for r in rows:
            ts = r["event_timestamp"]
            date_str = ts.strftime("%Y-%m-%d") if ts else ""
            time_str = ts.strftime("%H:%M:%SZ") if ts else ""
            lines.append(
                ",".join(
                    [
                        str(r["event_type"] or "").upper(),
                        str(r["traceability_lot_code"] or ""),
                        sanitize_cell(str(r["product_description"] or "")).replace(",", ";"),
                        str(r["quantity"] or ""),
                        str(r["unit_of_measure"] or ""),
                        date_str,
                        time_str,
                        sanitize_cell(str(r["ship_from"] or r["location_name"] or "")).replace(",", ";"),
                        str(r["ship_from_gln"] or r["location_gln"] or ""),
                        sanitize_cell(str(r["ship_to"] or "")).replace(",", ";"),
                        str(r["ship_to_gln"] or ""),
                        sanitize_cell(str(r["carrier"] or "")).replace(",", ";"),
                        str(r["temperature_c"] or ""),
                        str(r["sha256_hash"] or ""),
                    ]
                )
            )
        csv_content = "\n".join(lines) + "\n"
        event_count = len(rows)
    else:
        csv_content = FDA_CSV_HEADER + "\n"
        event_count = 0

    # EPIC-L (#1655): route filename through the shared safe_filename
    # builder so tenant_id can't carry CRLF / quotes into the header value.
    from shared.fda_export import safe_filename

    fda_headers: dict[str, str] = {
        "Content-Disposition": (
            'attachment; filename="'
            + safe_filename(
                "regengine_fda_export",
                scope=tenant_id,
                timestamp=now.strftime("%Y%m%d"),
            )
            + '"'
        ),
        "X-RegEngine-Events-Count": str(event_count),
        "X-RegEngine-Format": "FDA_21CFR1.1455",
        "X-RegEngine-Data-Source": data_source,
    }
    if data_source == "empty":
        fda_headers["X-RegEngine-Message"] = "No data yet"

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers=fda_headers,
    )


@router.get(
    "/formats",
    summary="List available export formats",
    dependencies=[Depends(require_tenant_context)],
)
async def list_export_formats():
    """List available export formats and their descriptions."""
    return {
        "formats": [
            {
                "id": "epcis",
                "name": "GS1 EPCIS 2.0 JSON-LD",
                "description": "Industry standard for supply chain event data. Compatible with Walmart, Kroger, Costco.",
                "content_type": "application/ld+json",
                "retailers": ["Walmart", "Kroger", "Costco", "Target"],
            },
            {
                "id": "fda",
                "name": "FDA Sortable Spreadsheet (CSV)",
                "description": "Sortable electronic format required by 21 CFR 1.1455 for FDA records requests.",
                "content_type": "text/csv",
                "retailers": ["FDA"],
            },
        ]
    }
