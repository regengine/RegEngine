"""Shared canonical schemas for RegEngine inter-service communication.

This module provides the single source of truth for all data contracts
across NLP, Review, and Graph services, preventing schema drift.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

# Example constants to avoid duplication in schema examples
EX_SUBJECT = "financial institutions"
EX_ACTION = "must maintain"
EX_OBJECT = "capital reserves"
EX_TEXT = "Financial institutions must maintain capital reserves of at least 8%"


class ObligationType(str, Enum):
    """Standardized obligation types for regulatory requirements."""

    MUST = "MUST"
    MUST_NOT = "MUST_NOT"
    SHOULD = "SHOULD"
    MAY = "MAY"
    CONDUCT = "CONDUCT"
    RECORDKEEPING = "RECORDKEEPING"
    REPORTING = "REPORTING"
    DISCLOSURE = "DISCLOSURE"


class JurisdictionScope(str, Enum):
    """Scope of jurisdiction granularity."""

    FEDERAL = "federal"
    STATE = "state"
    MUNICIPAL = "municipal"


class Jurisdiction(BaseModel):
    """Hierarchical jurisdiction model using ISO-3166 style codes.

    Examples:
    - US (federal)
    - US-NY (state)
    - US-TX-AUS (municipal: Austin, TX)
    """

    code: str = Field(..., description="Jurisdiction code (e.g., US, US-NY, US-TX-AUS)")
    name: str = Field(..., description="Human-readable name (e.g., United States, New York, Austin)")
    parent_code: Optional[str] = Field(
        None, description="Parent jurisdiction code (e.g., US for US-NY, US-TX for US-TX-AUS)"
    )
    scope: JurisdictionScope = Field(..., description="Jurisdiction scope: federal/state/municipal")



class Threshold(BaseModel):
    """Normalized threshold representation for regulatory limits."""

    value: float = Field(..., description="Numeric value of the threshold")
    unit: str = Field(..., description="Unit of measurement (USD, percent, days, etc.)")
    operator: Literal["gt", "lt", "eq", "gte", "lte", "<", ">", "<=", ">=", "=="] = Field(
        ..., description="Comparison operator"
    )
    context: Optional[str] = Field(None, description="Additional context for threshold")

    model_config = {
        "json_schema_extra": {
            "example": {
                "value": 5.0,
                "unit": "percent",
                "operator": "gte",
                "context": "capital requirement",
            }
        }
    }


class ExtractionPayload(BaseModel):
    """NLP extraction output - canonical format for regulatory provisions."""

    provision_id: Optional[str] = Field(None, description="Unique provision identifier")
    subject: str = Field(..., description="Subject of the obligation (e.g., 'financial entities')")
    action: str = Field(..., description="Required action (e.g., 'must maintain', 'shall report')")
    object: Optional[str] = Field(None, description="Object of the obligation")
    obligation_type: ObligationType = Field(..., description="Type of regulatory obligation")
    thresholds: List[Threshold] = Field(default_factory=list, description="Associated thresholds")
    effective_date: Optional[str] = Field(None, description="When obligation becomes effective")
    jurisdiction: Optional[str] = Field(None, description="Regulatory jurisdiction (deprecated; use jurisdiction_codes)")
    jurisdiction_codes: List[str] = Field(
        default_factory=list,
        description="One or more jurisdiction codes the provision applies to (e.g., ['US', 'US-NY'])",
    )
    # Citation/versioning metadata
    rule_version: Optional[str] = Field(None, description="Regulatory rule/version identifier (e.g., EU-2016/679)")
    source_uri: Optional[str] = Field(None, description="Canonical source URI for the cited rule")
    jurisdiction_code: Optional[str] = Field(None, description="Primary jurisdiction code for citation context")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence (0-1)")
    source_text: str = Field(..., description="Original text span from document")
    source_offset: int = Field(..., description="Character offset in source document")
    entities: List[Dict[str, Any]] = Field(default_factory=list, description="Raw extracted entities")

    model_config = {
        "json_schema_extra": {
            "example": {
                "subject": EX_SUBJECT,
                "action": EX_ACTION,
                "object": EX_OBJECT,
                "obligation_type": "MUST",
                "thresholds": [{"value": 8.0, "unit": "percent", "operator": "gte"}],
                "confidence_score": 0.92,
                "source_text": "Financial institutions must maintain capital reserves of at least 8%",
                "source_offset": 1024,
                "jurisdiction": "US-SEC",
                "jurisdiction_codes": ["US"],
            }
        }
    }


class GraphEvent(BaseModel):
    """Event sent to Graph service for knowledge graph ingestion."""

    event_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique event ID")
    event_type: Literal["create_document", "create_provision", "approve_provision"] = Field(
        ..., description="Type of graph operation"
    )
    tenant_id: Optional[UUID] = Field(None, description="Tenant identifier for multi-tenancy")
    doc_hash: str = Field(..., description="Content hash of source document")
    document_id: str = Field(..., description="Document identifier")
    text_clean: str = Field(..., description="Cleaned provision text")
    extraction: ExtractionPayload = Field(..., description="Extracted provision data")
    provenance: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provenance metadata (source URL, page, offset, request_id)",
    )
    embedding: Optional[List[float]] = Field(
        None, description="768-dimensional sentence-transformer embedding"
    )
    status: Literal["APPROVED", "APPROVED_BY_HUMAN", "PENDING_REVIEW"] = Field(
        default="PENDING_REVIEW", description="Approval status"
    )
    reviewer_id: Optional[str] = Field(None, description="User ID of human reviewer (if applicable)")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Event timestamp",
    )

    @field_validator("embedding")
    @classmethod
    def validate_embedding_dimension(cls, v):
        """Ensure embedding is 768-dimensional for sentence-transformers compatibility."""
        if v is not None and len(v) != 768:
            raise ValueError(f"Embedding must be 768-dimensional, got {len(v)}")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "event_type": "approve_provision",
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "doc_hash": "abc123def456",
                "document_id": "doc_001",
                "text_clean": EX_TEXT,
                "extraction": {
                    "subject": EX_SUBJECT,
                    "action": EX_ACTION,
                    "object": EX_OBJECT,
                    "obligation_type": "MUST",
                    "thresholds": [{"value": 8.0, "unit": "percent", "operator": "gte"}],
                    "confidence_score": 0.92,
                    "source_text": EX_TEXT,
                    "source_offset": 1024,
                },
                "provenance": {"source_url": "https://example.com/reg.pdf", "page": 5},
                "status": "APPROVED",
            }
        }
    }


class ReviewItem(BaseModel):
    """Review queue item for human-in-the-loop validation."""

    id: UUID = Field(default_factory=uuid4, description="Review item ID")
    tenant_id: Optional[UUID] = Field(None, description="Tenant identifier")
    document_id: str = Field(..., description="Source document ID")
    extraction: ExtractionPayload = Field(..., description="Extracted provision awaiting review")
    status: Literal["pending", "approved", "rejected"] = Field(
        default="pending", description="Review status"
    )
    reviewer_id: Optional[str] = Field(None, description="Reviewer user ID")
    reviewed_at: Optional[datetime] = Field(None, description="Review timestamp")
    notes: Optional[str] = Field(None, description="Reviewer notes")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "document_id": "doc_001",
                "extraction": {
                    "subject": EX_SUBJECT,
                    "action": EX_ACTION,
                    "object": EX_OBJECT,
                    "obligation_type": "MUST",
                    "confidence_score": 0.72,
                    "source_text": EX_TEXT,
                    "source_offset": 1024,
                },
                "status": "pending",
            }
        }
    }


# =============================================================================
# FSMA 204 Models - Food Safety Modernization Act Section 204
# =============================================================================


class CTEType(str, Enum):
    """Critical Tracking Event Types per FSMA 204.
    
    Used across services to ensure consistent event type handling.
    """
    SHIPPING = "SHIPPING"
    RECEIVING = "RECEIVING"
    TRANSFORMATION = "TRANSFORMATION"
    CREATION = "CREATION"
    INITIAL_PACKING = "INITIAL_PACKING"


class Location(BaseModel):
    """Location identifier for FSMA traceability (simplified model)."""
    
    gln: Optional[str] = Field(None, description="GS1 Global Location Number (13 digits)")
    name: Optional[str] = Field(None, description="Human-readable location name")
    address: Optional[str] = Field(None, description="Physical address")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "gln": "1234567890123",
                "name": "Fresh Farms Distribution Center",
                "address": "123 Produce Way, Fresno, CA 93706"
            }
        }
    }


class ProductDescription(BaseModel):
    """Product description for FSMA traceability."""
    
    text: str = Field(..., description="Product description text")
    sku: Optional[str] = Field(None, description="Stock Keeping Unit")
    gtin: Optional[str] = Field(None, description="GS1 Global Trade Item Number (14 digits)")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "text": "Romaine Lettuce Hearts 12ct",
                "sku": "ROM-12CT",
                "gtin": "00012345678901"
            }
        }
    }


class KDE(BaseModel):
    """Key Data Element extracted from a document."""
    
    name: str = Field(..., description="KDE field name")
    value: str = Field(..., description="KDE value as string")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Extraction confidence")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "traceability_lot_code",
                "value": "00012345678901-L2025-1105-A",
                "confidence": 0.92
            }
        }
    }


class FSMAEvent(BaseModel):
    """FSMA event model for Critical Tracking Events.
    
    Represents a single event extracted from shipping documents (BOL, invoices, ASN).
    Contains the 7 required KDEs for FSMA 204 compliance.
    """
    
    tlc: str = Field(..., description="Traceability Lot Code (GTIN-14 + variable lot)")
    cte_type: CTEType = Field(default=CTEType.SHIPPING, description="Critical Tracking Event type")
    date: str = Field(..., description="Event date in YYYY-MM-DD format")
    quantity: Optional[float] = Field(None, description="Numeric quantity")
    unit: Optional[str] = Field(None, description="Unit of measure (cases, lbs, kg, etc.)")
    product: Optional[ProductDescription] = Field(None, description="Product information")
    ship_from: Optional[Location] = Field(None, description="Ship from location")
    ship_to: Optional[Location] = Field(None, description="Ship to location")
    document_source: Optional[str] = Field(None, description="Source document identifier")
    document_hash: Optional[str] = Field(None, description="Source document hash")
    raw_row_index: Optional[int] = Field(None, description="Row index in source table (for tabular docs)")
    kdes: List[KDE] = Field(default_factory=list, description="All extracted Key Data Elements")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "tlc": "00012345678901-L2025-1105-A",
                "cte_type": "SHIPPING",
                "date": "2025-11-05",
                "quantity": 50,
                "unit": "cases",
                "product": {
                    "text": "Romaine Lettuce Hearts 12ct",
                    "gtin": "00012345678901"
                },
                "ship_from": {"gln": "1234567890123", "name": "Fresh Farms"},
                "ship_to": {"gln": "9876543210987", "name": "Metro Distribution"},
                "kdes": [
                    {"name": "traceability_lot_code", "value": "00012345678901-L2025-1105-A", "confidence": 0.92}
                ]
            }
        }
    }


class FSMALocation(BaseModel):
    """Location identifier for FSMA traceability."""
    
    gln: Optional[str] = Field(None, description="GS1 Global Location Number (13 digits)")
    fda_registration: Optional[str] = Field(None, description="FDA Facility Registration Number")
    name: Optional[str] = Field(None, description="Human-readable location name")
    address: Optional[str] = Field(None, description="Physical address")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "gln": "1234567890123",
                "fda_registration": "12345678901",
                "name": "Fresh Farms Distribution Center",
                "address": "123 Produce Way, Fresno, CA 93706"
            }
        }
    }


class FSMAKeyDataElements(BaseModel):
    """Key Data Elements (KDEs) per FSMA 204 requirements."""
    
    traceability_lot_code: Optional[str] = Field(None, description="GTIN + Lot identifier")
    product_description: Optional[str] = Field(None, description="Product name/description")
    quantity: Optional[float] = Field(None, description="Numeric quantity")
    unit_of_measure: Optional[str] = Field(None, description="Unit (cases, lbs, kg, etc.)")
    location_identifier: Optional[str] = Field(None, description="GLN or FDA Reg as URN")
    event_date: Optional[str] = Field(None, description="Date in YYYY-MM-DD format")
    event_time: Optional[str] = Field(None, description="Time in HH:MM:SSZ format")
    ship_from_location: Optional[FSMALocation] = None
    ship_to_location: Optional[FSMALocation] = None
    # TLC Source fields - required for TRANSFORMATION/INITIAL_PACKING/CREATION events
    tlc_source_gln: Optional[str] = Field(None, description="GLN of facility that assigned the TLC")
    tlc_source_fda_reg: Optional[str] = Field(None, description="FDA Registration of TLC source facility")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "traceability_lot_code": "00012345678901-L2025-1105-A",
                "product_description": "Romaine Lettuce Hearts 12ct",
                "quantity": 50,
                "unit_of_measure": "cases",
                "location_identifier": "urn:gln:1234567890123",
                "event_date": "2025-11-05",
                "event_time": "14:30:00Z",
                "tlc_source_gln": "1234567890123"
            }
        }
    }


class FSMACriticalTrackingEvent(BaseModel):
    """Critical Tracking Event (CTE) per FSMA 204."""
    
    type: str = Field(..., description="SHIPPING, RECEIVING, TRANSFORMATION, or CREATION")
    kdes: FSMAKeyDataElements
    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence score")
    source_document_id: Optional[str] = None
    extraction_timestamp: Optional[str] = None
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "type": "SHIPPING",
                "kdes": {
                    "traceability_lot_code": "00012345678901-L2025-1105-A",
                    "product_description": "Romaine Lettuce Hearts 12ct",
                    "quantity": 50,
                    "unit_of_measure": "cases",
                    "location_identifier": "urn:gln:1234567890123",
                    "event_date": "2025-11-05"
                },
                "confidence": 0.89
            }
        }
    }


class FSMAExtractionPayload(BaseModel):
    """Payload for FSMA extraction results."""
    
    document_id: str
    document_type: str = Field(..., description="BOL, INVOICE, PRODUCTION_LOG, or UNKNOWN")
    ctes: List[FSMACriticalTrackingEvent]
    extraction_timestamp: str
    warnings: List[str] = Field(default_factory=list)
    tenant_id: Optional[str] = None
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "document_id": "doc-fsma-001",
                "document_type": "BOL",
                "ctes": [{
                    "type": "SHIPPING",
                    "kdes": {
                        "traceability_lot_code": "00012345678901-L2025-1105-A",
                        "quantity": 50,
                        "unit_of_measure": "cases"
                    },
                    "confidence": 0.89
                }],
                "extraction_timestamp": "2025-12-02T10:30:00Z",
                "warnings": []
            }
        }
    }


class FSMATraceRequest(BaseModel):
    """Request for traceability query."""
    
    lot_id: str = Field(..., description="Traceability Lot Code to trace")
    direction: str = Field("forward", description="forward or backward")
    max_depth: int = Field(10, ge=1, le=100, description="Maximum hops in trace")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "lot_id": "00012345678901-L2025-1105-A",
                "direction": "forward",
                "max_depth": 10
            }
        }
    }


class FSMATraceResult(BaseModel):
    """Result of traceability query."""
    
    lot_id: str
    direction: str
    facilities: List[FSMALocation]
    events: List[FSMACriticalTrackingEvent]
    total_quantity: Optional[float] = None
    query_time_ms: float
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "lot_id": "00012345678901-L2025-1105-A",
                "direction": "forward",
                "facilities": [
                    {"gln": "1234567890123", "name": "Fresh Farms"},
                    {"gln": "9876543210987", "name": "Metro Distribution"}
                ],
                "events": [],
                "total_quantity": 500,
                "query_time_ms": 45.2
            }
        }
    }
