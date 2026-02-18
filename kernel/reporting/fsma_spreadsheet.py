#!/usr/bin/env python3
"""
FSMA 204 FDA Spreadsheet Generator.

Generates FDA-compliant CSV spreadsheets for traceability audits.
Maps graph data to FDA-required columns per FSMA 204 specification.
"""

from __future__ import annotations

import csv
import io
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


@dataclass
class FDASpreadsheetRow:
    """
    FDA spreadsheet row format per FSMA 204 requirements.
    
    These columns align with FDA's expected format for traceability records.
    """
    traceability_lot_code: str
    product_description: Optional[str] = None
    quantity: Optional[float] = None
    unit_of_measure: Optional[str] = None
    event_type: Optional[str] = None
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    ship_from_gln: Optional[str] = None
    ship_from_name: Optional[str] = None
    ship_from_address: Optional[str] = None
    ship_to_gln: Optional[str] = None
    ship_to_name: Optional[str] = None
    ship_to_address: Optional[str] = None
    tlc_source_gln: Optional[str] = None
    tlc_source_fda_reg: Optional[str] = None
    document_id: Optional[str] = None
    confidence_score: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for CSV writing."""
        return {
            "Traceability Lot Code (TLC)": self.traceability_lot_code,
            "Product Description": self.product_description or "",
            "Quantity": self.quantity if self.quantity is not None else "",
            "Unit of Measure": self.unit_of_measure or "",
            "Event Type": self.event_type or "",
            "Event Date": self.event_date or "",
            "Event Time": self.event_time or "",
            "Ship From GLN": self.ship_from_gln or "",
            "Ship From Name": self.ship_from_name or "",
            "Ship From Address": self.ship_from_address or "",
            "Ship To GLN": self.ship_to_gln or "",
            "Ship To Name": self.ship_to_name or "",
            "Ship To Address": self.ship_to_address or "",
            "TLC Source GLN": self.tlc_source_gln or "",
            "TLC Source FDA Reg": self.tlc_source_fda_reg or "",
            "Source Document ID": self.document_id or "",
            "Extraction Confidence": f"{self.confidence_score:.2%}" if self.confidence_score else "",
        }


# FDA spreadsheet column headers
FDA_SPREADSHEET_COLUMNS = [
    "Traceability Lot Code (TLC)",
    "Product Description",
    "Quantity",
    "Unit of Measure",
    "Event Type",
    "Event Date",
    "Event Time",
    "Ship From GLN",
    "Ship From Name",
    "Ship From Address",
    "Ship To GLN",
    "Ship To Name",
    "Ship To Address",
    "TLC Source GLN",
    "TLC Source FDA Reg",
    "Source Document ID",
    "Extraction Confidence",
]


def generate_fda_spreadsheet(
    tlc: str,
    start_date: str,
    end_date: str,
    events: Optional[List[Dict[str, Any]]] = None,
    facilities: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Generate FDA-compliant CSV spreadsheet for a traceability query.
    
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
            # Parse KDEs
            kdes = event.get("kdes", {})
            
            # Filter by date if provided
            event_date = kdes.get("event_date") or event.get("event_date")
            if event_date and start_date and end_date:
                if not (start_date <= event_date <= end_date):
                    continue
            
            row = FDASpreadsheetRow(
                traceability_lot_code=kdes.get("traceability_lot_code") or tlc,
                product_description=kdes.get("product_description"),
                quantity=kdes.get("quantity"),
                unit_of_measure=kdes.get("unit_of_measure"),
                event_type=event.get("type") or event.get("event_type"),
                event_date=event_date,
                event_time=kdes.get("event_time"),
                ship_from_gln=_extract_gln(kdes.get("ship_from_gln")),
                ship_to_gln=_extract_gln(kdes.get("ship_to_gln")),
                tlc_source_gln=_extract_gln(kdes.get("tlc_source_gln")),
                tlc_source_fda_reg=_extract_fda_reg(kdes.get("tlc_source_fda_reg")),
                document_id=event.get("document_id"),
                confidence_score=event.get("confidence"),
            )
            rows.append(row)
    
    # Add facility names if available
    if facilities:
        facility_lookup = {f.get("gln"): f for f in facilities if f.get("gln")}
        for row in rows:
            if row.ship_from_gln and row.ship_from_gln in facility_lookup:
                fac = facility_lookup[row.ship_from_gln]
                row.ship_from_name = fac.get("name")
                row.ship_from_address = fac.get("address")
            if row.ship_to_gln and row.ship_to_gln in facility_lookup:
                fac = facility_lookup[row.ship_to_gln]
                row.ship_to_name = fac.get("name")
                row.ship_to_address = fac.get("address")
    
    # If no events, create a placeholder row
    if not rows:
        rows.append(FDASpreadsheetRow(
            traceability_lot_code=tlc,
            event_type="NO_EVENTS_FOUND",
            event_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        ))
    
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
