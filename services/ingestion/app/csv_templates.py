"""
CSV Template Generator & Ingest Router.

Provides:
- GET /api/v1/templates/{cte_type} — Download a CSV template with correct headers
- POST /api/v1/ingest/csv — Upload a filled CSV, validate, and ingest
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.webhook_models import (
    IngestEvent,
    IngestResponse,
    WebhookCTEType,
    WebhookPayload,
)
from app.webhook_compat import _verify_api_key, ingest_events

logger = logging.getLogger("csv-templates")

router = APIRouter(prefix="/api/v1", tags=["CSV Templates & Import"])

# Column definitions per CTE type — each is a tuple of (column_name, example_value, description)
CTE_COLUMNS: dict[str, list[tuple[str, str, str]]] = {
    "harvesting": [
        ("traceability_lot_code", "TOM-0226-F3-001", "Unique lot code for this harvest"),
        ("product_description", "Roma Tomatoes", "Product name"),
        ("quantity", "500", "Numeric quantity"),
        ("unit_of_measure", "cases", "Unit: cases, lbs, kg, pallets"),
        ("harvest_date", "2026-02-26", "Date of harvest (YYYY-MM-DD)"),
        ("location_name", "Valley Fresh Farms, Salinas CA", "Farm or field name"),
        ("location_gln", "0614141000005", "GS1 GLN (optional, 13 digits)"),
        ("field_id", "FIELD-A7", "Field or growing area identifier"),
        ("harvester_name", "Valley Fresh Farms LLC", "Business name of harvester"),
    ],
    "cooling": [
        ("traceability_lot_code", "TOM-0226-F3-001", "Lot code from harvest"),
        ("product_description", "Roma Tomatoes", "Product name"),
        ("quantity", "500", "Numeric quantity"),
        ("unit_of_measure", "cases", "Unit"),
        ("cooling_date", "2026-02-26", "Date of cooling (YYYY-MM-DD)"),
        ("location_name", "Valley Fresh Cooler #2", "Cooling facility name"),
        ("location_gln", "0614141000005", "GS1 GLN (optional)"),
        ("temperature_celsius", "2.1", "Temperature at cooling (optional but recommended)"),
    ],
    "initial_packing": [
        ("traceability_lot_code", "TOM-0226-F3-001", "New lot code assigned at packing"),
        ("product_description", "Roma Tomatoes 12ct Box", "Packed product description"),
        ("quantity", "200", "Quantity of packed units"),
        ("unit_of_measure", "cases", "Unit"),
        ("packing_date", "2026-02-26", "Date of packing (YYYY-MM-DD)"),
        ("location_name", "Valley Fresh Packhouse", "Packing facility name"),
        ("location_gln", "0614141000005", "GS1 GLN (optional)"),
        ("input_lot_codes", "TOM-0226-F3-001", "Source lot code(s), comma-separated if multiple"),
    ],
    "shipping": [
        ("traceability_lot_code", "TOM-0226-F3-001", "Lot code being shipped"),
        ("product_description", "Roma Tomatoes 12ct Box", "Product name"),
        ("quantity", "200", "Quantity shipped"),
        ("unit_of_measure", "cases", "Unit"),
        ("ship_date", "2026-02-27", "Ship date (YYYY-MM-DD)"),
        ("ship_from_location", "Valley Fresh Farms, Salinas CA", "Origin facility"),
        ("ship_to_location", "Metro Distribution Center, LA", "Destination facility"),
        ("ship_from_gln", "0614141000005", "Origin GLN (optional)"),
        ("ship_to_gln", "0614141000006", "Destination GLN (optional)"),
        ("carrier_name", "Cold Express Logistics", "Carrier name (optional)"),
        ("po_number", "PO-2026-4521", "Purchase order number (optional)"),
    ],
    "receiving": [
        ("traceability_lot_code", "TOM-0226-F3-001", "Lot code received"),
        ("product_description", "Roma Tomatoes 12ct Box", "Product name"),
        ("quantity", "200", "Quantity received"),
        ("unit_of_measure", "cases", "Unit"),
        ("receive_date", "2026-02-28", "Date received (YYYY-MM-DD)"),
        ("receiving_location", "Metro Distribution Center, LA", "Receiving facility name"),
        ("receiving_gln", "0614141000006", "Receiving facility GLN (optional)"),
        ("immediate_previous_source", "Valley Fresh Farms", "Who shipped this to you"),
        ("temperature_celsius", "3.5", "Temp at receipt (optional but recommended)"),
    ],
    "transformation": [
        ("traceability_lot_code", "SALAD-0226-001", "NEW lot code for output product"),
        ("product_description", "Garden Salad Mix 16oz", "Output product description"),
        ("quantity", "1000", "Output quantity"),
        ("unit_of_measure", "bags", "Unit"),
        ("transformation_date", "2026-02-28", "Date of transformation (YYYY-MM-DD)"),
        ("location_name", "Metro Processing Plant", "Transformation facility"),
        ("location_gln", "0614141000007", "Facility GLN (optional)"),
        ("input_lot_codes", "TOM-0226-F3-001,LET-0226-A2-003", "ALL input lot codes, comma-separated"),
    ],
}


def _generate_csv_template(cte_type: str) -> str:
    """Generate a CSV template string with headers, descriptions, and example row."""
    columns = CTE_COLUMNS.get(cte_type)
    if not columns:
        raise HTTPException(status_code=404, detail=f"Unknown CTE type: {cte_type}")

    output = io.StringIO()
    writer = csv.writer(output)

    # Row 1: Column headers
    writer.writerow([col[0] for col in columns])

    # Row 2: Example data
    writer.writerow([col[1] for col in columns])

    # Row 3: Descriptions (commented)
    writer.writerow([f"# {col[2]}" for col in columns])

    return output.getvalue()


@router.get(
    "/templates/{cte_type}",
    summary="Download CSV template for a CTE type",
    description="Returns a CSV template with correct column headers and one example row.",
)
async def download_template(cte_type: str):
    """Download a CSV template for the specified CTE type."""
    cte_type = cte_type.lower()
    if cte_type not in CTE_COLUMNS:
        valid = ", ".join(CTE_COLUMNS.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Unknown CTE type '{cte_type}'. Valid types: {valid}"
        )

    csv_content = _generate_csv_template(cte_type)

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=regengine_{cte_type}_template.csv"
        },
    )


@router.get(
    "/templates",
    summary="List available CSV templates",
    description="Returns a list of available CTE types and their column definitions.",
)
async def list_templates():
    """List all available CSV templates."""
    return {
        "templates": {
            cte_type: {
                "columns": [{"name": col[0], "description": col[2]} for col in columns],
                "download_url": f"/api/v1/templates/{cte_type}",
            }
            for cte_type, columns in CTE_COLUMNS.items()
        }
    }


# Aliases for auto-detecting CTE type from a column value
_CTE_TYPE_ALIASES: dict[str, str] = {
    "harvesting": "harvesting", "harvest": "harvesting", "creation": "harvesting",
    "h": "harvesting",
    "cooling": "cooling", "cold_storage": "cooling", "c": "cooling",
    "initial_packing": "initial_packing", "packing": "initial_packing",
    "ip": "initial_packing", "p": "initial_packing",
    "shipping": "shipping", "ship": "shipping", "distribute": "shipping",
    "s": "shipping",
    "receiving": "receiving", "receive": "receiving", "receipt": "receiving",
    "r": "receiving",
    "transformation": "transformation", "transform": "transformation",
    "transforming": "transformation", "process": "transformation",
    "t": "transformation",
    "first_land_based_receiving": "first_land_based_receiving",
    "flbr": "first_land_based_receiving",
}

# Date column names per CTE type, used for timestamp detection
_DATE_FIELDS = [
    "event_date", "date", "timestamp",
    "harvest_date", "cooling_date", "packing_date",
    "ship_date", "receive_date", "transformation_date",
]

# Columns that might hold the CTE type in a mixed-type CSV
_CTE_TYPE_COLUMNS = ["cte_type", "event_type", "type", "cte"]


def _detect_row_cte_type(row: dict, fallback: Optional[str]) -> Optional[str]:
    """Detect the CTE type from a row, checking known columns then falling back."""
    for col in _CTE_TYPE_COLUMNS:
        raw = (row.get(col) or "").strip().lower().replace(" ", "_")
        if raw and raw in _CTE_TYPE_ALIASES:
            return _CTE_TYPE_ALIASES[raw]
    return fallback


@router.post(
    "/ingest/csv",
    response_model=IngestResponse,
    summary="Upload and ingest a CSV file",
    description=(
        "Parse a CSV file, validate rows, and persist CTE events to the database. "
        "Supports single-type files (pass cte_type) or mixed-type files with a "
        "cte_type/event_type column per row."
    ),
)
async def ingest_csv(
    file: UploadFile = File(..., description="CSV file to ingest"),
    cte_type: Optional[str] = Form(None, description="CTE type (optional if CSV has cte_type column)"),
    source: str = Form("csv_upload", description="Source identifier"),
    tenant_id: Optional[str] = Form(None, description="Tenant ID (default: 'default')"),
    _: None = Depends(_verify_api_key),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
):
    """Ingest a CSV file of CTE events (single-type or mixed-type)."""

    # Normalize the fallback cte_type if provided
    fallback_cte = None
    if cte_type:
        fallback_cte = _CTE_TYPE_ALIASES.get(cte_type.strip().lower().replace(" ", "_"))
        if not fallback_cte:
            valid = ", ".join(sorted(set(_CTE_TYPE_ALIASES.values())))
            raise HTTPException(status_code=400, detail=f"Unknown CTE type '{cte_type}'. Valid: {valid}")

    if not tenant_id:
        tenant_id = "default"

    # Read and parse CSV
    content = await file.read()
    text = content.decode("utf-8-sig")  # Handle BOM
    reader = csv.DictReader(io.StringIO(text))

    events: list[IngestEvent] = []
    parse_errors: list[str] = []

    for row_num, row in enumerate(reader, start=2):
        row = {(k or "").strip().lower().replace(" ", "_"): (v or "").strip() for k, v in row.items()}
        first_val = next(iter(row.values()), "")
        if first_val and str(first_val).startswith("#"):
            continue
        if not any(row.values()):
            continue

        try:
            row_cte = _detect_row_cte_type(row, fallback_cte)
            if not row_cte:
                parse_errors.append(f"Row {row_num}: No CTE type — add cte_type column or pass cte_type param")
                continue

            date_field = None
            for field_name in _DATE_FIELDS:
                if field_name in row and row[field_name]:
                    date_field = row[field_name]
                    break
            if not date_field:
                parse_errors.append(f"Row {row_num}: No date field found")
                continue

            ts = date_field
            if "T" not in ts and len(ts) <= 10:
                ts = f"{ts}T00:00:00Z"

            loc_gln = (row.get("location_gln") or row.get("ship_from_gln")
                or row.get("receiving_gln") or row.get("gln") or None)
            loc_name = (row.get("location_name") or row.get("ship_from_location")
                or row.get("receiving_location") or row.get("location_identifier")
                or row.get("facility_name") or row.get("location") or None)

            kdes = {}
            skip_fields = {"traceability_lot_code", "product_description",
                "quantity", "unit_of_measure", "location_gln", "location_name",
                "cte_type", "event_type", "type", "cte"}
            for key, val in row.items():
                if key and val and key not in skip_fields:
                    kdes[key] = val

            event = IngestEvent(
                cte_type=WebhookCTEType(row_cte),
                traceability_lot_code=row.get("traceability_lot_code") or row.get("tlc") or row.get("lot_code") or "",
                product_description=row.get("product_description") or row.get("product") or row.get("description") or "",
                quantity=float(row.get("quantity") or row.get("qty") or 0),
                unit_of_measure=row.get("unit_of_measure") or row.get("uom") or "units",
                location_gln=loc_gln,
                location_name=loc_name,
                timestamp=ts,
                kdes=kdes,
            )
            events.append(event)
        except Exception as e:
            parse_errors.append(f"Row {row_num}: {str(e)}")

    if not events and parse_errors:
        raise HTTPException(status_code=400, detail={"message": "No valid rows found", "errors": parse_errors})
    if not events:
        raise HTTPException(status_code=400, detail="CSV contained no data rows")

    payload = WebhookPayload(source=source, events=events, tenant_id=tenant_id)
    response = await ingest_events(payload, x_regengine_api_key=x_regengine_api_key)

    if parse_errors:
        from app.webhook_models import EventResult
        for err in parse_errors:
            response.events.append(EventResult(
                traceability_lot_code="", cte_type=fallback_cte or "unknown",
                status="rejected", errors=[err]))
            response.rejected += 1
            response.total += 1

    logger.info("csv_ingest_complete: total=%d accepted=%d rejected=%d",
        response.total, response.accepted, response.rejected)
    return response
