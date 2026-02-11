#!/usr/bin/env python3
"""
FSMA 204 Recall Engine — Live + Mock Fallback.

Attempts to query the graph service's recall API for live traceability data.
Falls back to mock data for testing/demo when graph service is unavailable.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger("recall-engine")

# Graph service URL for live recall queries
GRAPH_SERVICE_URL = os.environ.get(
    "GRAPH_SERVICE_URL", "http://graph-api:8000"
)
# Internal service API key (no auth required for internal calls in Docker network)
GRAPH_API_KEY = os.environ.get("GRAPH_INTERNAL_API_KEY", "")


@dataclass
class AffectedFacility:
    """A facility affected by the recall."""
    gln: Optional[str] = None
    fda_registration: Optional[str] = None
    name: str = ""
    address: Optional[str] = None
    facility_type: str = ""  # DISTRIBUTOR, RETAILER, RESTAURANT
    quantity_received: Optional[float] = None
    unit_of_measure: Optional[str] = None
    receiving_date: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None


@dataclass
class RecallImpactSummary:
    """Summary of recall impact."""
    total_facilities_affected: int = 0
    total_quantity_impacted: float = 0
    unit_of_measure: str = ""
    earliest_event_date: Optional[str] = None
    latest_event_date: Optional[str] = None
    supply_chain_depth: int = 0


@dataclass
class MockRecallResult:
    """
    Recall result structure matching FDA 24-hour response requirements.

    Per FSMA 204, facilities must provide traceability information
    within 24 hours of FDA request.
    """
    lot_id: str
    product_description: Optional[str] = None
    recall_initiated_at: str = ""
    query_time_ms: float = 0
    data_source: str = "mock"  # "live" or "mock"

    # Impact summary
    impact_summary: RecallImpactSummary = field(default_factory=RecallImpactSummary)

    # Affected downstream facilities
    affected_facilities: List[AffectedFacility] = field(default_factory=list)

    # Trace path for audit
    trace_path: List[str] = field(default_factory=list)

    # Warnings or data quality issues
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "lot_id": self.lot_id,
            "product_description": self.product_description,
            "recall_initiated_at": self.recall_initiated_at,
            "query_time_ms": round(self.query_time_ms, 2),
            "data_source": self.data_source,
            "impact_summary": {
                "total_facilities_affected": self.impact_summary.total_facilities_affected,
                "total_quantity_impacted": self.impact_summary.total_quantity_impacted,
                "unit_of_measure": self.impact_summary.unit_of_measure,
                "earliest_event_date": self.impact_summary.earliest_event_date,
                "latest_event_date": self.impact_summary.latest_event_date,
                "supply_chain_depth": self.impact_summary.supply_chain_depth,
            },
            "affected_facilities": [
                {
                    "gln": f.gln,
                    "fda_registration": f.fda_registration,
                    "name": f.name,
                    "address": f.address,
                    "facility_type": f.facility_type,
                    "quantity_received": f.quantity_received,
                    "unit_of_measure": f.unit_of_measure,
                    "receiving_date": f.receiving_date,
                    "contact_name": f.contact_name,
                    "contact_phone": f.contact_phone,
                }
                for f in self.affected_facilities
            ],
            "trace_path": self.trace_path,
            "warnings": self.warnings,
        }


def _try_live_recall(lot_id: str) -> Optional[Dict[str, Any]]:
    """Attempt to query graph service recall API for live data."""
    try:
        import httpx
    except ImportError:
        logger.debug("httpx not installed, skipping live recall")
        return None

    try:
        headers = {"Content-Type": "application/json"}
        if GRAPH_API_KEY:
            headers["X-API-Key"] = GRAPH_API_KEY

        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{GRAPH_SERVICE_URL}/v1/fsma/recall/drill",
                json={
                    "type": "forward_trace",
                    "target_tlc": lot_id,
                    "severity": "class_ii",
                    "reason": "compliance_recall_query",
                },
                headers=headers,
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(
                    "live_recall_failed",
                    status=response.status_code,
                    body=response.text[:200],
                )
                return None
    except Exception as e:
        logger.info("live_recall_unavailable", error=str(e))
        return None


def _build_from_live(lot_id: str, live_data: Dict[str, Any], query_time: float) -> MockRecallResult:
    """Build a MockRecallResult from live graph service response."""
    facilities = []
    for f in live_data.get("affected_facilities", []):
        facilities.append(AffectedFacility(
            gln=f.get("gln"),
            fda_registration=f.get("fda_registration"),
            name=f.get("name", ""),
            address=f.get("address"),
            facility_type=f.get("facility_type", ""),
            quantity_received=f.get("quantity_received"),
            unit_of_measure=f.get("unit_of_measure"),
            receiving_date=f.get("receiving_date"),
            contact_name=f.get("contact_name"),
            contact_phone=f.get("contact_phone"),
        ))

    metrics = live_data.get("metrics", {})
    return MockRecallResult(
        lot_id=lot_id,
        product_description=live_data.get("product_description"),
        recall_initiated_at=live_data.get("initiated_at", datetime.now(timezone.utc).isoformat()),
        query_time_ms=query_time,
        data_source="live",
        impact_summary=RecallImpactSummary(
            total_facilities_affected=len(facilities),
            total_quantity_impacted=metrics.get("total_quantity", 0),
            unit_of_measure=metrics.get("unit_of_measure", "cases"),
            earliest_event_date=metrics.get("earliest_event"),
            latest_event_date=metrics.get("latest_event"),
            supply_chain_depth=metrics.get("max_depth", 0),
        ),
        affected_facilities=facilities,
        trace_path=live_data.get("trace_path", []),
        warnings=live_data.get("warnings", []),
    )


def _build_mock(lot_id: str, product_description: Optional[str], query_time: float) -> MockRecallResult:
    """Build mock recall data for demo/testing."""
    facilities = [
        AffectedFacility(
            gln="1111111111111",
            name="Regional Distribution Center A",
            address="100 Warehouse Blvd, Chicago, IL",
            facility_type="DISTRIBUTOR",
            quantity_received=200,
            unit_of_measure="cases",
            receiving_date="2025-11-06",
            contact_name="Operations Manager",
            contact_phone="555-111-1111",
        ),
        AffectedFacility(
            gln="2222222222222",
            name="Metro Grocery Store #42",
            address="200 Main St, Chicago, IL",
            facility_type="RETAILER",
            quantity_received=50,
            unit_of_measure="cases",
            receiving_date="2025-11-07",
            contact_name="Store Manager",
            contact_phone="555-222-2222",
        ),
        AffectedFacility(
            gln="3333333333333",
            name="Fresh Foods Restaurant",
            address="300 Downtown Ave, Chicago, IL",
            facility_type="RESTAURANT",
            quantity_received=10,
            unit_of_measure="cases",
            receiving_date="2025-11-08",
            contact_name="Chef",
            contact_phone="555-333-3333",
        ),
    ]

    total_quantity = sum(f.quantity_received or 0 for f in facilities)
    dates = [f.receiving_date for f in facilities if f.receiving_date]

    return MockRecallResult(
        lot_id=lot_id,
        product_description=product_description or "Unknown Product",
        recall_initiated_at=datetime.now(timezone.utc).isoformat(),
        query_time_ms=query_time,
        data_source="mock",
        impact_summary=RecallImpactSummary(
            total_facilities_affected=len(facilities),
            total_quantity_impacted=total_quantity,
            unit_of_measure="cases",
            earliest_event_date=min(dates) if dates else None,
            latest_event_date=max(dates) if dates else None,
            supply_chain_depth=3,
        ),
        affected_facilities=facilities,
        trace_path=[
            "Fresh Farms (FARM)",
            "Sunshine Packing (PROCESSOR)",
            "Regional Distribution Center A (DISTRIBUTOR)",
            "Metro Grocery Store #42 (RETAILER)",
            "Fresh Foods Restaurant (RESTAURANT)",
        ],
        warnings=["Using mock data — graph service unavailable"],
    )


def simulate_mock_recall(
    lot_id: str,
    product_description: Optional[str] = None,
    simulate_delay_ms: float = 0,
) -> MockRecallResult:
    """
    Execute a recall trace — live graph query with mock fallback.

    Attempts to query the graph service's recall/drill API first.
    Falls back to mock data if the graph service is unavailable.

    Args:
        lot_id: Traceability Lot Code to trace
        product_description: Optional product description
        simulate_delay_ms: Optional delay to simulate query time

    Returns:
        MockRecallResult with live or mock facility data
    """
    start_time = time.time()

    logger.info("recall_initiated", lot_id=lot_id)

    if simulate_delay_ms > 0:
        time.sleep(simulate_delay_ms / 1000)

    # Try live recall first
    live_data = _try_live_recall(lot_id)
    query_time = (time.time() - start_time) * 1000

    if live_data:
        result = _build_from_live(lot_id, live_data, query_time)
        logger.info(
            "recall_completed_live",
            lot_id=lot_id,
            facilities_affected=result.impact_summary.total_facilities_affected,
            query_time_ms=round(query_time, 2),
        )
    else:
        result = _build_mock(lot_id, product_description, query_time)
        logger.info(
            "recall_completed_mock",
            lot_id=lot_id,
            facilities_affected=result.impact_summary.total_facilities_affected,
            query_time_ms=round(query_time, 2),
        )

    return result
