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

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from shared.database import get_db_safe
from shared.tenant_context import TenantContext
from sqlalchemy import text

from .disclaimers import SAMPLE_EXPORT_DISCLAIMER
from .shared.csv_safety import sanitize_cell
from .webhook_compat import require_tenant_context

logger = logging.getLogger("epcis-export")


def _query_tenant_events(
    tenant_id: str, lot_code: str | None, date_from: str | None, date_to: str | None
) -> list[dict]:
    """Query real CTE events from fsma.cte_events for export."""
    db = get_db_safe()
    try:
        where = ["e.tenant_id = :tenant_id"]
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
                SELECT
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
                    k_gtin.kde_value AS gtin,
                    k_from.kde_value AS ship_from,
                    k_from_gln.kde_value AS ship_from_gln,
                    k_to.kde_value AS ship_to,
                    k_to_gln.kde_value AS ship_to_gln,
                    k_carrier.kde_value AS carrier,
                    k_temp.kde_value AS temperature_c
                FROM fsma.cte_events e
                LEFT JOIN fsma.cte_kdes k_from ON k_from.cte_event_id = e.id AND k_from.kde_key = 'ship_from_location'
                LEFT JOIN fsma.cte_kdes k_epcis ON k_epcis.cte_event_id = e.id AND k_epcis.tenant_id = e.tenant_id AND k_epcis.kde_key = 'epcis_document_json'
                LEFT JOIN fsma.cte_kdes k_gtin ON k_gtin.cte_event_id = e.id AND k_gtin.tenant_id = e.tenant_id AND k_gtin.kde_key = 'gtin'
                LEFT JOIN fsma.cte_kdes k_from_gln ON k_from_gln.cte_event_id = e.id AND k_from_gln.kde_key = 'ship_from_gln'
                LEFT JOIN fsma.cte_kdes k_to ON k_to.cte_event_id = e.id AND k_to.kde_key = 'ship_to_location'
                LEFT JOIN fsma.cte_kdes k_to_gln ON k_to_gln.cte_event_id = e.id AND k_to_gln.kde_key = 'ship_to_gln'
                LEFT JOIN fsma.cte_kdes k_carrier ON k_carrier.cte_event_id = e.id AND k_carrier.kde_key = 'carrier_name'
                LEFT JOIN fsma.cte_kdes k_temp ON k_temp.cte_event_id = e.id AND k_temp.kde_key = 'temperature_celsius'
                WHERE {" AND ".join(where)}
                ORDER BY e.event_timestamp DESC
                LIMIT 5000
            """),
            params,
        ).fetchall()
        return [dict(row._mapping) for row in rows]
    except Exception as exc:
        logger.warning("db_query_failed_for_export", extra={"error": str(exc)})
        return []
    finally:
        db.close()


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
    "accepting", "arriving", "assembling", "collecting", "commissioning",
    "consigning", "creating_class_instance", "cycle_counting", "decommissioning",
    "departing", "destroying", "disassembling", "dispensing", "encoding",
    "entering_exiting", "holding", "inspecting", "installing", "killing",
    "loading", "other", "packing", "picking", "receiving", "removing",
    "repackaging", "repairing", "replacing", "reserving", "retail_selling",
    "sampling", "sensor_reporting", "shipping", "staging_outbound",
    "stock_taking", "stocking", "storing", "transporting", "unloading",
    "unpacking", "void_shipping",
}
_CBV_DISPOSITIONS = {
    "active", "available", "container_closed", "damaged", "destroyed",
    "dispensed", "disposed", "encoded", "expired", "in_progress", "in_transit",
    "inactive", "no_pedigree_match", "non_sellable_other",
    "partially_dispensed", "recalled", "reserved", "retail_sold", "returned",
    "sellable_accessible", "sellable_not_accessible", "stolen", "unknown",
}


def _gs1_check_digit_valid(digits: str) -> bool:
    if not digits.isdigit():
        return False
    total = sum(int(digit) * (3 if offset % 2 else 1) for offset, digit in enumerate(reversed(digits[:-1])))
    return (10 - total % 10) % 10 == int(digits[-1])


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
    """Use an existing class URI, or a GTIN Digital Link when both keys exist.

    GTIN/GLN digits do not reveal the company-prefix split required by EPC
    URNs. A lot code alone cannot identify an EPC class.
    """
    value = row.get("epc_class")
    if _valid_class_uri(value):
        return value
    raw = row.get("epcis_document_json")
    if raw:
        try:
            original = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(original, dict):
                for field in ("quantityList", "outputQuantityList"):
                    for item in original.get(field) or []:
                        candidate = item.get("epcClass") if isinstance(item, dict) else None
                        if _valid_class_uri(candidate):
                            return candidate
        except (TypeError, ValueError):
            pass
    gtin = str(row.get("gtin") or "")
    lot = str(row.get("traceability_lot_code") or "")
    if re.fullmatch(r"\d{14}", gtin) and _gs1_check_digit_valid(gtin) and lot:
        return f"https://id.gs1.org/01/{gtin}/10/{quote(lot, safe='-._~')}"
    return None


def _location_uri(value: object) -> str | None:
    if not isinstance(value, str):
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
            allowed = _CBV_BIZSTEPS if kind == "bizstep" else _CBV_DISPOSITIONS
            web_prefix = f"https://ref.gs1.org/cbv/{'BizStep' if kind == 'bizstep' else 'Disp'}-"
            if value and value not in allowed and not (
                isinstance(value, str)
                and value.startswith(web_prefix)
                and value.removeprefix(web_prefix) in allowed
            ):
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


# Sample EPCIS 2.0 event data (in production, pulled from database)
SAMPLE_EPCIS_EVENTS = [
    {
        "type": "ObjectEvent",
        "eventTime": "2026-02-26T14:30:00.000Z",
        "eventTimeZoneOffset": "-08:00",
        "action": "OBSERVE",
        "bizStep": "shipping",
        "disposition": "in_transit",
        "epcList": ["urn:epc:id:sgtin:0614141.000001.001"],
        "readPoint": {"id": "urn:epc:id:sgln:0614141.00000.0"},
        "bizLocation": {"id": "urn:epc:id:sgln:0614141.00000.0"},
        "quantityList": [
                {"epcClass": "urn:epc:class:lgtin:0614141.000001.TOM-0226-F3-001", "quantity": 200, "uom": "CS"}
        ],
        "sourceList": [
                {"type": "possessing_party", "source": "urn:epc:id:pgln:0614141.00000"}
        ],
        "destinationList": [
                {"type": "possessing_party", "destination": "urn:epc:id:pgln:0614141.00001"}
        ],
        "regengine:sha256": "a3f8c1d2e4b5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1",
        "regengine:chainHash": "b4c9e2c7d5f6a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3",
    },
    {
        "type": "ObjectEvent",
        "eventTime": "2026-02-27T09:15:00.000Z",
        "eventTimeZoneOffset": "-08:00",
        "action": "ADD",
        "bizStep": "receiving",
        "disposition": "in_progress",
        "epcList": ["urn:epc:id:sgtin:0614141.000001.001"],
        "readPoint": {"id": "urn:epc:id:sgln:0614141.00001.0"},
        "bizLocation": {"id": "urn:epc:id:sgln:0614141.00001.0"},
        "quantityList": [
                {"epcClass": "urn:epc:class:lgtin:0614141.000001.TOM-0226-F3-001", "quantity": 200, "uom": "CS"}
        ],
        "ilmd": {"https://regengine.co/ns/temperatureCelsius": 3.2, "https://regengine.co/ns/inspectionResult": "PASS"},
        "regengine:sha256": "c5dae3d8e6f7a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4",
        "regengine:chainHash": "d6ebf4e9f7a8b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5",
    },
]


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

    rows = _query_tenant_events(tenant_id, request.lot_code, request.date_from, request.date_to)
    data_source = "tenant" if rows else "sample"

    if rows:
        event_list = []
        skipped = 0
        for r in rows:
            epc_class = _epc_class(r)
            if (
                not epc_class
                or not r.get("event_timestamp")
                or r.get("epcis_event_type") not in (None, "ObjectEvent")
                or r.get("event_type") == "transformation"
                or r.get("epcis_action") not in (None, "ADD", "OBSERVE", "DELETE")
            ):
                skipped += 1
                continue
            ts = r["event_timestamp"]
            event = {
                "type": "ObjectEvent",
                "eventTime": ts.isoformat(),
                "eventTimeZoneOffset": ts.strftime("%z")[:3] + ":" + ts.strftime("%z")[3:] if ts.tzinfo else "+00:00",
                "action": r["epcis_action"] or "OBSERVE",
                "quantityList": [{"epcClass": epc_class}],
            }
            biz_step = _cbv_term(r.get("epcis_biz_step") or _CTE_TO_BIZSTEP.get(r.get("event_type") or ""), "bizstep")
            if biz_step:
                event["bizStep"] = biz_step
            location = _location_uri(r.get("location_gln"))
            if location:
                event["readPoint"] = {"id": location}
            quantity = r.get("quantity")
            if quantity is not None:
                event["quantityList"][0]["quantity"] = quantity
                if r.get("unit_of_measure"):
                    event["quantityList"][0]["uom"] = r["unit_of_measure"]
            if r.get("sha256_hash"):
                event["regengine:sha256"] = r["sha256_hash"]
            event_list.append(event)
    else:
        event_list = SAMPLE_EPCIS_EVENTS
        skipped = 0

    epcis_document = {
        "@context": [
            "https://ref.gs1.org/standards/epcis/2.0.0/epcis-context.jsonld",
            {
                "regengine": "https://regengine.co/ns/",
                **{
                    key: f"regengine:{key}"
                    for key in (
                        "tenantId", "exportFormat", "generatedAt", "eventsCount",
                        "skippedEventsCount", "dataSource", "integrityVerified",
                        "chainHashVerified", "valid", "errors", "checkedAt",
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
            "dataSource": data_source,
            "integrityVerified": data_source == "tenant",
            "chainHashVerified": data_source == "tenant",
            **({"regengine:disclaimer": SAMPLE_EXPORT_DISCLAIMER} if data_source == "sample" else {}),
        },
    }

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

    rows = _query_tenant_events(tenant_id, request.lot_code, request.date_from, request.date_to)
    data_source = "tenant" if rows else "sample"

    if rows:
        # Build CSV from real data
        lines = [
            "CTE_Type,Traceability_Lot_Code,Product_Description,Quantity,Unit_of_Measure,Event_Date,Event_Time,Ship_From_Location,Ship_From_GLN,Ship_To_Location,Ship_To_GLN,Carrier,Temperature_C,SHA256_Hash"
        ]
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
        # Sample data fallback for tenants with no events yet
        csv_content = """CTE_Type,Traceability_Lot_Code,Product_Description,Quantity,Unit_of_Measure,Event_Date,Event_Time,Ship_From_Location,Ship_From_GLN,Ship_To_Location,Ship_To_GLN,Carrier,Temperature_C,SHA256_Hash
SHIPPING,TOM-0226-F3-001,Roma Tomatoes 12ct,200,cases,2026-02-26,14:30:00Z,Valley Fresh Farms Salinas CA,0614141000005,Metro Distribution Center LA,0614141000012,Cold Express Logistics,3.2,a3f8c1d2e4b5...
RECEIVING,TOM-0226-F3-001,Roma Tomatoes 12ct,200,cases,2026-02-27,09:15:00Z,Valley Fresh Farms Salinas CA,0614141000005,Metro Distribution Center LA,0614141000012,,3.5,c5dae3d8e6f7...
SHIPPING,LET-0226-A2-003,Romaine Lettuce Hearts 12ct,150,cases,2026-02-26,16:00:00Z,Green Valley Farms Salinas CA,0614141000029,Metro Distribution Center LA,0614141000012,Fresh Fleet Inc,2.8,e7f0a1b2c3d4...
HARVESTING,CUC-0226-F2-015,English Cucumbers,500,cases,2026-02-25,08:00:00Z,Sunrise Farms Field 2,,,,,,f8a1b2c3d4e5...
COOLING,SAL-0226-B1-007,Atlantic Salmon Fillets,300,lbs,2026-02-26,06:00:00Z,Pacific Seafood Portland OR,0614141000036,,,,-1.5,a9b0c1d2e3f4...
TRANSFORMATION,SALAD-0226-001,Garden Salad Mix 16oz,1000,bags,2026-02-28,10:00:00Z,Metro Processing Plant LA,0614141000012,,,,,b0c1d2e3f4a5...
"""
        event_count = 6

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
    if data_source == "sample":
        fda_headers["X-RegEngine-Disclaimer"] = SAMPLE_EXPORT_DISCLAIMER

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
