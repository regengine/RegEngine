"""
EPCIS Export Router.

Generates GS1 EPCIS 2.0 JSON-LD exports for retailer compliance
(Walmart, Kroger, Costco). Also provides FDA 21 CFR 1.1455 sortable
spreadsheet export format.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from shared.database import get_db_safe
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
                    k_from.kde_value AS ship_from,
                    k_from_gln.kde_value AS ship_from_gln,
                    k_to.kde_value AS ship_to,
                    k_to_gln.kde_value AS ship_to_gln,
                    k_carrier.kde_value AS carrier,
                    k_temp.kde_value AS temperature_c
                FROM fsma.cte_events e
                LEFT JOIN fsma.cte_kdes k_from ON k_from.cte_event_id = e.id AND k_from.kde_key = 'ship_from_location'
                LEFT JOIN fsma.cte_kdes k_from_gln ON k_from_gln.cte_event_id = e.id AND k_from_gln.kde_key = 'ship_from_gln'
                LEFT JOIN fsma.cte_kdes k_to ON k_to.cte_event_id = e.id AND k_to.kde_key = 'ship_to_location'
                LEFT JOIN fsma.cte_kdes k_to_gln ON k_to_gln.cte_event_id = e.id AND k_to_gln.kde_key = 'ship_to_gln'
                LEFT JOIN fsma.cte_kdes k_carrier ON k_carrier.cte_event_id = e.id AND k_carrier.kde_key = 'carrier_name'
                LEFT JOIN fsma.cte_kdes k_temp ON k_temp.cte_event_id = e.id AND k_temp.kde_key = 'temperature_celsius'
                WHERE {" AND ".join(where)}
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
    "transformation": "urn:epcglobal:cbv:bizstep:transforming",
    "initial_packing": "urn:epcglobal:cbv:bizstep:packing",
    "harvesting": "urn:epcglobal:cbv:bizstep:harvesting",
    "cooling": "urn:epcglobal:cbv:bizstep:storing",
    "first_land_based_receiving": "urn:epcglobal:cbv:bizstep:landing",
}


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
    bizstep_prefix = "urn:epcglobal:cbv:bizstep:"

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
        biz_step = event.get("bizStep", "")
        if biz_step and not biz_step.startswith(bizstep_prefix):
            errors.append(f"{prefix}: bizStep '{biz_step}' is not a valid GS1 CBV URI")

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
        "traceability events. Compatible with Walmart, Kroger, and Costco portals. "
        "Stored event hashes are included without cryptographic verification."
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
    if rows:
        for r in rows:
            ts = r["event_timestamp"]
            event = {
                "type": r["epcis_event_type"] or "ObjectEvent",
                "eventTime": ts.isoformat() if ts else now.isoformat(),
                "eventTimeZoneOffset": "-08:00",
                "action": r["epcis_action"] or "OBSERVE",
                "bizStep": r["epcis_biz_step"]
                or _CTE_TO_BIZSTEP.get(r["event_type"] or "", "urn:epcglobal:cbv:bizstep:observing"),
                "readPoint": {"id": f"urn:epc:id:sgln:{r['location_gln'] or '0000000000000'}.0"},
                "extension": {
                    "quantityList": [
                        {
                            "epcClass": f"urn:epc:class:lgtin:0000000.000000.{r['traceability_lot_code'] or 'UNKNOWN'}",
                            "quantity": r["quantity"] or 0,
                            "uom": r["unit_of_measure"] or "EA",
                        }
                    ],
                },
                "regengine:sha256": r["sha256_hash"] or "",
            }
            event_list.append(event)
    epcis_document = {
        "@context": [
            "https://ref.gs1.org/standards/epcis/2.0.0/epcis-context.jsonld",
            {"regengine": "https://regengine.co/ns/"},
        ],
        "id": f"urn:uuid:regengine-export-{tenant_id}-{now.strftime('%Y%m%d')}",
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
            "dataSource": data_source,
            # Loading stored hashes does not verify event content or chain integrity.
            "integrityVerified": False,
            "chainHashVerified": False,
            **({"regengine:message": "No data yet"} if data_source == "empty" else {}),
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
        "X-RegEngine-Integrity-Verified": "false",
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
