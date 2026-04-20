"""
Generic webhook receiver for ERP and external system integrations.

Accepts any JSON payload, applies a configurable field mapping to convert
it to RegEngine's WebhookPayload format, then routes it through the
standard ingestion pipeline.

This allows ERPs (Produce Pro, SAP B1, Aptean, etc.) to push data to
RegEngine without a dedicated connector — the tenant configures a field
mapping in their settings, and RegEngine does the rest.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = structlog.get_logger("integration-webhook")

router = APIRouter(prefix="/api/v1/integrations", tags=["Integrations"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class FieldMapping(BaseModel):
    """Maps source field paths to RegEngine canonical fields."""
    cte_type: str = Field(default="cte_type", description="Source field for CTE type")
    traceability_lot_code: str = Field(default="traceability_lot_code")
    product_description: str = Field(default="product_description")
    quantity: str = Field(default="quantity")
    unit_of_measure: str = Field(default="unit_of_measure")
    location_name: str = Field(default="location_name")
    timestamp: str = Field(default="timestamp")


class WebhookPayload(BaseModel):
    """Incoming webhook payload with optional field mapping override."""
    events: List[Dict[str, Any]] = Field(..., description="Array of event objects")
    field_mapping: Optional[FieldMapping] = Field(
        default=None,
        description="Custom field mapping. If omitted, uses default canonical field names.",
    )


class WebhookResponse(BaseModel):
    """Response from webhook ingestion."""
    received: int
    mapped: int
    errors: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_nested(obj: Dict[str, Any], path: str) -> Any:
    """Extract a value from a nested dict using dot notation (e.g., 'header.docDate')."""
    parts = path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _apply_mapping(event: Dict[str, Any], mapping: FieldMapping) -> Dict[str, Any]:
    """Apply field mapping to convert an external event to canonical format."""
    canonical: Dict[str, Any] = {}

    for canonical_field, source_path in mapping.model_dump().items():
        value = _extract_nested(event, source_path)
        if value is not None:
            canonical[canonical_field] = value

    # Carry over any extra fields as KDEs
    mapped_sources = set(mapping.model_dump().values())
    kdes: Dict[str, Any] = {}
    for key, value in event.items():
        if key not in mapped_sources and value is not None:
            kdes[key] = value
    if kdes:
        canonical["kdes"] = kdes

    return canonical


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/webhook/{connector_id}",
    response_model=WebhookResponse,
    summary="Receive events from an external system via webhook",
    description=(
        "Generic webhook endpoint that accepts JSON event arrays with "
        "optional field mapping. Maps events to RegEngine's canonical "
        "format and routes them through the ingestion pipeline."
    ),
)
async def receive_webhook(
    connector_id: str,
    payload: WebhookPayload,
    request: Request,
) -> WebhookResponse:
    """Receive and map events from an external system."""
    # Use provided mapping or default
    mapping = payload.field_mapping or FieldMapping()

    mapped_events: List[Dict[str, Any]] = []
    errors: List[str] = []

    for i, event in enumerate(payload.events):
        try:
            canonical = _apply_mapping(event, mapping)
            if not canonical.get("cte_type"):
                errors.append(f"Event {i}: missing cte_type after mapping")
                continue
            if not canonical.get("traceability_lot_code"):
                errors.append(f"Event {i}: missing traceability_lot_code after mapping")
                continue
            canonical["_source_connector"] = connector_id
            mapped_events.append(canonical)
        except Exception as e:
            errors.append(f"Event {i}: mapping error: {str(e)}")

    # TODO: Route mapped_events through the standard ingestion pipeline
    # For now, return the count of successfully mapped events
    logger.info(
        "webhook_received",
        connector_id=connector_id,
        total=len(payload.events),
        mapped=len(mapped_events),
        errors=len(errors),
    )

    return WebhookResponse(
        received=len(payload.events),
        mapped=len(mapped_events),
        errors=errors,
    )
