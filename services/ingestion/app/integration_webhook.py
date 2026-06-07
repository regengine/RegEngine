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
    """Receive and map events from an external system.

    F-6 (Ingestion re-audit): this endpoint is intentionally not wired into
    ``main.py``. The active, secured replacement is
    ``app/integration_router.py`` which is mounted at the same prefix
    (``/api/v1/integrations``) with auth + tenant scoping + HMAC + rate-limit
    + idempotency. This module is retained only because its pure mapping
    helpers (``_extract_nested``, ``_apply_mapping``) and Pydantic models are
    locked under ``tests/test_integration_webhook_1342.py``.

    To prevent regression — i.e. a future "wire up integrations" PR mounting
    this router without restoring those security invariants — the endpoint
    raises ``NotImplementedError``. Any caller that hits this path will get a
    501 and a clear pointer to ``integration_router`` so they migrate rather
    than re-introduce an unauthenticated receiver.
    """
    raise NotImplementedError(
        "integration_webhook.receive_webhook is not wired. Use the secured "
        "integration_router (app/integration_router.py) which provides "
        "auth + tenant scoping + HMAC + idempotency at the same /api/v1/integrations "
        "prefix. See F-6 in the ingestion re-audit."
    )
