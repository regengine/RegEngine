"""
Webhook Ingestion Models.

Pydantic models for the webhook ingestion endpoint.
Defines the payload structure for external systems to push
FSMA 204 traceability events into RegEngine.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class WebhookCTEType(str, Enum):
    """CTE types accepted by the webhook endpoint (all 7 per FSMA 204 §1.1310)."""
    HARVESTING = "harvesting"
    COOLING = "cooling"
    INITIAL_PACKING = "initial_packing"
    FIRST_LAND_BASED_RECEIVING = "first_land_based_receiving"
    SHIPPING = "shipping"
    RECEIVING = "receiving"
    TRANSFORMATION = "transformation"


# Valid units of measure for FSMA 204 traceability records
VALID_UNITS_OF_MEASURE = {
    "lbs", "kg", "oz", "g", "tons", "mt",           # weight
    "cases", "cartons", "boxes", "crates", "bins",   # containers
    "pallets", "totes", "bags", "sacks",             # bulk
    "each", "units", "pieces", "count",              # discrete
    "gallons", "liters", "barrels", "bushels",       # volume
}


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
    WebhookCTEType.FIRST_LAND_BASED_RECEIVING: [
        "traceability_lot_code", "product_description", "quantity",
        "unit_of_measure", "landing_date", "receiving_location",
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
    product_description: str = Field(..., description="Human-readable product name", min_length=1, max_length=500)
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
        """Ensure timestamp is parseable and within reasonable bounds."""
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid ISO 8601 timestamp: {v}")

        now = datetime.now(timezone.utc)
        # Reject events more than 90 days old (stale data)
        if dt < now - timedelta(days=90):
            raise ValueError(
                f"Event timestamp {v} is more than 90 days old. "
                "Contact support if you need to backfill historical data."
            )
        # Reject events more than 24 hours in the future (clock skew)
        if dt > now + timedelta(hours=24):
            raise ValueError(
                f"Event timestamp {v} is more than 24 hours in the future."
            )
        return v

    @field_validator("location_gln")
    @classmethod
    def validate_gln_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate GLN is 13 digits with valid GS1 check digit."""
        if v is None or v.strip() == "":
            return v
        clean = re.sub(r"\D", "", v)
        if len(clean) != 13:
            raise ValueError(f"GLN must be exactly 13 digits, got {len(clean)}")
        # GS1 check digit validation
        total = sum(
            int(d) * (3 if i % 2 else 1)
            for i, d in enumerate(reversed(clean[:-1]))
        )
        expected = (10 - (total % 10)) % 10
        if int(clean[-1]) != expected:
            raise ValueError(
                f"GLN check digit invalid: expected {expected}, got {clean[-1]}"
            )
        return clean

    @field_validator("unit_of_measure")
    @classmethod
    def validate_unit_of_measure(cls, v: str) -> str:
        """Validate unit of measure against known FSMA 204 units."""
        normalized = v.strip().lower()
        if normalized not in VALID_UNITS_OF_MEASURE:
            raise ValueError(
                f"Unknown unit '{v}'. Valid units: {', '.join(sorted(VALID_UNITS_OF_MEASURE))}"
            )
        return normalized

    @model_validator(mode="after")
    def require_location(self) -> "IngestEvent":
        """FSMA 204 requires location description for every CTE (§1.1325–§1.1350)."""
        has_gln = self.location_gln and self.location_gln.strip()
        has_name = self.location_name and self.location_name.strip()
        if not has_gln and not has_name:
            # Also check KDEs for location fields
            kde_locations = [
                "ship_from_location", "ship_to_location", "receiving_location",
                "ship_from_gln", "ship_to_gln",
            ]
            has_kde_location = any(
                self.kdes.get(k) for k in kde_locations
                if self.kdes.get(k) and str(self.kdes[k]).strip()
            )
            if not has_kde_location:
                raise ValueError(
                    "FSMA 204 requires at least one location identifier per CTE. "
                    "Provide location_gln, location_name, or a location KDE "
                    "(ship_from_location, receiving_location, etc.)"
                )
        return self


class WebhookPayload(BaseModel):
    """Webhook ingestion payload — the top-level request body."""

    source: str = Field(
        ...,
        description="Source system identifier (sensitech, tive, erp, manual, custom)",
        min_length=1,
    )
    events: List[IngestEvent] = Field(
        ...,
        description="List of CTE events to ingest (max 500 per batch)",
        min_length=1,
        max_length=500,
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
