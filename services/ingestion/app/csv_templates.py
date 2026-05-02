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
import re
from datetime import datetime, timezone
from typing import Optional

from dateutil import parser as _dateutil_parser
from dateutil.parser import ParserError as _DateParserError

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from .authz import IngestionPrincipal, require_permission
from .config import get_settings
from .shared.tenant_resolution import resolve_principal_tenant_id
from .shared.upload_limits import read_upload_with_limit, MAX_CSV_FILE_SIZE_BYTES
from .webhook_models import (
    IngestEvent,
    IngestResponse,
    REQUIRED_KDES_BY_CTE,
    WebhookCTEType,
    WebhookPayload,
)
from .webhook_compat import ingest_events

logger = logging.getLogger("csv-templates")

router = APIRouter(prefix="/api/v1", tags=["CSV Templates & Import"])

# Column definitions per CTE type — each is a tuple of (column_name, example_value, description)
CTE_COLUMNS: dict[str, list[tuple[str, str, str]]] = {
    "growing": [
        ("traceability_lot_code", "ORG-KALE-0401-001", "Unique lot code for this growing batch"),
        ("product_description", "Organic Kale", "Product name"),
        ("quantity", "1200", "Numeric quantity"),
        ("unit_of_measure", "lbs", "Unit: lbs, kg, cases, pallets"),
        ("growing_area_name", "North Field Block A", "Growing area or field identifier"),
        ("event_time", "07:00:00", "Time of event HH:MM:SS (optional)"),
        ("location_name", "Sunrise Organic Farm, Watsonville CA", "Farm or growing facility name"),
        ("location_gln", "0614141000003", "GS1 GLN (optional, 13 digits)"),
        ("growing_coordinates", "36.9107,-121.7569", "GPS coordinates of growing area (optional)"),
        ("grower_name", "Sunrise Organic Farm LLC", "Business name of grower"),
    ],
    "harvesting": [
        ("traceability_lot_code", "TOM-0226-F3-001", "Unique lot code for this harvest"),
        ("product_description", "Roma Tomatoes", "Product name"),
        ("quantity", "500", "Numeric quantity"),
        ("unit_of_measure", "cases", "Unit: cases, lbs, kg, pallets"),
        ("harvest_date", "2026-02-26", "Date of harvest (YYYY-MM-DD)"),
        ("event_time", "08:30:00", "Time of event HH:MM:SS (optional)"),
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
        ("event_time", "10:00:00", "Time of event HH:MM:SS (optional)"),
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
        ("event_time", "14:00:00", "Time of event HH:MM:SS (optional)"),
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
        ("event_time", "16:30:00", "Time of event HH:MM:SS (optional)"),
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
        ("event_time", "09:15:00", "Time of event HH:MM:SS (optional)"),
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
        ("event_time", "10:00:00", "Time of event HH:MM:SS (optional)"),
        ("location_name", "Metro Processing Plant", "Transformation facility"),
        ("location_gln", "0614141000007", "Facility GLN (optional)"),
        ("input_lot_codes", "TOM-0226-F3-001,LET-0226-A2-003", "ALL input lot codes, comma-separated"),
    ],
    "first_land_based_receiving": [
        ("traceability_lot_code", "SAL-0301-DOCK4-001", "Lot code assigned at landing"),
        ("product_description", "Atlantic Salmon Fillets", "Product name"),
        ("quantity", "2000", "Numeric quantity"),
        ("unit_of_measure", "lbs", "Unit: lbs, kg, cases, pallets"),
        ("landing_date", "2026-03-01", "Date of first land-based receipt (YYYY-MM-DD)"),
        ("event_time", "06:00:00", "Time of event HH:MM:SS (optional)"),
        ("receiving_location", "Pacific Seafood Dock 4, Portland OR", "Receiving facility name"),
        ("receiving_gln", "0614141000020", "Receiving facility GLN (optional, 13 digits)"),
        ("immediate_previous_source", "FV Ocean Harvest", "Vessel or entity that delivered product"),
        ("reference_document", "BOL-2026-0301-042", "Bill of lading or reference document number"),
        ("temperature_celsius", "-1.5", "Temperature at receipt (optional but recommended)"),
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
    """List available CSV templates (canonical FSMA 204 CTEs only)."""
    # "growing" template kept for backwards-compat downloads but hidden
    # from listing — it is not one of the 7 FDA-defined CTEs.
    return {
        "templates": {
            cte_type: {
                "columns": [{"name": col[0], "description": col[2]} for col in columns],
                "download_url": f"/api/v1/templates/{cte_type}",
            }
            for cte_type, columns in CTE_COLUMNS.items()
            if cte_type != "growing"
        }
    }


# Aliases for auto-detecting CTE type from a column value.
# Canonical FSMA 204 CTEs: harvesting, cooling, initial_packing,
# first_land_based_receiving, shipping, receiving, transformation.
# "growing" and "creation" are accepted for backwards compatibility
# and normalize to "harvesting".
_CTE_TYPE_ALIASES: dict[str, str] = {
    "harvesting": "harvesting", "harvest": "harvesting",
    "creation": "harvesting", "growing": "harvesting",
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
    "landing_date",
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


# Map CTE type → the specific date KDE the validator expects
_CTE_DATE_KDE: dict[str, str] = {
    "harvesting": "harvest_date",
    "cooling": "cooling_date",
    "initial_packing": "packing_date",
    "shipping": "ship_date",
    "receiving": "receive_date",
    "transformation": "transformation_date",
    "first_land_based_receiving": "landing_date",
}


def _inject_required_kdes(kdes: dict, row_cte: str, row: dict, loc_name: Optional[str], date_val: str) -> None:
    """Auto-inject CTE-specific required KDEs from generic CSV columns."""
    # Inject the CTE-specific date field
    date_kde = _CTE_DATE_KDE.get(row_cte)
    if date_kde and date_kde not in kdes:
        # Use just the date portion (YYYY-MM-DD)
        kdes[date_kde] = date_val[:10] if date_val else ""

    # Inject location KDEs that the validator requires
    if row_cte == "shipping":
        if "ship_from_location" not in kdes and loc_name:
            kdes["ship_from_location"] = loc_name
        if "ship_to_location" not in kdes:
            kdes["ship_to_location"] = row.get("ship_to_location") or row.get("destination") or "See receiver"
    elif row_cte in ("receiving", "first_land_based_receiving"):
        if "receiving_location" not in kdes and loc_name:
            kdes["receiving_location"] = loc_name

    # Inject standard fields the validator checks in KDEs
    for kde_key, row_keys in [
        ("traceability_lot_code", ["traceability_lot_code", "tlc", "lot_code"]),
        ("product_description", ["product_description", "product", "description"]),
        ("quantity", ["quantity", "qty"]),
        ("unit_of_measure", ["unit_of_measure", "uom"]),
        ("location_name", ["location_name", "facility_name", "location"]),
    ]:
        if kde_key not in kdes:
            for rk in row_keys:
                if row.get(rk):
                    kdes[kde_key] = row[rk]
                    break


def _validate_kde_completeness(
    cte_type: str, event: IngestEvent, kdes: dict
) -> list[str]:
    """Check required KDEs for a CTE type. Returns list of missing field names."""
    try:
        cte_enum = WebhookCTEType(cte_type)
    except ValueError:
        return []
    required = REQUIRED_KDES_BY_CTE.get(cte_enum, [])
    missing = []
    for field in required:
        # Check in top-level event fields first, then KDEs
        if field in {"traceability_lot_code", "product_description", "quantity", "unit_of_measure"}:
            val = getattr(event, field, None)
            if val is None or str(val).strip() in ("", "0", "0.0"):
                missing.append(field)
        elif field == "location_name":
            if not (event.location_name or kdes.get("location_name")):
                missing.append(field)
        else:
            val = kdes.get(field)
            if val is None or str(val).strip() == "":
                missing.append(field)
    return missing


# ── UOM normalisation ────────────────────────────────────────────────────────
# Maps common abbreviations / typos → canonical FSMA 204 unit strings.
_UOM_ALIASES: dict[str, str] = {
    "lb": "lbs", "pound": "lbs", "pounds": "lbs", "lb.": "lbs",
    "kilogram": "kg", "kilograms": "kg", "kgs": "kg",
    "ounce": "oz", "ounces": "oz",
    "gram": "g", "grams": "g",
    "ton": "tons", "tonne": "mt", "tonnes": "mt", "metric_ton": "mt", "metric ton": "mt",
    "case": "cases", "cs": "cases",
    "carton": "cartons", "ctn": "cartons", "ctns": "cartons",
    "box": "boxes", "bx": "boxes", "bxs": "boxes",
    "crate": "crates", "crt": "crates",
    "bin": "bins",
    "pallet": "pallets", "plt": "pallets", "plts": "pallets", "skid": "pallets",
    "tote": "totes",
    "bag": "bags", "bg": "bags",
    "sack": "sacks", "sk": "sacks",
    "ea": "each", "pc": "pieces", "piece": "pieces",
    "unit": "units", "un": "units",
    "ct": "count",
    "gallon": "gallons", "gal": "gallons", "gals": "gallons",
    "liter": "liters", "litre": "liters", "litres": "liters",
    "barrel": "barrels", "bbl": "barrels",
    "bushel": "bushels", "bu": "bushels",
}


def _normalize_uom(raw: str) -> str:
    """Map common UOM abbreviations/typos to canonical FSMA 204 units.

    Falls back to the lowercased input so the model validator can still
    warn about truly unknown values rather than crashing on abbreviations.
    """
    normalized = raw.strip().lower().rstrip(".")
    return _UOM_ALIASES.get(normalized, normalized)


# ── Location / string normalisation ─────────────────────────────────────────
_LOCATION_ABBREV_PATTERNS: list[tuple[str, str]] = [
    (r"\bwhse\b",   "Warehouse"),
    (r"\bwhs\b",    "Warehouse"),
    (r"\bdist\.?\b","Distribution"),
    (r"\bmfg\.?\b", "Manufacturing"),
    (r"\bfac\.?\b", "Facility"),
    (r"\bpkg\.?\b", "Packaging"),
    (r"\brecv\.?\b","Receiving"),
    (r"\bshpg\.?\b","Shipping"),
    (r"\bctr\.?\b", "Center"),
    (r"\bcntr\.?\b","Center"),
    (r"\bhdqtrs?\b","Headquarters"),
    (r"\bblvd\.?\b","Boulevard"),
    (r"\bave\.?\b", "Avenue"),
]


def _normalize_location(raw: str) -> str:
    """Strip whitespace, collapse runs, and expand common abbreviations."""
    val = " ".join(raw.strip().split())
    for pattern, replacement in _LOCATION_ABBREV_PATTERNS:
        val = re.sub(pattern, replacement, val, flags=re.IGNORECASE)
    return val


# ── Flexible date parsing ────────────────────────────────────────────────────
_SENTINEL_TS = "1970-01-01T00:00:00Z"  # placeholder when date is unreadable


def _parse_date_flexible(raw: str, event_time: str = "") -> tuple[str, str | None]:
    """Parse a date string in *any* common format into an ISO 8601 UTC timestamp.

    Handles YYYY-MM-DD, M/D/YY, April 2nd 2026, 04-01-2026, and more.

    Returns:
        (iso_ts, warning)  — warning is None on success, or a human-readable
        message describing why the date could not be parsed.  In that case
        iso_ts is _SENTINEL_TS so the row can still be ingested and flagged.
    """
    if not raw or not raw.strip():
        return _SENTINEL_TS, "date field was empty"

    raw = raw.strip()

    # Fast-path: already an ISO timestamp
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z"), None
    except (ValueError, AttributeError):
        pass

    # Flexible parsing: handles M/D/YY, "April 2nd", "04-01-2026", etc.
    try:
        dt = _dateutil_parser.parse(raw, fuzzy=True, dayfirst=False)
        # Merge in a separate event_time field if provided
        if event_time:
            try:
                t = _dateutil_parser.parse(event_time)
                dt = dt.replace(hour=t.hour, minute=t.minute, second=t.second)
            except (_DateParserError, ValueError):
                pass
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z"), None
    except (_DateParserError, ValueError, OverflowError):
        pass

    return _SENTINEL_TS, f"INVALID_FORMAT: could not parse date '{raw}'"


# ── Lot-code integrity checks ────────────────────────────────────────────────
_LOT_DIGIT_ADJACENT = re.compile(r"(?<=[0-9])[OI]|[OI](?=[0-9])", re.IGNORECASE)


def _check_lot_code_integrity(lot_code: str) -> list[str]:
    """Flag likely O↔0 and I↔1 character swaps in a Traceability Lot Code.

    Returns a (possibly empty) list of human-readable integrity warnings.
    These are advisory — the row is still ingested.
    """
    if not lot_code:
        return []
    warnings: list[str] = []
    suspicious = _LOT_DIGIT_ADJACENT.findall(lot_code)
    if suspicious:
        chars = ", ".join(f"'{c}'" for c in set(s.upper() for s in suspicious))
        warnings.append(
            f"lot_code '{lot_code}': possible character swap ({chars} adjacent to digits — "
            f"verify O vs 0 or I vs 1)"
        )
    # All-alpha codes longer than 3 chars have no digits — flag for review
    if lot_code.isalpha() and len(lot_code) > 3:
        warnings.append(
            f"lot_code '{lot_code}': no digits found — confirm this is not a data entry error"
        )
    return warnings


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
    tenant_id: Optional[str] = Form(None, description="Tenant ID for legacy/master-key callers"),
    principal: IngestionPrincipal = Depends(require_permission("webhooks.ingest")),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
):
    """Ingest a CSV file of CTE events (single-type or mixed-type)."""

    # Normalize the fallback cte_type if provided
    fallback_cte = None
    if cte_type:
        fallback_cte = _CTE_TYPE_ALIASES.get(cte_type.strip().lower().replace(" ", "_"))
        if not fallback_cte:
            valid = ", ".join(sorted(set(_CTE_TYPE_ALIASES.values())))
            raise HTTPException(status_code=400, detail=f"Unknown CTE type '{cte_type}'. Valid: {valid}")

    tenant_id = resolve_principal_tenant_id(tenant_id, x_tenant_id, principal.tenant_id)

    # Read and parse CSV
    content = await read_upload_with_limit(file, max_bytes=MAX_CSV_FILE_SIZE_BYTES, label="CSV file")
    text = content.decode("utf-8-sig")  # Handle BOM
    reader = csv.DictReader(io.StringIO(text))

    events: list[IngestEvent] = []
    parse_errors: list[str] = []
    kde_warnings: list[str] = []
    MAX_CSV_ROWS = 500

    for row_num, row in enumerate(reader, start=2):
        if row_num - 1 > MAX_CSV_ROWS:
            parse_errors.append(f"Row {row_num}: CSV exceeds maximum row limit of {MAX_CSV_ROWS}")
            break
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

            # ── Phase 1: Ingestion — flexible, never crashes on bad data ──────
            # Date: accept any human format; sentinel + warning on total failure
            raw_date = next(
                (row[f] for f in _DATE_FIELDS if row.get(f)),
                ""
            )
            event_time_raw = (row.get("event_time") or "").strip()
            ts, date_warning = _parse_date_flexible(raw_date, event_time_raw)
            if date_warning:
                kde_warnings.append(f"Row {row_num}: {date_warning}")

            # Location: strip whitespace and expand abbreviations
            loc_gln = (row.get("location_gln") or row.get("ship_from_gln")
                or row.get("receiving_gln") or row.get("gln") or None)
            _loc_raw = (row.get("location_name") or row.get("ship_from_location")
                or row.get("receiving_location") or row.get("location_identifier")
                or row.get("facility_name") or row.get("location") or "")
            loc_name = _normalize_location(_loc_raw) if _loc_raw else None

            # Unit of measure: map abbreviations before Pydantic sees them
            uom_raw = (row.get("unit_of_measure") or row.get("uom") or "units")
            uom = _normalize_uom(uom_raw)

            # Lot code: extract and run integrity checks
            lot_code = (row.get("traceability_lot_code") or row.get("tlc")
                or row.get("lot_code") or "")
            for integrity_warn in _check_lot_code_integrity(lot_code):
                kde_warnings.append(f"Row {row_num}: {integrity_warn}")

            kdes: dict = {}
            skip_fields = {"traceability_lot_code", "product_description",
                "quantity", "unit_of_measure", "location_gln", "location_name",
                "cte_type", "event_type", "type", "cte", "input_lot_codes",
                "event_time"}
            for key, val in row.items():
                if key and val and key not in skip_fields:
                    kdes[key] = val

            # Store original date string for audit trail when it was unparseable
            if date_warning:
                kdes["_original_date_value"] = raw_date
                kdes["_date_parse_status"] = "INVALID_FORMAT"

            # Parse input_lot_codes (comma-separated) if present
            input_lot_codes_raw = row.get("input_lot_codes")
            if input_lot_codes_raw:
                input_lot_codes = [c.strip() for c in input_lot_codes_raw.split(",") if c.strip()]
                if input_lot_codes:
                    kdes["input_lot_codes"] = input_lot_codes

            # Auto-inject CTE-specific required KDEs from generic CSV columns
            _inject_required_kdes(kdes, row_cte, row, loc_name, raw_date)

            event = IngestEvent(
                cte_type=WebhookCTEType(row_cte),
                traceability_lot_code=lot_code,
                product_description=(row.get("product_description") or row.get("product")
                    or row.get("description") or ""),
                quantity=float(row.get("quantity") or row.get("qty") or 0),
                unit_of_measure=uom,
                location_gln=loc_gln,
                location_name=loc_name,
                timestamp=ts,
                kdes=kdes,
            )
            events.append(event)

            # KDE completeness validation (warn, don't reject)
            missing_kdes = _validate_kde_completeness(row_cte, event, kdes)
            if missing_kdes:
                kde_warnings.append(
                    f"Row {row_num}: Missing KDEs for {row_cte}: {', '.join(missing_kdes)}"
                )
        except Exception as e:
            parse_errors.append(f"Row {row_num}: {str(e)}")

    if not events and parse_errors:
        raise HTTPException(status_code=400, detail={"message": "No valid rows found", "errors": parse_errors})
    if not events:
        raise HTTPException(status_code=400, detail="CSV contained no data rows")

    payload = WebhookPayload(source=source, events=events, tenant_id=tenant_id)
    response = await ingest_events(payload, x_regengine_api_key=x_regengine_api_key)

    if parse_errors:
        from .webhook_models import EventResult
        for err in parse_errors:
            response.events.append(EventResult(
                traceability_lot_code="", cte_type=fallback_cte or "unknown",
                status="rejected", errors=[err]))
            response.rejected += 1
            response.total += 1

    if kde_warnings:
        logger.warning("csv_ingest_kde_warnings: %d events with missing KDEs: %s",
            len(kde_warnings), "; ".join(kde_warnings[:5]))

    logger.info("csv_ingest_complete: total=%d accepted=%d rejected=%d kde_warnings=%d",
        response.total, response.accepted, response.rejected, len(kde_warnings))

    # Attach KDE warnings as extra response metadata via JSONResponse
    # so callers can see which events are missing required fields
    from fastapi.responses import JSONResponse
    response_data = response.model_dump()
    if kde_warnings:
        response_data["kde_warnings"] = kde_warnings
        response_data["kde_warning_count"] = len(kde_warnings)
    return JSONResponse(content=response_data)
