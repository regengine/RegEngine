"""
FSMA 204 extraction data types — enums and dataclasses.

Extracted from fsma_extractor.py for reusability across
extraction, validation, and serialization modules.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


def _new_event_id() -> str:
    """Generate a fresh UUID for a CTE event — #1123.

    A paired SHIPPING/RECEIVING split must not share an ID so the two
    halves do not collide on ingest (they represent distinct events
    at distinct parties).
    """
    return str(uuid.uuid4())


# Kafka topic constants for FSMA event routing
TOPIC_GRAPH_UPDATE = "graph.update"
TOPIC_NEEDS_REVIEW = "nlp.needs_review"

# Confidence threshold below which extractions require human review
HITL_CONFIDENCE_THRESHOLD = 0.85


class CTEType(str, Enum):
    """Critical Tracking Event Types per FSMA 204.

    The seven FDA-defined CTE types from 21 CFR §1.1310 plus CREATION
    (an internal origin marker for synthesized events). HARVESTING,
    COOLING, INITIAL_PACKING, and FIRST_LAND_BASED_RECEIVER were
    missing from this enum before #1103 — which meant the extractor
    silently fell back to SHIPPING for harvest logs, cooling records,
    and packing slips, breaking "one step back to the farm".
    """

    HARVESTING = "HARVESTING"                        # §1.1325 origin
    COOLING = "COOLING"                              # §1.1330
    INITIAL_PACKING = "INITIAL_PACKING"              # §1.1335
    FIRST_LAND_BASED_RECEIVER = "FIRST_LAND_BASED_RECEIVER"  # §1.1325(c)
    SHIPPING = "SHIPPING"                            # §1.1340
    RECEIVING = "RECEIVING"                          # §1.1345
    TRANSFORMATION = "TRANSFORMATION"                # §1.1350
    CREATION = "CREATION"                            # internal origin


class DocumentType(str, Enum):
    """Supported document types for FSMA extraction."""

    BILL_OF_LADING = "BOL"
    INVOICE = "INVOICE"
    PRODUCTION_LOG = "PRODUCTION_LOG"
    # Added for #1103 — origin-side documents that were previously
    # classified UNKNOWN and fell back to SHIPPING.
    HARVEST_LOG = "HARVEST_LOG"
    COOLING_LOG = "COOLING_LOG"
    PACKING_SLIP = "PACKING_SLIP"
    LANDING_REPORT = "LANDING_REPORT"  # first land-based receiver (marine catch)
    UNKNOWN = "UNKNOWN"


class ExtractionConfidence(str, Enum):
    """
    Model Risk Management confidence levels per SR 11-7.

    Used to gate automated acceptance of extracted data.
    """
    HIGH = "HIGH"      # >= 0.95: Auto-accept
    MEDIUM = "MEDIUM"  # 0.85 - 0.95: Manual review required
    LOW = "LOW"        # < 0.85: Reject/Queue for deep review


@dataclass
class LineItem:
    """
    A single line item extracted from a tabular document.

    Groups related entities (lot_code, description, quantity) that appear
    on the same row of a BOL, invoice, or similar document.
    """

    description: str
    lot_code: Optional[str] = None
    quantity: Optional[float] = None
    unit_of_measure: Optional[str] = None
    gtin: Optional[str] = None
    row_index: int = 0
    bounding_box: Optional[Dict[str, float]] = None
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "description": self.description,
            "lot_code": self.lot_code,
            "quantity": self.quantity,
            "unit_of_measure": self.unit_of_measure,
            "gtin": self.gtin,
            "row_index": self.row_index,
            "bounding_box": self.bounding_box,
            "confidence": self.confidence,
        }


@dataclass
class KDE:
    """Key Data Element extracted from a document."""

    traceability_lot_code: Optional[str] = None
    product_description: Optional[str] = None
    quantity: Optional[float] = None
    unit_of_measure: Optional[str] = None
    location_identifier: Optional[str] = None  # GS1 GLN or FDA Reg #
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    ship_from_location: Optional[str] = None
    ship_to_location: Optional[str] = None
    tlc_source_gln: Optional[str] = None
    tlc_source_fda_reg: Optional[str] = None
    ship_from_gln: Optional[str] = None
    ship_to_gln: Optional[str] = None
    # #1104 — GTIN is stored separately instead of being glued into
    # the TLC. The originator-assigned TLC (21 CFR §1.1320) is
    # preserved verbatim. Same-row pairing is handled by LineItem.gtin.
    gtin: Optional[str] = None
    # #1103 — origin-side KDEs for the CTE types that were previously
    # missing from the extractor pipeline.
    harvester_identifier: Optional[str] = None
    field_identifier: Optional[str] = None
    harvest_date: Optional[str] = None
    cooling_location: Optional[str] = None
    cooling_temperature: Optional[str] = None
    packing_location: Optional[str] = None
    harvest_location_ref: Optional[str] = None
    entry_point: Optional[str] = None
    source_vessel_name: Optional[str] = None
    # #1123 — when a BOL is split into SHIPPING + RECEIVING, the
    # RECEIVING half carries a pointer back to the SHIPPING event's
    # TLC so the two legs of the chain are linkable.
    prior_source_tlc: Optional[str] = None
    # #1116 — FTL scoping. ``True`` = product is on the FDA Food
    # Traceability List; ``False`` = verified non-FTL; ``None`` =
    # classifier could not decide (caller should surface as gap, not
    # stamp compliant).
    is_ftl_covered: Optional[bool] = None
    ftl_category: Optional[str] = None


@dataclass
class CTE:
    """Critical Tracking Event with associated KDEs."""

    type: CTEType
    kdes: KDE
    confidence: float
    source_text: Optional[str] = None
    bounding_box: Optional[Dict[str, float]] = None
    # #1123 — stable per-event UUID. Each CTE gets its own ID so that
    # a BOL split into paired SHIPPING + RECEIVING events has two
    # distinct IDs that won't collide on ingest.
    event_id: str = field(default_factory=_new_event_id)


@dataclass
class FSMAExtractionResult:
    """Result of FSMA extraction from a document.

    ``tenant_id`` (#1122) — every extraction must carry its originating
    tenant so downstream consumers (graph ingestion, review queue) can
    enforce tenant scoping without re-reading the event envelope. The
    top-level field is authoritative; nested ``KDE``/``CTE`` structures
    inherit it implicitly from the containing result.
    """

    document_id: str
    tenant_id: str
    document_type: DocumentType
    ctes: List[CTE]
    extraction_timestamp: str
    raw_text: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    line_items: List[LineItem] = field(
        default_factory=list
    )  # Tabular extraction results
    confidence_level: ExtractionConfidence = ExtractionConfidence.LOW
    review_required: bool = True
