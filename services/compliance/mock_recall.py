#!/usr/bin/env python3
"""
FSMA 204 Mock Recall API Output Structure.

Provides mock recall simulation for testing and demonstration purposes.
Outputs the structure expected for FDA 24-hour recall response requirements.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger("mock-recall")


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
    supply_chain_depth: int = 0  # Number of hops from source


@dataclass
class MockRecallResult:
    """
    Mock recall API output structure.
    
    This structure matches FDA expectations for rapid traceability response.
    Per FSMA 204, facilities must be able to provide this information
    within 24 hours of FDA request.
    """
    lot_id: str
    product_description: Optional[str] = None
    recall_initiated_at: str = ""
    query_time_ms: float = 0
    
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


def simulate_mock_recall(
    lot_id: str,
    product_description: Optional[str] = None,
    simulate_delay_ms: float = 0,
) -> MockRecallResult:
    """
    Simulate a mock recall for demonstration purposes.
    
    This function generates sample data to demonstrate the recall
    response structure. In production, this would query the Neo4j
    graph for actual traceability data.
    
    Args:
        lot_id: Traceability Lot Code to trace
        product_description: Optional product description
        simulate_delay_ms: Optional delay to simulate query time
        
    Returns:
        MockRecallResult with simulated affected facilities
    """
    start_time = time.time()
    
    logger.info("mock_recall_initiated", lot_id=lot_id)
    
    if simulate_delay_ms > 0:
        time.sleep(simulate_delay_ms / 1000)
    
    # Generate sample affected facilities
    affected_facilities = [
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
    
    # Calculate impact summary
    total_quantity = sum(f.quantity_received or 0 for f in affected_facilities)
    dates = [f.receiving_date for f in affected_facilities if f.receiving_date]
    
    impact_summary = RecallImpactSummary(
        total_facilities_affected=len(affected_facilities),
        total_quantity_impacted=total_quantity,
        unit_of_measure="cases",
        earliest_event_date=min(dates) if dates else None,
        latest_event_date=max(dates) if dates else None,
        supply_chain_depth=3,  # Farm -> Packer -> Distributor -> Retailer/Restaurant
    )
    
    query_time = (time.time() - start_time) * 1000
    
    result = MockRecallResult(
        lot_id=lot_id,
        product_description=product_description or "Unknown Product",
        recall_initiated_at=datetime.utcnow().isoformat() + "Z",
        query_time_ms=query_time,
        impact_summary=impact_summary,
        affected_facilities=affected_facilities,
        trace_path=[
            "Fresh Farms (FARM)",
            "Sunshine Packing (PROCESSOR)",
            "Regional Distribution Center A (DISTRIBUTOR)",
            "Metro Grocery Store #42 (RETAILER)",
            "Fresh Foods Restaurant (RESTAURANT)",
        ],
        warnings=[],
    )
    
    logger.info(
        "mock_recall_completed",
        lot_id=lot_id,
        facilities_affected=len(affected_facilities),
        total_quantity=total_quantity,
        query_time_ms=round(query_time, 2),
    )
    
    return result
