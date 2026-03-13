"""
FSMA 204 FDA Sortable Spreadsheet Generator.

Produces a CSV matching the FDA 24-hour recall response format with all
mandatory Key Data Elements (KDEs) and Critical Tracking Event (CTE) columns
per FSMA Section 204 requirements.

Columns include: TLC, Product Description, Quantity, Unit of Measure,
Event Type (CTE), Event Date/Time, Origin/Destination GLN + Name + Address,
TLC Source GLN, TLC Source FDA Registration, Reference Document Type/Number,
named KDE date fields, Temperature, Carrier, Immediate Previous Source,
and overflow Additional KDEs as JSON.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any

# Mandatory FDA 204 spreadsheet columns in required sort order
FDA_COLUMNS = [
    "event_type",
    "event_date",
    "event_time",
    "traceability_lot_code",
    "product_description",
    "quantity",
    "unit_of_measure",
    "origin_gln",
    "origin_name",
    "origin_address",
    "destination_gln",
    "destination_name",
    "destination_address",
    "tlc_source_gln",
    "tlc_source_fda_reg",
    "reference_document_type",
    "reference_document_number",
    "harvest_date",
    "cooling_date",
    "pack_date",
    "ship_date",
    "receive_date",
    "transformation_date",
    "landing_date",
    "temperature",
    "carrier",
    "immediate_previous_source",
    "additional_kdes_json",
    "risk_flag",
]

# Friendly header labels for the CSV (1:1 with FDA_COLUMNS)
FDA_HEADERS = [
    "Event Type (CTE)",
    "Event Date",
    "Event Time",
    "Traceability Lot Code (TLC)",
    "Product Description",
    "Quantity",
    "Unit of Measure",
    "Origin GLN",
    "Origin Facility Name",
    "Origin Address",
    "Destination GLN",
    "Destination Facility Name",
    "Destination Address",
    "TLC Source GLN",
    "TLC Source FDA Registration",
    "Reference Document Type",
    "Reference Document Number",
    "Harvest Date",
    "Cooling Date",
    "Pack Date",
    "Ship Date",
    "Receive Date",
    "Transformation Date",
    "Landing Date",
    "Temperature",
    "Carrier",
    "Immediate Previous Source",
    "Additional KDEs (JSON)",
    "Risk Flag",
]

# Named KDE keys that get their own dedicated columns
_NAMED_KDE_KEYS = {
    "harvest_date", "cooling_date", "pack_date", "ship_date",
    "receive_date", "transformation_date", "landing_date",
    "temperature", "carrier", "immediate_previous_source",
}

# Keys already mapped into top-level columns (skip when building extra KDE JSON)
_SKIP_KDE_KEYS = _NAMED_KDE_KEYS | {
    "traceability_lot_code", "product_description", "quantity",
    "unit_of_measure", "event_date", "event_time", "cte_type",
    "ship_from_gln", "ship_to_gln", "ship_from_location",
    "ship_to_location", "tlc_source_gln", "tlc_source_fda_reg",
    "reference_document_number", "reference_document_type",
    "location_identifier",
}


def _parse_timestamp(raw: str) -> tuple[str, str]:
    """Split an ISO timestamp into (date, time)."""
    if not raw:
        return ("", "")
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return (dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S"))
    except (ValueError, AttributeError):
        return (str(raw)[:10], "")


def _normalise_event(event: dict[str, Any]) -> dict[str, str]:
    """Map a graph-service event dict to FDA column values."""

    kdes = event.get("kdes", {})
    event_date_raw = kdes.get("event_date") or event.get("event_date") or ""
    event_date, event_time = _parse_timestamp(event_date_raw)
    if kdes.get("event_time"):
        event_time = kdes["event_time"]

    # Collect named KDE values
    kde_vals = {k: str(kdes.get(k, "")) for k in _NAMED_KDE_KEYS if kdes.get(k)}

    # Extra KDEs -> JSON
    extra = {k: v for k, v in kdes.items() if k not in _SKIP_KDE_KEYS and v}
    extra_json = json.dumps(extra, default=str) if extra else ""

    return {
        "event_type": (event.get("type") or event.get("event_type") or "").upper(),
        "event_date": event_date,
        "event_time": event_time,
        "traceability_lot_code": event.get("tlc") or event.get("traceability_lot_code") or "",
        "product_description": event.get("product_description") or kdes.get("product_description") or "",
        "quantity": str(event.get("quantity") or kdes.get("quantity") or ""),
        "unit_of_measure": event.get("uom") or event.get("unit_of_measure") or kdes.get("unit_of_measure") or "",
        "origin_gln": event.get("facility_gln") or kdes.get("ship_from_gln") or "",
        "origin_name": event.get("facility_name") or kdes.get("ship_from_location") or "",
        "origin_address": event.get("facility_address") or event.get("ship_from_address") or "",
        "destination_gln": event.get("dest_gln") or kdes.get("ship_to_gln") or "",
        "destination_name": event.get("dest_name") or kdes.get("ship_to_location") or "",
        "destination_address": event.get("dest_address") or event.get("ship_to_address") or "",
        "tlc_source_gln": kdes.get("tlc_source_gln") or "",
        "tlc_source_fda_reg": kdes.get("tlc_source_fda_reg") or "",
        "reference_document_type": kdes.get("reference_document_type") or event.get("document_type") or "",
        "reference_document_number": kdes.get("reference_document_number") or event.get("ref_doc") or "",
        "harvest_date": kde_vals.get("harvest_date", ""),
        "cooling_date": kde_vals.get("cooling_date", ""),
        "pack_date": kde_vals.get("pack_date", ""),
        "ship_date": kde_vals.get("ship_date", ""),
        "receive_date": kde_vals.get("receive_date", ""),
        "transformation_date": kde_vals.get("transformation_date", ""),
        "landing_date": kde_vals.get("landing_date", ""),
        "temperature": kde_vals.get("temperature", ""),
        "carrier": kde_vals.get("carrier", ""),
        "immediate_previous_source": kde_vals.get("immediate_previous_source", ""),
        "additional_kdes_json": extra_json,
        "risk_flag": event.get("risk_flag") or "",
    }


def generate_fda_csv(
    events: list[dict[str, Any]],
    *,
    start_date: str = "",
    end_date: str = "",
    requesting_entity: str = "",
) -> str:
    """Generate a complete FDA 204 Sortable Spreadsheet as a CSV string.

    Parameters
    ----------
    events:
        List of event dicts (matching ``query_events_by_range()`` output).
    start_date:
        Start of the reporting window (ISO date).
    end_date:
        End of the reporting window (ISO date).
    requesting_entity:
        Name of the requesting entity (e.g. "FDA District Office").

    Returns
    -------
    str
        Complete CSV content ready for streaming to the client.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)

    # --- Metadata header rows ---
    writer.writerow(["FSMA Section 204 - Sortable Spreadsheet"])
    writer.writerow(["Generated", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")])
    if start_date or end_date:
        writer.writerow(["Date Range", f"{start_date} to {end_date}"])
    if requesting_entity:
        writer.writerow(["Requesting Entity", requesting_entity])
    writer.writerow(["Record Count", str(len(events))])
    writer.writerow([])  # blank separator

    # --- Column headers ---
    writer.writerow(FDA_HEADERS)

    # --- Data rows (sorted by event_date then event_time) ---
    normalised = [_normalise_event(e) for e in events]
    normalised.sort(key=lambda r: (r.get("event_date") or "", r.get("event_time") or ""))

    for row in normalised:
        writer.writerow([row[col] for col in FDA_COLUMNS])

    return buf.getvalue()
