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
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Optional

from dateutil import parser as _dateutil_parser
from dateutil.parser import ParserError as _DateParserError
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from shared.agent_task_bridge import enqueue_agent_artifact_task
from shared.database import SessionLocal
from shared.jev import JevDecider, get_jev_decider
from shared.jev.header_mapping import (
    QUESTIONS_VERSION as _JEV_QUESTIONS_VERSION,
    HeaderMappingResult,
    build_field_mapping_artifacts,
    collect_sample_values,
    normalize_csv_header,
    outranked_columns,
    suggest_header_mappings,
    unrecognized_headers,
)
from shared.tenant_context import set_tenant_guc

from .authz import IngestionPrincipal, require_permission
from .config import get_settings
from .shared.tenant_resolution import resolve_principal_tenant_id
from .shared.upload_limits import MAX_CSV_FILE_SIZE_BYTES, read_upload_with_limit
from .webhook_compat import SourceFileReceipt, ingest_events
from .webhook_models import (
    REQUIRED_KDES_BY_CTE,
    CsvIngestResponse,
    HeaderMappingEngineResult,
    HeaderMappingSuggestionResult,
    IngestEvent,
    WebhookCTEType,
    WebhookPayload,
)

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
        ("location_gln", "0614141000012", "GS1 GLN (optional, 13 digits)"),
        ("growing_coordinates", "36.9107,-121.7569", "GPS coordinates of growing area (optional)"),
        ("grower_name", "Sunrise Organic Farm LLC", "Business name of grower"),
        ("harvest_date", "2026-04-01", "Date of harvest (YYYY-MM-DD) — growing rows ingest as harvesting"),
        ("reference_document", "HARV-2026-0401-001", "Harvest record or reference document number"),
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
        ("reference_document", "HARV-2026-0226-001", "Harvest record or reference document number"),
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
        ("reference_document", "COOL-2026-0226-014", "Cooling record or reference document number"),
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
        (
            "input_quantities",
            "200",
            "Quantity of EACH source lot used, comma-separated in the same order as input_lot_codes",
        ),
        ("input_units_of_measure", "cases", "Unit for each source lot, comma-separated (one value applies to all)"),
        ("reference_document", "PACK-2026-0226-007", "Packing record or reference document number"),
        ("harvester_business_name", "Valley Fresh Farms LLC", "Business name of the harvester"),
        ("harvester_business_phone", "+1-202-555-0100", "Phone number of the harvester; sample number only"),
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
        ("ship_to_gln", "0614141000029", "Destination GLN (optional)"),
        ("carrier_name", "Cold Express Logistics", "Carrier name (optional)"),
        ("po_number", "PO-2026-4521", "Purchase order number (optional)"),
        ("reference_document", "BOL-2026-0227-042", "Bill of lading or reference document number"),
        (
            "tlc_source_reference",
            "PACK-2026-0226-007",
            "Reference to where the lot code was assigned (packing record or source location)",
        ),
    ],
    "receiving": [
        ("traceability_lot_code", "TOM-0226-F3-001", "Lot code received"),
        ("product_description", "Roma Tomatoes 12ct Box", "Product name"),
        ("quantity", "200", "Quantity received"),
        ("unit_of_measure", "cases", "Unit"),
        ("receive_date", "2026-02-28", "Date received (YYYY-MM-DD)"),
        ("event_time", "09:15:00", "Time of event HH:MM:SS (optional)"),
        ("receiving_location", "Metro Distribution Center, LA", "Receiving facility name"),
        ("receiving_gln", "0614141000029", "Receiving facility GLN (optional)"),
        ("immediate_previous_source", "Valley Fresh Farms", "Who shipped this to you"),
        ("temperature_celsius", "3.5", "Temp at receipt (optional but recommended)"),
        ("reference_document", "RCV-2026-0228-011", "Receiving record or reference document number"),
        (
            "tlc_source_reference",
            "PACK-2026-0226-007",
            "Reference to where the lot code was assigned (packing record or source location)",
        ),
    ],
    "transformation": [
        ("traceability_lot_code", "SALAD-0226-001", "NEW lot code for output product"),
        ("product_description", "Garden Salad Mix 16oz", "Output product description"),
        ("quantity", "1000", "Output quantity"),
        ("unit_of_measure", "bags", "Unit"),
        ("transformation_date", "2026-02-28", "Date of transformation (YYYY-MM-DD)"),
        ("event_time", "10:00:00", "Time of event HH:MM:SS (optional)"),
        ("location_name", "Metro Processing Plant", "Transformation facility"),
        ("location_gln", "0614141000036", "Facility GLN (optional)"),
        ("input_lot_codes", "TOM-0226-F3-001,LET-0226-A2-003", "ALL input lot codes, comma-separated"),
        (
            "input_quantities",
            "600,400",
            "Quantity of EACH input lot used, comma-separated in the same order as input_lot_codes (21 CFR 1.1350(a)(1)(iii))",
        ),
        (
            "input_units_of_measure",
            "cases,cases",
            "Unit for each input lot, comma-separated (one value applies to all)",
        ),
        ("reference_document", "PROD-2026-0228-003", "Production record or reference document number"),
    ],
    "first_land_based_receiving": [
        ("traceability_lot_code", "SAL-0301-DOCK4-001", "Lot code assigned at landing"),
        ("product_description", "Atlantic Salmon Fillets", "Product name"),
        ("quantity", "2000", "Numeric quantity"),
        ("unit_of_measure", "lbs", "Unit: lbs, kg, cases, pallets"),
        ("landing_date", "2026-03-01", "Date of first land-based receipt (YYYY-MM-DD)"),
        ("event_time", "06:00:00", "Time of event HH:MM:SS (optional)"),
        ("receiving_location", "Pacific Seafood Dock 4, Portland OR", "Receiving facility name"),
        ("receiving_gln", "0614141000043", "Receiving facility GLN (optional, 13 digits)"),
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
        raise HTTPException(status_code=404, detail=f"Unknown CTE type '{cte_type}'. Valid types: {valid}")

    csv_content = _generate_csv_template(cte_type)

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=regengine_{cte_type}_template.csv"},
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
    "harvesting": "harvesting",
    "harvest": "harvesting",
    "creation": "harvesting",
    "growing": "harvesting",
    "h": "harvesting",
    "cooling": "cooling",
    "cold_storage": "cooling",
    "c": "cooling",
    "initial_packing": "initial_packing",
    "packing": "initial_packing",
    "ip": "initial_packing",
    "p": "initial_packing",
    "shipping": "shipping",
    "ship": "shipping",
    "distribute": "shipping",
    "s": "shipping",
    "receiving": "receiving",
    "receive": "receiving",
    "receipt": "receiving",
    "r": "receiving",
    "transformation": "transformation",
    "transform": "transformation",
    "transforming": "transformation",
    "process": "transformation",
    "t": "transformation",
    "first_land_based_receiving": "first_land_based_receiving",
    "flbr": "first_land_based_receiving",
}

# Date column names per CTE type, used for timestamp detection
_DATE_FIELDS = [
    "event_date",
    "date",
    "timestamp",
    "harvest_date",
    "cooling_date",
    "packing_date",
    "ship_date",
    "receive_date",
    "transformation_date",
    "landing_date",
]

# Columns that might hold the CTE type in a mixed-type CSV
_CTE_TYPE_COLUMNS = ["cte_type", "event_type", "type", "cte"]

# Fallback chains: when several columns can supply the same field, the first
# present, non-empty one wins. ``parse_csv_rows`` reads through these tuples
# (never through ad-hoc ``row.get(a) or row.get(b)`` chains) so the Jev apply
# policy below can see the same precedence: a mapped column copied under a
# key that outranks a column the file already carries would silently replace
# the uploader's own value.
_LOT_CODE_COLUMNS = ("traceability_lot_code", "tlc", "lot_code")
_PRODUCT_COLUMNS = ("product_description", "product", "description")
_QUANTITY_COLUMNS = ("quantity", "qty")
_UNIT_COLUMNS = ("unit_of_measure", "uom")
_LOCATION_GLN_COLUMNS = ("location_gln", "ship_from_gln", "receiving_gln", "gln")
_LOCATION_NAME_COLUMNS = (
    "location_name",
    "ship_from_location",
    "receiving_location",
    "location_identifier",
    "facility_name",
    "location",
)
_SHIP_TO_COLUMNS = ("ship_to_location", "destination")
_COLUMN_PRECEDENCE: tuple[tuple[str, ...], ...] = (
    tuple(_DATE_FIELDS),
    tuple(_CTE_TYPE_COLUMNS),
    _LOT_CODE_COLUMNS,
    _PRODUCT_COLUMNS,
    _QUANTITY_COLUMNS,
    _UNIT_COLUMNS,
    _LOCATION_GLN_COLUMNS,
    _LOCATION_NAME_COLUMNS,
    _SHIP_TO_COLUMNS,
)


def _first_present(row: Mapping[str, Optional[str]], keys: Sequence[str]) -> str:
    """The first non-empty value among ``keys`` in ``row`` (parser precedence), else ``""``."""
    for key in keys:
        value = row.get(key)
        if value:
            return value
    return ""


def _row_provides(row: Mapping[str, Optional[str]], canonical_field: str) -> bool:
    """True when copying a mapped value under ``canonical_field`` would replace one the row carries.

    That is the case when the row already has ``canonical_field`` itself, or a
    non-empty column the parser consults only after it (see
    ``_COLUMN_PRECEDENCE``): the copy would outrank that column.
    """
    if row.get(canonical_field):
        return True
    return any(row.get(key) for key in outranked_columns(canonical_field, _COLUMN_PRECEDENCE))


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

# Every normalised column name ``parse_csv_rows`` (or a validator it feeds)
# reads by name. A header outside this set is opaque to the parser: it passes
# through into ``kdes`` unchanged and can never satisfy a required KDE. Those
# are the only columns the Jev header-mapping step is asked about.
_RECOGNIZED_COLUMNS: frozenset[str] = frozenset(
    {
        "input_lot_codes",
        "input_quantities",
        "input_units_of_measure",
        "event_time",
        # Read from ``kdes`` by ``normalize_webhook_event`` (transport_reference).
        "carrier",
    }
    | {key for chain in _COLUMN_PRECEDENCE for key in chain}
    | {column for columns in CTE_COLUMNS.values() for column, _, _ in columns}
    | {kde for kdes in REQUIRED_KDES_BY_CTE.values() for kde in kdes}
)


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
        # No default when the ship-to is absent: the completeness check
        # reports it missing and the ship-to rule fails on the event, which
        # is the true state of the record.
        if "ship_to_location" not in kdes:
            ship_to = _first_present(row, _SHIP_TO_COLUMNS)
            if ship_to:
                kdes["ship_to_location"] = ship_to
    elif row_cte in ("receiving", "first_land_based_receiving"):
        if "receiving_location" not in kdes and loc_name:
            kdes["receiving_location"] = loc_name

    # Inject standard fields the validator checks in KDEs
    for kde_key, row_keys in [
        ("traceability_lot_code", _LOT_CODE_COLUMNS),
        ("product_description", _PRODUCT_COLUMNS),
        ("quantity", _QUANTITY_COLUMNS),
        ("unit_of_measure", _UNIT_COLUMNS),
        # Deliberately narrower than _LOCATION_NAME_COLUMNS: the ship-from and
        # receiving columns are their own KDEs and must not double as this one.
        ("location_name", ("location_name", "facility_name", "location")),
    ]:
        if kde_key not in kdes:
            value = _first_present(row, row_keys)
            if value:
                kdes[kde_key] = value


def _validate_kde_completeness(cte_type: str, event: IngestEvent, kdes: dict) -> list[str]:
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
    "lb": "lbs",
    "pound": "lbs",
    "pounds": "lbs",
    "lb.": "lbs",
    "kilogram": "kg",
    "kilograms": "kg",
    "kgs": "kg",
    "ounce": "oz",
    "ounces": "oz",
    "gram": "g",
    "grams": "g",
    "ton": "tons",
    "tonne": "mt",
    "tonnes": "mt",
    "metric_ton": "mt",
    "metric ton": "mt",
    "case": "cases",
    "cs": "cases",
    "carton": "cartons",
    "ctn": "cartons",
    "ctns": "cartons",
    "box": "boxes",
    "bx": "boxes",
    "bxs": "boxes",
    "crate": "crates",
    "crt": "crates",
    "bin": "bins",
    "pallet": "pallets",
    "plt": "pallets",
    "plts": "pallets",
    "skid": "pallets",
    "tote": "totes",
    "bag": "bags",
    "bg": "bags",
    "sack": "sacks",
    "sk": "sacks",
    "ea": "each",
    "pc": "pieces",
    "piece": "pieces",
    "unit": "units",
    "un": "units",
    "ct": "count",
    "gallon": "gallons",
    "gal": "gallons",
    "gals": "gallons",
    "liter": "liters",
    "litre": "liters",
    "litres": "liters",
    "barrel": "barrels",
    "bbl": "barrels",
    "bushel": "bushels",
    "bu": "bushels",
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
    (r"\bwhse\b", "Warehouse"),
    (r"\bwhs\b", "Warehouse"),
    (r"\bdist\.?\b", "Distribution"),
    (r"\bmfg\.?\b", "Manufacturing"),
    (r"\bfac\.?\b", "Facility"),
    (r"\bpkg\.?\b", "Packaging"),
    (r"\brecv\.?\b", "Receiving"),
    (r"\bshpg\.?\b", "Shipping"),
    (r"\bctr\.?\b", "Center"),
    (r"\bcntr\.?\b", "Center"),
    (r"\bhdqtrs?\b", "Headquarters"),
    (r"\bblvd\.?\b", "Boulevard"),
    (r"\bave\.?\b", "Avenue"),
]


def _normalize_location(raw: str) -> str:
    """Strip whitespace, collapse runs, and expand common abbreviations."""
    val = " ".join(raw.strip().split())
    for pattern, replacement in _LOCATION_ABBREV_PATTERNS:
        val = re.sub(pattern, replacement, val, flags=re.IGNORECASE)
    return val


# ── Flexible date parsing ────────────────────────────────────────────────────


def _parse_date_flexible(raw: str, event_time: str = "") -> tuple[str | None, str | None]:
    """Parse a date string in *any* common format into an ISO 8601 UTC timestamp.

    Handles YYYY-MM-DD, M/D/YY, April 2nd 2026, 04-01-2026, and more.

    Returns:
        (iso_ts, warning)  — warning is None on success, or a human-readable
        message describing why the date could not be parsed.  In that case
        iso_ts is None: an unreadable date yields no timestamp. Rows ingested
        before this change may carry the old ``1970-01-01T00:00:00Z``
        placeholder.
    """
    if not raw or not raw.strip():
        return None, "date field was empty"

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

    return None, f"INVALID_FORMAT: could not parse date '{raw}'"


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
            f"lot_code '{lot_code}': possible character swap ({chars} adjacent to digits — verify O vs 0 or I vs 1)"
        )
    # All-alpha codes longer than 3 chars have no digits — flag for review
    if lot_code.isalpha() and len(lot_code) > 3:
        warnings.append(f"lot_code '{lot_code}': no digits found — confirm this is not a data entry error")
    return warnings


def _parse_input_quantities(
    row: dict, input_lot_codes: list[str], row_cte: str
) -> tuple[list[dict], Optional[str], Optional[str]]:
    """Build ``kdes.inputs`` from ``input_quantities`` / ``input_units_of_measure``.

    Returns ``(inputs, error, warning)``. ``inputs`` is a list of
    ``{"traceability_lot_code", "quantity", "unit_of_measure"}`` aligned with
    ``input_lot_codes``. ``error`` rejects the row (misaligned or non-numeric
    values); ``warning`` is advisory (a transformation row that names input
    lots without their quantities).
    """
    quantities_raw = (row.get("input_quantities") or "").strip()
    units_raw = (row.get("input_units_of_measure") or "").strip()
    if not quantities_raw and not units_raw:
        if input_lot_codes and row_cte == "transformation":
            return (
                [],
                None,
                "input_quantities missing: 21 CFR 1.1350(a)(1)(iii) requires the quantity and unit of "
                "measure of each input lot (add input_quantities and input_units_of_measure)",
            )
        return [], None, None
    if not input_lot_codes:
        return [], "input_quantities given without input_lot_codes", None
    quantities = [q.strip() for q in quantities_raw.split(",")] if quantities_raw else []
    units = [u.strip() for u in units_raw.split(",")] if units_raw else []
    if len(quantities) != len(input_lot_codes):
        return (
            [],
            f"input_quantities lists {len(quantities)} value(s) for {len(input_lot_codes)} input lot(s); "
            "give one quantity per input lot in the same order as input_lot_codes",
            None,
        )
    if len(units) == 1 and len(input_lot_codes) > 1:
        units = units * len(input_lot_codes)
    if len(units) != len(input_lot_codes):
        return (
            [],
            f"input_units_of_measure lists {len(units)} value(s) for {len(input_lot_codes)} input lot(s); "
            "give one unit per input lot, or a single unit that applies to all",
            None,
        )
    inputs: list[dict] = []
    for lot, quantity_text, unit_text in zip(input_lot_codes, quantities, units):
        try:
            quantity = float(quantity_text)
        except ValueError:
            return [], f"input quantity {quantity_text!r} for input lot {lot} is not a number", None
        if quantity < 0:
            return [], f"input quantity {quantity_text!r} for input lot {lot} is negative", None
        if not unit_text:
            return [], f"input unit of measure for input lot {lot} is blank", None
        inputs.append(
            {"traceability_lot_code": lot, "quantity": quantity, "unit_of_measure": _normalize_uom(unit_text)}
        )
    return inputs, None, None


def parse_csv_rows(
    text: str,
    fallback_cte: Optional[str] = None,
    header_mapping: Optional[Mapping[str, str]] = None,
) -> tuple[list[IngestEvent], list[str], list[str]]:
    """Parse CSV text into ``IngestEvent`` objects.

    Shared by the ``/ingest/csv`` upload route and any other ingestion
    entrypoint (e.g. the Postmark inbound-email webhook) that needs to accept
    the same CSV structure and produce identical validation results — this
    is the single place CTE/KDE row-mapping logic lives.

    ``header_mapping`` (``normalised source column -> canonical column``) is
    the set of Jev header suggestions that passed the apply policy in
    ``shared.jev.header_mapping``. Each mapped value is copied under the
    canonical key before the row is read, unless the row already provides
    that field through the canonical key or a column the parser consults
    after it (``_row_provides``): a mapping never replaces a value the file
    carries. The source column is left in place so the raw column still
    reaches ``kdes`` and nothing is lost.

    Returns ``(events, parse_errors, kde_warnings)``.
    """
    reader = csv.DictReader(io.StringIO(text))

    events: list[IngestEvent] = []
    parse_errors: list[str] = []
    kde_warnings: list[str] = []
    MAX_CSV_ROWS = 500

    for row_num, row in enumerate(reader, start=2):
        if row_num - 1 > MAX_CSV_ROWS:
            parse_errors.append(f"Row {row_num}: CSV exceeds maximum row limit of {MAX_CSV_ROWS}")
            break
        row = {normalize_csv_header(k): (v or "").strip() for k, v in row.items()}
        if header_mapping:
            for source_key, canonical_field in header_mapping.items():
                value = row.get(source_key)
                if value and not _row_provides(row, canonical_field):
                    row[canonical_field] = value
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

            # ── Phase 1: Ingestion — flexible on format, strict on presence ──
            # Date: accept any human format. An unreadable or empty date
            # rejects the row; a placeholder timestamp would enter the hash
            # chain as evidence of when the event happened.
            raw_date = _first_present(row, _DATE_FIELDS)
            event_time_raw = (row.get("event_time") or "").strip()
            ts, date_warning = _parse_date_flexible(raw_date, event_time_raw)
            if ts is None:
                parse_errors.append(f"Row {row_num}: {date_warning}")
                continue

            # Location: strip whitespace and expand abbreviations
            loc_gln = _first_present(row, _LOCATION_GLN_COLUMNS) or None
            _loc_raw = _first_present(row, _LOCATION_NAME_COLUMNS)
            loc_name = _normalize_location(_loc_raw) if _loc_raw else None

            # Unit of measure: map abbreviations before Pydantic sees them.
            # No default: a unit the uploader did not record is not "units".
            uom_raw = _first_present(row, _UNIT_COLUMNS)
            if not uom_raw:
                parse_errors.append(f"Row {row_num}: unit_of_measure is required")
                continue
            uom = _normalize_uom(uom_raw)

            # Quantity: required and numeric. The generic exception handler
            # below would reject the row too, but with an opaque message.
            quantity_raw = _first_present(row, _QUANTITY_COLUMNS)
            if not quantity_raw:
                parse_errors.append(f"Row {row_num}: quantity is required")
                continue
            try:
                quantity = float(quantity_raw)
            except ValueError:
                parse_errors.append(f"Row {row_num}: quantity '{quantity_raw}' is not a number")
                continue

            # Lot code: extract and run integrity checks
            lot_code = _first_present(row, _LOT_CODE_COLUMNS)
            for integrity_warn in _check_lot_code_integrity(lot_code):
                kde_warnings.append(f"Row {row_num}: {integrity_warn}")

            kdes: dict = {}
            skip_fields = {
                "traceability_lot_code",
                "product_description",
                "quantity",
                "unit_of_measure",
                "location_gln",
                "location_name",
                "cte_type",
                "event_type",
                "type",
                "cte",
                "input_lot_codes",
                "input_quantities",
                "input_units_of_measure",
                "event_time",
            }
            for key, val in row.items():
                if key and val and key not in skip_fields:
                    kdes[key] = val

            # Parse input_lot_codes (comma-separated) if present
            input_lot_codes: list[str] = []
            input_lot_codes_raw = row.get("input_lot_codes")
            if input_lot_codes_raw:
                input_lot_codes = [c.strip() for c in input_lot_codes_raw.split(",") if c.strip()]
                if input_lot_codes:
                    kdes["input_lot_codes"] = input_lot_codes

            # Per-input quantity and unit (21 CFR 1.1350(a)(1)(iii)), aligned with
            # input_lot_codes. A list that cannot be attributed to its lots rejects
            # the row: guessing which quantity belongs to which lot would fabricate
            # a KDE. Rows without the columns still ingest (older templates) with a
            # warning for transformations.
            inputs, input_error, input_warning = _parse_input_quantities(row, input_lot_codes, row_cte)
            if input_error:
                parse_errors.append(f"Row {row_num}: {input_error}")
                continue
            if inputs:
                kdes["inputs"] = inputs
            if input_warning:
                kde_warnings.append(f"Row {row_num}: {input_warning}")

            # Auto-inject CTE-specific required KDEs from generic CSV columns
            _inject_required_kdes(kdes, row_cte, row, loc_name, raw_date)

            event = IngestEvent(
                cte_type=WebhookCTEType(row_cte),
                traceability_lot_code=lot_code,
                product_description=_first_present(row, _PRODUCT_COLUMNS),
                quantity=quantity,
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
                kde_warnings.append(f"Row {row_num}: Missing KDEs for {row_cte}: {', '.join(missing_kdes)}")
        except Exception as e:
            # Log the detail server-side; return a generic per-row message so
            # raw exception text (library internals) isn't echoed to callers.
            logger.warning("csv_row_parse_failed row=%s error=%s", row_num, str(e))
            parse_errors.append(f"Row {row_num}: could not be parsed (see server logs)")

    return events, parse_errors, kde_warnings


# ---------------------------------------------------------------------------
# Jev header-mapping suggestions (shared.jev.header_mapping)
#
# Optional: without TYPESAFE_API_KEY every helper below is a no-op and the
# route behaves exactly as before. With it, unrecognised column headers are
# sent to Jev once per upload, each answer is recorded as an advisory
# ``field_mapping_suggestion`` agent artifact for the review queue, and only
# with REGENGINE_JEV_APPLY_HEADER_MAPPINGS are AUTO_APPLY-band answers copied
# onto the rows. No failure in this block can fail the upload.
# ---------------------------------------------------------------------------


def _csv_headers_and_samples(text: str, sample_limit: int) -> tuple[list[str], dict[str, list[str]]]:
    """The header row and, when enabled, PII-redacted sample values for unrecognised columns."""
    reader = csv.DictReader(io.StringIO(text))
    headers = [header or "" for header in (reader.fieldnames or [])]
    if sample_limit <= 0 or not headers:
        return headers, {}
    unknown = unrecognized_headers(headers, _RECOGNIZED_COLUMNS)
    if not unknown:
        return headers, {}
    data_rows = (row for row in reader if not str(next(iter(row.values()), "") or "").startswith("#"))
    return headers, collect_sample_values(data_rows, unknown, sample_limit)


async def _suggest_header_mappings_for_upload(
    text: str, *, decider: Optional[JevDecider] = None, cte_type: Optional[str] = None
) -> HeaderMappingResult:
    """Ask Jev about the upload's unrecognised headers, off the event loop. Never raises.

    ``decider`` defaults to the process-wide one (what the route uses).
    ``scripts/jev_header_preview.py`` passes its own so operators can preview
    this exact path against a local file without running the service.
    ``cte_type`` is the canonical CTE declared for the whole file (the
    route's normalised ``cte_type`` form field), or ``None``; Jev sees it as
    ``file_cte_type`` in the state.
    """
    decider = decider if decider is not None else get_jev_decider()
    if not decider.enabled:
        return HeaderMappingResult(status="disabled", thresholds=decider.settings.thresholds)
    try:
        headers, samples = _csv_headers_and_samples(text, decider.settings.header_sample_values)
        if not headers:
            return HeaderMappingResult(status="no_headers", thresholds=decider.settings.thresholds)
        return await run_in_threadpool(
            suggest_header_mappings,
            headers,
            recognized=_RECOGNIZED_COLUMNS,
            samples=samples,
            decider=decider,
            precedence=_COLUMN_PRECEDENCE,
            cte_type=cte_type,
        )
    except Exception:  # noqa: BLE001 - a suggestion failure must never reject an upload.
        logger.exception("csv_header_mapping_failed")
        return HeaderMappingResult(status="error", thresholds=decider.settings.thresholds)


def _record_header_mapping_evidence(
    result: HeaderMappingResult,
    *,
    tenant_id: str,
    source_hash: str,
    ingestion_run_id: Optional[str],
) -> int:
    """Queue advisory ``field_mapping_suggestion`` artifacts for the agent bridge.

    The bridge persists them to ``fsma.agent_artifacts`` and appends a
    ledger receipt to the ingestion run, so the review queue and the export
    audit trail both see what Jev suggested and what code did with it.
    Returns the number of artifacts queued; failures are logged, not raised.

    This is synchronous psycopg I/O: the async route calls it through
    ``run_in_threadpool`` so the round-trips never block the event loop.
    """
    try:
        artifacts = build_field_mapping_artifacts(
            result, tenant_id=tenant_id, source_hash=source_hash, ingestion_run_id=ingestion_run_id
        )
    except ValueError as exc:
        logger.warning("csv_header_mapping_evidence_skipped reason=%s", exc)
        return 0
    if not artifacts:
        return 0
    session = SessionLocal()
    try:
        set_tenant_guc(session, str(tenant_id))
        for artifact in artifacts:
            enqueue_agent_artifact_task(session, artifact)
        session.commit()
    except Exception:  # noqa: BLE001 - evidence queueing is best-effort; the run itself is already retained.
        session.rollback()
        logger.exception(
            "csv_header_mapping_evidence_failed source_hash=%s ingestion_run_id=%s applied=%d",
            source_hash,
            ingestion_run_id,
            len(result.applied_mapping),
        )
        return 0
    finally:
        session.close()
    logger.info(
        "csv_header_mapping_evidence_queued artifacts=%d applied=%d ingestion_run_id=%s",
        len(artifacts),
        len(result.applied_mapping),
        ingestion_run_id,
    )
    return len(artifacts)


def _header_mapping_engine_result(
    result: HeaderMappingResult, artifacts_recorded: int
) -> Optional[HeaderMappingEngineResult]:
    """Response provenance for the suggestions; ``None`` when Jev is not configured."""
    if result.status == "disabled":
        return None
    evidence = result.evidence
    return HeaderMappingEngineResult(
        status=result.status,
        model=evidence.model if evidence else None,
        request_id=evidence.request_id if evidence else None,
        questions_version=_JEV_QUESTIONS_VERSION if evidence else None,
        apply_enabled=result.apply_enabled,
        auto_apply_confidence=result.thresholds.auto_apply,
        review_confidence=result.thresholds.review,
        artifacts_recorded=artifacts_recorded,
    )


@router.post(
    "/ingest/csv",
    response_model=CsvIngestResponse,
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
    tenant_id: Optional[str] = Form(None, description="Optional tenant assertion; must match the credential"),
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
    header_mapping = await _suggest_header_mappings_for_upload(text, cte_type=fallback_cte)
    if header_mapping.applied_mapping:
        logger.info(
            "csv_header_mappings_applied count=%d mapping=%s",
            len(header_mapping.applied_mapping),
            sorted(header_mapping.applied_mapping.items()),
        )
    events, parse_errors, kde_warnings = parse_csv_rows(
        text, fallback_cte, header_mapping=header_mapping.applied_mapping
    )

    if not events and parse_errors:
        raise HTTPException(status_code=400, detail={"message": "No valid rows found", "errors": parse_errors})
    if not events:
        raise HTTPException(status_code=400, detail="CSV contained no data rows")

    payload = WebhookPayload(source=source, events=events, tenant_id=tenant_id)
    # Receipt: the upload is retained verbatim as an ingestion run (file name,
    # SHA-256, size, every row counted) and each accepted event carries the
    # run id, so an export can point at the exact source file for any row.
    receipt = SourceFileReceipt(
        filename=file.filename or "upload.csv",
        raw_bytes=content,
        content_type=file.content_type,
        initiated_by=getattr(principal, "key_id", None),
        record_count=len(events) + len(parse_errors),
        parse_errors=list(parse_errors),
    )
    response = await ingest_events(
        payload,
        principal_tenant_id=tenant_id,
        x_regengine_api_key=x_regengine_api_key,
        source_file=receipt,
    )

    artifacts_recorded = 0
    if header_mapping.ok and header_mapping.suggestions:
        artifacts_recorded = await run_in_threadpool(
            _record_header_mapping_evidence,
            header_mapping,
            tenant_id=tenant_id,
            source_hash=receipt.sha256,
            ingestion_run_id=response.ingestion_run_id,
        )

    if parse_errors:
        from .webhook_models import EventResult

        for err in parse_errors:
            response.events.append(
                EventResult(
                    traceability_lot_code="", cte_type=fallback_cte or "unknown", status="rejected", errors=[err]
                )
            )
            response.rejected += 1
            response.total += 1

    if kde_warnings:
        logger.warning(
            "csv_ingest_kde_warnings: %d events with missing KDEs: %s", len(kde_warnings), "; ".join(kde_warnings[:5])
        )

    logger.info(
        "csv_ingest_complete: total=%d accepted=%d rejected=%d kde_warnings=%d",
        response.total,
        response.accepted,
        response.rejected,
        len(kde_warnings),
    )

    # #2892: return the declared model rather than a raw JSONResponse.
    # A JSONResponse bypasses FastAPI serialization entirely, so these two
    # fields went out on the wire but never appeared in the published
    # OpenAPI schema — generated SDKs dropped the only signal telling an
    # integrator which rows are missing required FSMA key data elements.
    return CsvIngestResponse(
        **response.model_dump(),
        kde_warnings=kde_warnings,
        kde_warning_count=len(kde_warnings),
        header_mapping_suggestions=[
            HeaderMappingSuggestionResult(
                source_header=suggestion.source_header,
                source_key=suggestion.source_key,
                canonical_field=suggestion.canonical_field,
                confidence=suggestion.confidence,
                band=suggestion.band.value,
                applied=suggestion.applied,
                blocked_reason=suggestion.blocked_reason,
            )
            for suggestion in header_mapping.suggestions
        ],
        header_mapping_engine=_header_mapping_engine_result(header_mapping, artifacts_recorded),
    )
