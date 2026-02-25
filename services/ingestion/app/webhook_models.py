"""
Webhook Ingestion Models.

Pydantic models for the webhook ingestion endpoint.
Defines the payload structure for external systems to push
FSMA 204 traceability events into RegEngine.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class WebhookCTEType(str, Enum):
    """CTE types accepted by the webhook endpoint."""
    HARVESTING = "harvesting"
    COOLING = "cooling"
    INITIAL_PACKING = "initial_packing"
    SHIPPING = "shipping"
    RECEIVING = "receiving"
    TRANSFORMATION = "transformation"


# Required KDEs per CTE type (§1.1325–§1.1350)
REQUIRED_KDES_BY_CTE: Dict[WebhookCTEType, List[str]] = {
    WebhookCTEType.HARVESTING: [
        "traceability_lot_code", "product_description", "quantity",
        "unit_of_measure", "harvest_date", "location_name",
    ],
    WebhookCTEType.COOLING: [
        "traceability_lot_code", "product_description", "quantity",
        "unit_of_measure", "cooling_date", "location_name",
    ],
    WebhookCTEType.INITIAL_PACKING: [
        "traceability_lot_code", "product_description", "quantity",
        "unit_of_measure", "packing_date", "location_name",
    ],
    WebhookCTEType.SHIPPING: [
        "traceability_lot_code", "product_description", "quantity",
        "unit_of_measure", "ship_date", "ship_from_location", "ship_to_location",
    ],
    WebhookCTEType.RECEIVING: [
        "traceability_lot_code", "product_description", "quantity",
        "unit_of_measure", "receive_date", "receiving_location",
    ],
    WebhookCTEType.TRANSFORMATION: [
        "traceability_lot_code", "product_description", "quantity",
        "unit_of_measure", "transformation_date",
    ],
}


class IngestEvent(BaseModel):
    """A single CTE event to ingest."""

    cte_type: WebhookCTEType = Field(..., description="Critical Tracking Event type")
    traceability_lot_code: str = Field(..., description="Traceability Lot Code (TLC)", min_length=3)
    product_description: str = Field(..., description="Human-readable product name", min_length=1)
    quantity: float = Field(..., description="Numeric quantity", gt=0)
    unit_of_measure: str = Field(..., description="Unit (cases, lbs, kg, pallets, etc.)")
    location_gln: Optional[str] = Field(None, description="GS1 Global Location Number (13 digits)")
    location_name: Optional[str] = Field(None, description="Human-readable location name")
    timestamp: str = Field(..., description="ISO 8601 timestamp of the event")
    kdes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional Key Data Elements (temperature, carrier, PO, field ID, etc.)"
    )

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Ensure timestamp is parseable."""
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid ISO 8601 timestamp: {v}")
        return v


class WebhookPayload(BaseModel):
    """Webhook ingestion payload — the top-level request body."""

    source: str = Field(
        ...,
        description="Source system identifier (sensitech, tive, erp, manual, custom)",
        min_length=1,
    )
    events: List[IngestEvent] = Field(
        ...,
        description="List of CTE events to ingest",
        min_length=1,
    )
    tenant_id: Optional[str] = Field(
        None,
        description="Tenant identifier (auto-detected from API key if not provided)"
    )


class EventResult(BaseModel):
    """Result for a single ingested event."""

    traceability_lot_code: str
    cte_type: str
    status: str  # "accepted" or "rejected"
    event_id: Optional[str] = None
    sha256_hash: Optional[str] = None
    chain_hash: Optional[str] = None
    errors: List[str] = Field(default_factory=list)


class IngestResponse(BaseModel):
    """Response from the webhook ingestion endpoint."""

    accepted: int = 0
    rejected: int = 0
    total: int = 0
    events: List[EventResult] = Field(default_factory=list)
    ingestion_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
