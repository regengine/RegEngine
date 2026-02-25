"""
Webhook Ingestion Router.

Provides POST /api/v1/webhooks/ingest for external systems to push
FSMA 204 traceability events into RegEngine. Each event is validated
against per-CTE KDE requirements, SHA-256 hashed, and chained.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import get_settings
from app.webhook_models import (
    EventResult,
    IngestEvent,
    IngestResponse,
    REQUIRED_KDES_BY_CTE,
    WebhookPayload,
)

logger = logging.getLogger("webhook-ingestion")

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhook Ingestion"])

# In-memory chain state (per-tenant in production this would be DB-backed)
_chain_state: dict[str, str] = {}  # tenant_id -> last_chain_hash


def _verify_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    """Verify API key if configured."""
    settings = get_settings()
    if settings.api_key is not None:
        if not x_api_key or x_api_key != settings.api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _validate_event_kdes(event: IngestEvent) -> list[str]:
    """Validate that an event has all required KDEs for its CTE type."""
    errors: list[str] = []
    required = REQUIRED_KDES_BY_CTE.get(event.cte_type, [])

    # Build a merged dict of top-level fields + kdes for checking
    available: dict[str, object] = {
        "traceability_lot_code": event.traceability_lot_code,
        "product_description": event.product_description,
        "quantity": event.quantity,
        "unit_of_measure": event.unit_of_measure,
        "location_name": event.location_name,
        "location_gln": event.location_gln,
        **event.kdes,
    }

    for kde_name in required:
        val = available.get(kde_name)
        if val is None or (isinstance(val, str) and val.strip() == ""):
            errors.append(f"Missing required KDE '{kde_name}' for {event.cte_type.value} CTE")

    return errors


def _compute_event_hash(event: IngestEvent, event_id: str) -> str:
    """Compute SHA-256 hash of an event using pipe-delimited canonical form."""
    canonical = "|".join([
        event_id,
        event.cte_type.value,
        event.traceability_lot_code,
        event.product_description,
        str(event.quantity),
        event.unit_of_measure,
        event.location_gln or "",
        event.location_name or "",
        event.timestamp,
        json.dumps(event.kdes, sort_keys=True, default=str),
    ])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _compute_chain_hash(event_hash: str, previous_chain_hash: str | None) -> str:
    """Chain this event's hash to the previous chain hash."""
    chain_input = f"{previous_chain_hash or 'GENESIS'}|{event_hash}"
    return hashlib.sha256(chain_input.encode("utf-8")).hexdigest()


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Ingest traceability events",
    description=(
        "Accept CTE events from external systems (IoT platforms, ERPs, manual entry). "
        "Each event is validated against FSMA 204 KDE requirements, SHA-256 hashed, "
        "and chained to the tenant's audit trail."
    ),
)
async def ingest_events(
    payload: WebhookPayload,
    _: None = Depends(_verify_api_key),
) -> IngestResponse:
    """Process incoming webhook events."""
    tenant_id = payload.tenant_id or "default"
    results: list[EventResult] = []
    accepted = 0
    rejected = 0

    for event in payload.events:
        # Validate KDEs
        errors = _validate_event_kdes(event)

        if errors:
            results.append(EventResult(
                traceability_lot_code=event.traceability_lot_code,
                cte_type=event.cte_type.value,
                status="rejected",
                errors=errors,
            ))
            rejected += 1
            continue

        # Generate event ID
        event_id = str(uuid4())

        # Compute hashes
        event_hash = _compute_event_hash(event, event_id)
        previous_chain = _chain_state.get(tenant_id)
        chain_hash = _compute_chain_hash(event_hash, previous_chain)
        _chain_state[tenant_id] = chain_hash

        results.append(EventResult(
            traceability_lot_code=event.traceability_lot_code,
            cte_type=event.cte_type.value,
            status="accepted",
            event_id=event_id,
            sha256_hash=event_hash,
            chain_hash=chain_hash,
        ))
        accepted += 1

        logger.info(
            "event_ingested",
            extra={
                "event_id": event_id,
                "cte_type": event.cte_type.value,
                "tlc": event.traceability_lot_code,
                "source": payload.source,
                "tenant_id": tenant_id,
                "sha256": event_hash[:16],
            },
        )

    return IngestResponse(
        accepted=accepted,
        rejected=rejected,
        total=len(payload.events),
        events=results,
    )
