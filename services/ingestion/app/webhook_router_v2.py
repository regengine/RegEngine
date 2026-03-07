"""
Webhook Ingestion Router.

Provides POST /api/v1/webhooks/ingest for external systems to push
FSMA 204 traceability events into RegEngine. Each event is validated
against per-CTE KDE requirements, SHA-256 hashed, chain-linked, and
persisted to Postgres.

V2: Replaced in-memory storage with CTEPersistence (Postgres-backed).
    Events now survive restarts, support multi-tenant RLS, and feed
    the FDA export pipeline with real data.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

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


# ---------------------------------------------------------------------------
# Database Session
# ---------------------------------------------------------------------------

def _get_db_session():
    """
    Get a database session for CTE persistence.

    Uses the shared database module's session factory. Falls back to
    in-memory mode if DATABASE_URL is not configured (dev/test).
    """
    try:
        from shared.database import SessionLocal
        db = SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as e:
        logger.warning("database_unavailable, falling back to in-memory: %s", str(e))
        yield None


def _get_persistence(db_session=None):
    """Get CTEPersistence instance, or None if DB unavailable."""
    if db_session is None:
        return None
    try:
        from shared.cte_persistence import CTEPersistence
        return CTEPersistence(db_session)
    except ImportError:
        logger.warning("cte_persistence module not available")
        return None


# ---------------------------------------------------------------------------
# In-memory fallback (dev/test only — logs a warning every time)
# ---------------------------------------------------------------------------

_memory_chain_state: dict[str, str] = {}  # tenant_id -> last_chain_hash
_memory_store: dict[str, dict] = {}


def _store_in_memory(event: IngestEvent, event_id: str, sha256_hash: str, chain_hash: str, tenant_id: str):
    """Fallback storage when Postgres is unavailable. NOT production-safe."""
    logger.warning(
        "STORING_IN_MEMORY — data will be lost on restart",
        extra={"event_id": event_id, "tenant_id": tenant_id},
    )
    _memory_store[event_id] = {
        "id": event_id,
        "event": event.model_dump(),
        "sha256_hash": sha256_hash,
        "chain_hash": chain_hash,
    }


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _verify_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
) -> None:
    """Verify API key if configured."""
    settings = get_settings()
    configured_api_key = getattr(settings, "api_key", None)
    if configured_api_key is not None:
        provided_api_key = x_api_key or x_regengine_api_key
        if not provided_api_key or provided_api_key != configured_api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------------------------------------------------------------------------
# KDE Validation
# ---------------------------------------------------------------------------

def _validate_event_kdes(event: IngestEvent) -> list[str]:
    """Validate that an event has all required KDEs for its CTE type."""
    errors: list[str] = []
    required = REQUIRED_KDES_BY_CTE.get(event.cte_type, [])

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


# ---------------------------------------------------------------------------
# Compliance Alerts
# ---------------------------------------------------------------------------

def _generate_alerts(event: IngestEvent) -> list[dict]:
    """Generate compliance alerts for an event."""
    alerts: list[dict] = []

    if event.cte_type.value in ("shipping", "receiving"):
        has_source = event.kdes.get("ship_from_location") or event.kdes.get("ship_from_gln")
        has_dest = event.kdes.get("ship_to_location") or event.kdes.get("ship_to_gln") or event.kdes.get("receiving_location")
        if not has_source or not has_dest:
            alerts.append({
                "severity": "warning",
                "alert_type": "incomplete_route",
                "message": "Shipping/receiving event missing source or destination identifiers",
            })

    return alerts


# ---------------------------------------------------------------------------
# Neo4j Graph Sync
# ---------------------------------------------------------------------------

def _publish_graph_sync(event_id: str, event: IngestEvent, tenant_id: str) -> None:
    """Push a CTE creation event to Redis for Neo4j graph sync."""
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return

    try:
        import redis as redis_lib
        client = redis_lib.from_url(redis_url)
        message = {
            "event": "cte.created",
            "data": {
                "cte": {
                    "id": event_id,
                    "event_type": event.cte_type.value,
                    "traceability_lot_code": event.traceability_lot_code,
                    "product_description": event.product_description,
                    "quantity": event.quantity,
                    "unit_of_measure": event.unit_of_measure,
                    "location_gln": event.location_gln,
                    "location_name": event.location_name,
                    "timestamp": event.timestamp,
                    "tenant_id": tenant_id,
                    "kdes": event.kdes,
                },
            },
        }
        client.rpush("neo4j-sync", json.dumps(message, default=str))
    except Exception as exc:
        logger.warning("graph_sync_publish_failed event_id=%s error=%s", event_id, str(exc))


# ---------------------------------------------------------------------------
# Ingest Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Ingest traceability events",
    description=(
        "Accept CTE events from external systems (IoT platforms, ERPs, manual entry). "
        "Each event is validated against FSMA 204 KDE requirements, SHA-256 hashed, "
        "chain-linked, and persisted to the compliance database."
    ),
)
async def ingest_events(
    payload: WebhookPayload,
) -> IngestResponse:
    """Process incoming webhook events with persistent storage."""
    tenant_id = payload.tenant_id or "default"
    results: list[EventResult] = []
    accepted = 0
    rejected = 0

    # Get database session
    db_session = None
    persistence = None
    try:
        from shared.database import SessionLocal
        db_session = SessionLocal()
        from shared.cte_persistence import CTEPersistence
        persistence = CTEPersistence(db_session)
    except Exception as e:
        logger.warning("db_init_failed, using in-memory fallback: %s", str(e))

    try:
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

            # Generate alerts
            alerts = _generate_alerts(event)

            if persistence:
                # --- Persistent path (production) ---
                try:
                    store_result = persistence.store_event(
                        tenant_id=tenant_id,
                        event_type=event.cte_type.value,
                        traceability_lot_code=event.traceability_lot_code,
                        product_description=event.product_description,
                        quantity=event.quantity,
                        unit_of_measure=event.unit_of_measure,
                        event_timestamp=event.timestamp,
                        source=payload.source,
                        location_gln=event.location_gln,
                        location_name=event.location_name,
                        kdes=event.kdes,
                        alerts=alerts,
                    )

                    results.append(EventResult(
                        traceability_lot_code=event.traceability_lot_code,
                        cte_type=event.cte_type.value,
                        status="accepted",
                        event_id=store_result.event_id,
                        sha256_hash=store_result.sha256_hash,
                        chain_hash=store_result.chain_hash,
                    ))
                    accepted += 1

                    # Async graph sync
                    _publish_graph_sync(store_result.event_id, event, tenant_id)

                    logger.info(
                        "event_ingested_persistent",
                        extra={
                            "event_id": store_result.event_id,
                            "cte_type": event.cte_type.value,
                            "tlc": event.traceability_lot_code,
                            "source": payload.source,
                            "tenant_id": tenant_id,
                            "idempotent": store_result.idempotent,
                            "sha256": store_result.sha256_hash[:16],
                        },
                    )

                except Exception as e:
                    logger.error(
                        "persistence_failed",
                        extra={"error": str(e), "tlc": event.traceability_lot_code},
                    )
                    results.append(EventResult(
                        traceability_lot_code=event.traceability_lot_code,
                        cte_type=event.cte_type.value,
                        status="rejected",
                        errors=[f"Storage error: {str(e)}"],
                    ))
                    rejected += 1

            else:
                # --- In-memory fallback (dev/test only) ---
                from shared.cte_persistence import compute_event_hash, compute_chain_hash
                from uuid import uuid4

                event_id = str(uuid4())
                sha256_hash = compute_event_hash(
                    event_id, event.cte_type.value,
                    event.traceability_lot_code, event.product_description,
                    event.quantity, event.unit_of_measure,
                    event.location_gln, event.location_name,
                    event.timestamp, event.kdes,
                )
                previous_chain = _memory_chain_state.get(tenant_id)
                chain_hash = compute_chain_hash(sha256_hash, previous_chain)
                _memory_chain_state[tenant_id] = chain_hash
                _store_in_memory(event, event_id, sha256_hash, chain_hash, tenant_id)

                results.append(EventResult(
                    traceability_lot_code=event.traceability_lot_code,
                    cte_type=event.cte_type.value,
                    status="accepted",
                    event_id=event_id,
                    sha256_hash=sha256_hash,
                    chain_hash=chain_hash,
                ))
                accepted += 1

                _publish_graph_sync(event_id, event, tenant_id)

        # Commit all events in a single transaction
        if db_session:
            db_session.commit()

    except Exception as e:
        if db_session:
            db_session.rollback()
        logger.error("ingest_batch_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
    finally:
        if db_session:
            db_session.close()

    return IngestResponse(
        accepted=accepted,
        rejected=rejected,
        total=len(payload.events),
        events=results,
    )


# ---------------------------------------------------------------------------
# Chain Verification Endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/chain/verify",
    summary="Verify hash chain integrity",
    description=(
        "Walk the tenant's entire hash chain from genesis to head, "
        "recomputing each link and checking for tampering."
    ),
)
async def verify_chain(
    tenant_id: str = "default",
):
    """Verify the integrity of the tenant's hash chain."""
    db_session = None
    try:
        from shared.database import SessionLocal
        from shared.cte_persistence import CTEPersistence

        db_session = SessionLocal()
        persistence = CTEPersistence(db_session)
        result = persistence.verify_chain(tenant_id)

        return {
            "tenant_id": tenant_id,
            "chain_valid": result.valid,
            "chain_length": result.chain_length,
            "errors": result.errors,
            "checked_at": result.checked_at,
        }
    except Exception as e:
        logger.error("chain_verification_failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Chain verification failed: {str(e)}")
    finally:
        if db_session:
            db_session.close()
