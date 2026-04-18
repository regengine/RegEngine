"""
Webhook Ingestion Models.

Pydantic models for the webhook ingestion endpoint.
Defines the payload structure for external systems to push
FSMA 204 traceability events into RegEngine.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

import logging

from pydantic import BaseModel, Field, field_validator, model_validator

_gln_logger = logging.getLogger("gln-validation")


def validate_gln(gln: str) -> tuple[bool, str | None]:
    """Validate a GS1 Global Location Number (13-digit with mod-10 check digit).

    Returns (is_valid, error_message). Standalone helper for use outside Pydantic.
    """
    clean = re.sub(r"\D", "", gln)
    if len(clean) != 13:
        return False, f"GLN must be exactly 13 digits, got {len(clean)}"
    total = sum(
        int(d) * (1 if i % 2 else 3)
        for i, d in enumerate(reversed(clean[:-1]))
    )
    expected = (10 - (total % 10)) % 10
    if int(clean[-1]) != expected:
        return False, f"GLN check digit invalid: expected {expected}, got {clean[-1]}"
    return True, None


class WebhookCTEType(str, Enum):
    """CTE types accepted by the webhook endpoint.

    The 7 canonical FSMA 204 CTEs (per 21 CFR 1.1310) are: harvesting,
    cooling, initial_packing, first_land_based_receiving, shipping,
    receiving, transformation.  GROWING is accepted for ingest
    backwards-compatibility but normalizes to farm metadata, not a CTE.
    """
    GROWING = "growing"  # legacy/internal — not an FDA-defined CTE
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
        "reference_document",  # §1.1327(b)(5)
    ],
    WebhookCTEType.COOLING: [
        "traceability_lot_code", "product_description", "quantity",
        "unit_of_measure", "cooling_date", "location_name",
        "reference_document",  # §1.1330(b)(6)
    ],
    WebhookCTEType.INITIAL_PACKING: [
        "traceability_lot_code", "product_description", "quantity",
        "unit_of_measure", "packing_date", "location_name",
        "reference_document",  # §1.1335(c)(7)
        "harvester_business_name",  # §1.1335(c)(8)
    ],
    WebhookCTEType.FIRST_LAND_BASED_RECEIVING: [
        "traceability_lot_code", "product_description", "quantity",
        "unit_of_measure", "landing_date", "receiving_location",
        "reference_document",  # §1.1325(c)(7)
    ],
    WebhookCTEType.SHIPPING: [
        "traceability_lot_code", "product_description", "quantity",
        "unit_of_measure", "ship_date", "ship_from_location", "ship_to_location",
        "reference_document",  # §1.1340(c)(6)
        "tlc_source_reference",  # §1.1340(c)(7)
    ],
    WebhookCTEType.RECEIVING: [
        "traceability_lot_code", "product_description", "quantity",
        "unit_of_measure", "receive_date", "receiving_location",
        "immediate_previous_source",  # §1.1345(c)(5)
        "reference_document",  # §1.1345(c)(6)
        "tlc_source_reference",  # §1.1345(c)(7)
    ],
    WebhookCTEType.TRANSFORMATION: [
        "traceability_lot_code", "product_description", "quantity",
        "unit_of_measure", "transformation_date", "location_name",
        "reference_document",  # §1.1350(c)(6)
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
    input_traceability_lot_codes: Optional[list[str]] = Field(
        None,
        description=(
            "For transformation CTEs (21 CFR §1.1340): list of input TLCs that were "
            "combined/transformed into the new traceability_lot_code. Required per "
            "§1.1340(a)(4) to link each new TLC to all input TLCs."
        ),
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
        # Allow historical events for FSMA 204 §1.1455(h) 2-year retention backfill.
        # Events older than 90 days are accepted but flagged via _historical_warning.
        # Reject events more than 24 hours in the future (clock skew)
        if dt > now + timedelta(hours=24):
            raise ValueError(
                f"Event timestamp {v} is more than 24 hours in the future."
            )
        return v

    @field_validator("location_gln")
    @classmethod
    def validate_gln_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate GLN is 13 digits with valid GS1 check digit.

        Warning-only: logs invalid GLNs but accepts them to avoid
        breaking existing imports. Use validate_gln() for strict checks.
        """
        if v is None or v.strip() == "":
            return v
        clean = re.sub(r"\D", "", v)
        is_valid, error_msg = validate_gln(clean) if len(clean) == 13 else (False, f"GLN must be exactly 13 digits, got {len(clean)}")
        if not is_valid:
            strict = os.getenv("STRICT_GLN_VALIDATION", "true").lower() == "true"
            if strict:
                raise ValueError(f"Invalid GLN: {error_msg}")
            _gln_logger.warning("invalid_gln value=%s error=%s (strict mode disabled)", v, error_msg)
            return clean if len(clean) == 13 else v
        return clean

    @field_validator("unit_of_measure")
    @classmethod
    def validate_unit_of_measure(cls, v: str) -> str:
        """Validate unit of measure against known FSMA 204 units.

        Warning-only: unknown units are logged but accepted so that
        abbreviated or misspelled values (e.g. "bx", "ea", "lbs.")
        don't crash the entire row. The CSV ingest layer normalises
        common aliases before reaching this validator; this guard exists
        for direct API callers.
        """
        normalized = v.strip().lower()
        if normalized not in VALID_UNITS_OF_MEASURE:
            import logging as _logging
            _logging.getLogger("uom-validation").warning(
                "unknown_unit value=%s accepted_as_is=true valid=%s",
                v, ",".join(sorted(VALID_UNITS_OF_MEASURE)),
            )
            # Accept it — KDE completeness checks will flag it to the user
            return normalized
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
    """Result for a single ingested event.

    status values:
      - ``"accepted"``   — event was new and has been persisted
      - ``"idempotent"`` — event's content matched a previously-persisted
                           event (same ``idempotency_key``); the returned
                           ``event_id`` / ``sha256_hash`` / ``chain_hash``
                           are the existing row's values. Clients should
                           treat this as a success (#1248)
      - ``"rejected"``   — validation failed; see ``errors``
    """

    traceability_lot_code: str
    cte_type: str
    status: str  # "accepted" | "idempotent" | "rejected"
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


class RecentEventsResponse(BaseModel):
    """Response from the /recent events endpoint."""

    tenant_id: str
    events: List[dict] = Field(default_factory=list)
    total: int = 0


class ChainVerifyResponse(BaseModel):
    """Response from the /chain/verify endpoint."""

    tenant_id: str
    chain_valid: bool = False
    chain_length: int = 0
    errors: List[str] = Field(default_factory=list)
    checked_at: Optional[str] = None
