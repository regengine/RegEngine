#!/usr/bin/env python3
"""
FSMA 204 FDA Spreadsheet Generator.

Generates FDA-compliant CSV spreadsheets for traceability audits containing
all mandatory FSMA 204 columns: TLC, Quantity, Unit of Measure, GLN for
origin/destination, Product Description, CTEs (Creation, Transformation,
Shipping, Receiving), KDEs, Event Timestamps, and Reference Documents.

Maps graph data to FDA-required columns per FSMA 204 specification.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

# Add project root for shared imports
_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from shared.schemas import FSMALocation

logger = structlog.get_logger("fsma-spreadsheet")


# ---------------------------------------------------------------------------
# Valid CTE types per FSMA 204
# ---------------------------------------------------------------------------
VALID_CTE_TYPES = {"CREATION", "TRANSFORMATION", "SHIPPING", "RECEIVING", "INITIAL_PACKING"}


@dataclass
class FDASpreadsheetRow:
    """
    FDA spreadsheet row format per FSMA 204 requirements.

    Covers every mandatory column the FDA expects in a 24-hour recall
    response, including CTEs, KDEs, GLNs, reference documents, and
    event timestamps.
    """

    # --- Core identifiers ---
    traceability_lot_code: str
    product_description: Optional[str] = None

    # --- Quantity ---
    quantity: Optional[float] = None
    unit_of_measure: Optional[str] = None

    # --- CTE (Critical Tracking Event) ---
    event_type: Optional[str] = None           # CREATION | TRANSFORMATION | SHIPPING | RECEIVING
    event_date: Optional[str] = None           # YYYY-MM-DD
    event_time: Optional[str] = None           # HH:MM:SS or HH:MM:SSZ

    # --- Origin GLN ---
    origin_gln: Optional[str] = None
    origin_name: Optional[str] = None
    origin_address: Optional[str] = None

    # --- Destination GLN ---
    destination_gln: Optional[str] = None
    destination_name: Optional[str] = None
    destination_address: Optional[str] = None

    # --- TLC Source ---
    tlc_source_gln: Optional[str] = None
    tlc_source_fda_reg: Optional[str] = None

    # --- Reference Document ---
    reference_document_type: Optional[str] = None   # BOL, INVOICE, ASN, PRODUCTION_LOG, etc.
    reference_document_number: Optional[str] = None

    # --- Key Data Elements (KDEs) ---
    kde_harvest_date: Optional[str] = None
    kde_cooling_date: Optional[str] = None
    kde_pack_date: Optional[str] = None
    kde_ship_date: Optional[str] = None
    kde_receive_date: Optional[str] = None
    kde_transformation_date: Optional[str] = None
    kde_landing_date: Optional[str] = None
    kde_temperature: Optional[str] = None
    kde_carrier: Optional[str] = None
    kde_immediate_previous_source: Optional[str] = None
    additional_kdes_json: Optional[str] = None

    # --- Provenance ---
    source_document_id: Optional[str] = None
    extraction_confidence: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for CSV writing."""
        return {
            "Traceability Lot Code (TLC)": self.traceability_lot_code,
            "Product Description": self.product_description or "",
            "Quantity": self.quantity if self.quantity is not None else "",
            "Unit of Measure": self.unit_of_measure or "",
            "Event Type (CTE)": self.event_type or "",
            "Event Date": self.event_date or "",
            "Event Time": self.event_time or "",
            "Origin GLN": self.origin_gln or "",
            "Origin Name": self.origin_name or "",
            "Origin Address": self.origin_address or "",
            "Destination GLN": self.destination_gln or "",
            "Destination Name": self.destination_name or "",
            "Destination Address": self.destination_address or "",
            "TLC Source GLN": self.tlc_source_gln or "",
            "TLC Source FDA Registration": self.tlc_source_fda_reg or "",
            "Reference Document Type": self.reference_document_type or "",
            "Reference Document Number": self.reference_document_number or "",
            "Harvest Date": self.kde_harvest_date or "",
            "Cooling Date": self.kde_cooling_date or "",
            "Pack Date": self.kde_pack_date or "",
            "Ship Date": self.kde_ship_date or "",
            "Receive Date": self.kde_receive_date or "",
            "Transformation Date": self.kde_transformation_date or "",
            "Landing Date": self.kde_landing_date or "",
            "Temperature": self.kde_temperature or "",
            "Carrier": self.kde_carrier or "",
            "Immediate Previous Source": self.kde_immediate_previous_source or "",
            "Additional KDEs (JSON)": self.additional_kdes_json or "",
            "Source Document ID": self.source_document_id or "",
            "Extraction Confidence": (
                f"{self.extraction_confidence:.2%}" if self.extraction_confidence is not None else ""
            ),
        }


# FDA spreadsheet column headers — full FSMA 204 specification
FDA_SPREADSHEET_COLUMNS = [
    "Traceability Lot Code (TLC)",
    "Product Description",
    "Quantity",
    "Unit of Measure",
    "Event Type (CTE)",
    "Event Date",
    "Event Time",
    "Origin GLN",
    "Origin Name",
    "Origin Address",
    "Destination GLN",
    "Destination Name",
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
    "Source Document ID",
    "Extraction Confidence",
]

# Named KDE keys that map to their own dedicated columns
_NAMED_KDE_KEYS = {
    "harvest_date", "cooling_date", "pack_date", "ship_date",
    "receive_date", "transformation_date", "landing_date",
    "temperature", "carrier", "immediate_previous_source",
}


def _parse_event_timestamp(raw: Optional[str]) -> tuple:
    """Split an ISO timestamp into (date, time) strings."""
    if not raw:
        return ("", "")
    try:
        ts = str(raw)
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S"))
    except (ValueError, AttributeError):
        return (str(raw)[:10], "")


def _build_row_from_event(
    event: Dict[str, Any],
    default_tlc: str,
    start_date: str,
    end_date: str,
) -> Optional[FDASpreadsheetRow]:
    """Build a single FDA row from a raw event dict, returning None if filtered out."""
    kdes = event.get("kdes", {})

    # Resolve event date from multiple possible locations
    event_date_raw = (
        kdes.get("event_date")
        or event.get("event_date")
        or event.get("event_timestamp")
        or event.get("date")
    )
    event_date, event_time = _parse_event_timestamp(event_date_raw)

    # If no parsed date but raw value exists, try direct string
    if not event_date and event_date_raw:
        event_date = str(event_date_raw)[:10]

    # Use explicit event_time from KDEs if available
    if kdes.get("event_time"):
        event_time = kdes["event_time"]

    # Apply date range filter
    if event_date and start_date and end_date:
        if not (start_date <= event_date <= end_date):
            return None

    # Resolve event type (CTE)
    event_type = (
        event.get("type")
        or event.get("event_type")
        or event.get("cte_type")
        or kdes.get("cte_type")
        or ""
    )
    if isinstance(event_type, str):
        event_type = event_type.upper()

    # Collect named KDE values
    kde_values = {k: str(kdes.get(k, "")) for k in _NAMED_KDE_KEYS if kdes.get(k)}

    # Remaining KDEs not captured in named columns
    skip_keys = _NAMED_KDE_KEYS | {
        "traceability_lot_code", "product_description", "quantity",
        "unit_of_measure", "event_date", "event_time", "cte_type",
        "ship_from_gln", "ship_to_gln", "ship_from_location",
        "ship_to_location", "tlc_source_gln", "tlc_source_fda_reg",
        "reference_document_number", "reference_document_type",
        "location_identifier",
    }
    extra_kdes = {k: v for k, v in kdes.items() if k not in skip_keys and v}
    additional_json = json.dumps(extra_kdes, default=str) if extra_kdes else ""

    return FDASpreadsheetRow(
        traceability_lot_code=kdes.get("traceability_lot_code") or event.get("tlc") or default_tlc,
        product_description=kdes.get("product_description") or event.get("product_description"),
        quantity=kdes.get("quantity") or event.get("quantity"),
        unit_of_measure=kdes.get("unit_of_measure") or event.get("uom") or event.get("unit_of_measure"),
        event_type=event_type,
        event_date=event_date,
        event_time=event_time,
        origin_gln=_extract_gln(kdes.get("ship_from_gln") or event.get("facility_gln")),
        origin_name=kdes.get("ship_from_location") or event.get("facility_name"),
        destination_gln=_extract_gln(kdes.get("ship_to_gln") or event.get("dest_gln")),
        destination_name=kdes.get("ship_to_location") or event.get("dest_name"),
        tlc_source_gln=_extract_gln(kdes.get("tlc_source_gln")),
        tlc_source_fda_reg=_extract_fda_reg(kdes.get("tlc_source_fda_reg")),
        reference_document_type=(
            kdes.get("reference_document_type")
            or event.get("document_type")
            or event.get("source_type")
        ),
        reference_document_number=(
            kdes.get("reference_document_number")
            or event.get("ref_doc")
        ),
        kde_harvest_date=kde_values.get("harvest_date"),
        kde_cooling_date=kde_values.get("cooling_date"),
        kde_pack_date=kde_values.get("pack_date"),
        kde_ship_date=kde_values.get("ship_date"),
        kde_receive_date=kde_values.get("receive_date"),
        kde_transformation_date=kde_values.get("transformation_date"),
        kde_landing_date=kde_values.get("landing_date"),
        kde_temperature=kde_values.get("temperature"),
        kde_carrier=kde_values.get("carrier"),
        kde_immediate_previous_source=kde_values.get("immediate_previous_source"),
        additional_kdes_json=additional_json,
        source_document_id=event.get("document_id") or event.get("source"),
        extraction_confidence=event.get("confidence"),
    )


def generate_fda_spreadsheet(
    tlc: str,
    start_date: str,
    end_date: str,
    events: Optional[List[Dict[str, Any]]] = None,
    facilities: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Generate FDA-compliant CSV spreadsheet for a traceability query.

    The output contains every mandatory FSMA 204 column:
    - TLC, Product Description, Quantity, Unit of Measure
    - Event Type (CTE): Creation, Transformation, Shipping, Receiving
    - Event Date/Time
    - Origin/Destination GLN, Name, Address
    - TLC Source GLN and FDA Registration
    - Reference Document Type and Number
    - All named KDEs (harvest, cooling, pack, ship, receive, transformation,
      landing dates; temperature; carrier; immediate previous source)
    - Additional KDEs as JSON
    - Source Document ID and Extraction Confidence

    Args:
        tlc: Traceability Lot Code being traced
        start_date: Start date filter (YYYY-MM-DD)
        end_date: End date filter (YYYY-MM-DD)
        events: List of trace events from graph query
        facilities: List of facilities from graph query

    Returns:
        CSV content as string
    """
    logger.info(
        "generating_fda_spreadsheet",
        tlc=tlc,
        start_date=start_date,
        end_date=end_date,
        event_count=len(events) if events else 0,
    )

    rows: List[FDASpreadsheetRow] = []

    # Convert events to spreadsheet rows
    if events:
        for event in events:
            row = _build_row_from_event(event, default_tlc=tlc, start_date=start_date, end_date=end_date)
            if row is not None:
                rows.append(row)

    # Enrich rows with facility names/addresses if available
    if facilities:
        facility_lookup = {f.get("gln"): f for f in facilities if f.get("gln")}
        for row in rows:
            if row.origin_gln and row.origin_gln in facility_lookup:
                fac = facility_lookup[row.origin_gln]
                row.origin_name = row.origin_name or fac.get("name")
                row.origin_address = row.origin_address or fac.get("address")
            if row.destination_gln and row.destination_gln in facility_lookup:
                fac = facility_lookup[row.destination_gln]
                row.destination_name = row.destination_name or fac.get("name")
                row.destination_address = row.destination_address or fac.get("address")

    # If no events matched, create a single informational row
    if not rows:
        rows.append(FDASpreadsheetRow(
            traceability_lot_code=tlc,
            event_type="NO_EVENTS_FOUND",
            event_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            event_time=datetime.now(timezone.utc).strftime("%H:%M:%S"),
        ))

    # Sort rows by event_date then event_time for FDA-required sortability
    rows.sort(key=lambda r: (r.event_date or "", r.event_time or ""))

    # Generate CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FDA_SPREADSHEET_COLUMNS)
    writer.writeheader()

    for row in rows:
        writer.writerow(row.to_dict())

    csv_content = output.getvalue()

    logger.info(
        "fda_spreadsheet_generated",
        tlc=tlc,
        row_count=len(rows),
        size_bytes=len(csv_content),
    )

    return csv_content


def _extract_gln(value: Optional[str]) -> Optional[str]:
    """Extract GLN from URN format if present."""
    if not value:
        return None
    if value.startswith("urn:gln:"):
        return value.replace("urn:gln:", "")
    return value


def _extract_fda_reg(value: Optional[str]) -> Optional[str]:
    """Extract FDA registration from URN format if present."""
    if not value:
        return None
    if value.startswith("fda:"):
        return value.replace("fda:", "")
    return value


def generate_spreadsheet_from_graph(
    client: Any,
    tlc: str,
    start_date: str,
    end_date: str,
) -> str:
    """
    Generate FDA spreadsheet by querying the Neo4j graph.

    Args:
        client: Neo4j client instance
        tlc: Traceability Lot Code to trace
        start_date: Start date filter (YYYY-MM-DD)
        end_date: End date filter (YYYY-MM-DD)

    Returns:
        CSV content as string
    """
    # Query graph for events and facilities
    events = []
    facilities = []

    try:
        from services.graph.app.fsma_utils import trace_forward

        trace_result = trace_forward(client, tlc, max_depth=20)
        events = trace_result.events
        facilities = trace_result.facilities
    except ImportError:
        logger.warning("fsma_utils_not_available")
    except Exception as e:
        logger.error("graph_query_failed", error=str(e))

    return generate_fda_spreadsheet(
        tlc=tlc,
        start_date=start_date,
        end_date=end_date,
        events=events,
        facilities=facilities,
    )
