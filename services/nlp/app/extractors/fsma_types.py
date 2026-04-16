"""
FSMA 204 extraction data types — enums and dataclasses.

Extracted from fsma_extractor.py for reusability across
extraction, validation, and serialization modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# Kafka topic constants for FSMA event routing
TOPIC_GRAPH_UPDATE = "graph.update"
TOPIC_NEEDS_REVIEW = "nlp.needs_review"

# Confidence threshold below which extractions require human review
HITL_CONFIDENCE_THRESHOLD = 0.85


class CTEType(str, Enum):
    """Critical Tracking Event Types per FSMA 204."""

    SHIPPING = "SHIPPING"
    RECEIVING = "RECEIVING"
    TRANSFORMATION = "TRANSFORMATION"
    CREATION = "CREATION"


class DocumentType(str, Enum):
    """Supported document types for FSMA extraction."""

    BILL_OF_LADING = "BOL"
    INVOICE = "INVOICE"
    PRODUCTION_LOG = "PRODUCTION_LOG"
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


@dataclass
class CTE:
    """Critical Tracking Event with associated KDEs."""

    type: CTEType
    kdes: KDE
    confidence: float
    source_text: Optional[str] = None
    bounding_box: Optional[Dict[str, float]] = None


@dataclass
class FSMAExtractionResult:
    """Result of FSMA extraction from a document."""

    document_id: str
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
