"""
TEMPORARY: Legacy dual-write and graph sync code.

This module exists ONLY for the migration period. It will be deleted
entirely when:
  1. All consumers (export, graph sync) read from fsma.traceability_events
     instead of fsma.cte_events
  2. Neo4j graph sync is replaced by direct PostgreSQL queries

To remove: delete this file and remove the two calls in writer.py:
  - migration.dual_write_legacy(...)
  - migration.publish_graph_sync(...)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional, TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from shared.canonical_event import TraceabilityEvent

logger = logging.getLogger("canonical-persistence.migration")


def dual_write_legacy(session: Session, event: TraceabilityEvent) -> Optional[str]:
    """
    Write to legacy fsma.cte_events for backward compatibility.

    During the migration period, both tables receive writes so that
    existing export and graph sync code continues to work.

    Returns the legacy event ID, or None on failure.
    """
    try:
        legacy_id = str(event.event_id)
        session.execute(
            text("""
                INSERT INTO fsma.cte_events (
                    id, tenant_id, event_type, traceability_lot_code,
                    product_description, quantity, unit_of_measure,
                    location_gln, location_name, event_timestamp,
                    source, source_event_id, idempotency_key,
                    sha256_hash, chain_hash,
                    epcis_event_type, epcis_action, epcis_biz_step,
                    validation_status
                ) VALUES (
                    :id, :tenant_id, :event_type, :tlc,
                    :product_description, :quantity, :unit_of_measure,
                    :location_gln, :location_name, :event_timestamp,
                    :source, :source_event_id, :idempotency_key,
                    :sha256_hash, :chain_hash,
                    :epcis_event_type, :epcis_action, :epcis_biz_step,
                    :validation_status
                )
                ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            """),
            {
                "id": legacy_id,
                "tenant_id": str(event.tenant_id),
                "event_type": event.event_type.value,
                "tlc": event.traceability_lot_code,
                "product_description": event.product_reference or "",
                "quantity": event.quantity,
                "unit_of_measure": event.unit_of_measure,
                "location_gln": event.from_facility_reference if event.from_facility_reference and len(event.from_facility_reference) == 13 else None,
                "location_name": event.from_facility_reference or event.to_facility_reference,
                "event_timestamp": event.event_timestamp.isoformat(),
                "source": event.source_system.value,
                "source_event_id": event.source_record_id,
                "idempotency_key": event.idempotency_key,
                "sha256_hash": event.sha256_hash,
                "chain_hash": event.chain_hash,
                "epcis_event_type": event.epcis_event_type,
                "epcis_action": event.epcis_action,
                "epcis_biz_step": event.epcis_biz_step,
                "validation_status": "valid" if event.status.value == "active" else event.status.value,
            },
        )

        # Write KDEs to legacy table
        for kde_key, kde_value in event.kdes.items():
            if kde_value is None:
                continue
            nested = session.begin_nested()
            try:
                session.execute(
                    text("""
                        INSERT INTO fsma.cte_kdes (
                            tenant_id, cte_event_id, kde_key, kde_value, is_required
                        ) VALUES (
                            :tenant_id, :cte_event_id, :kde_key, :kde_value, :is_required
                        )
                        ON CONFLICT (cte_event_id, kde_key) DO NOTHING
                    """),
                    {
                        "tenant_id": str(event.tenant_id),
                        "cte_event_id": legacy_id,
                        "kde_key": kde_key,
                        "kde_value": str(kde_value),
                        "is_required": False,
                    },
                )
            except Exception:
                logger.debug("KDE insert failed, rolling back savepoint", exc_info=True)
                nested.rollback()

        return legacy_id
    except Exception as e:
        logger.warning(
            "legacy_dual_write_failed",
            extra={"event_id": str(event.event_id), "error": str(e)},
        )
        return None


def publish_graph_sync(event: TraceabilityEvent) -> None:
    """
    Publish canonical event to Redis for Neo4j graph sync.

    This is temporary — will be removed when Neo4j is replaced
    by PostgreSQL-native graph queries.
    """
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return

    try:
        import redis as redis_lib
        client = redis_lib.from_url(redis_url)
        message = {
            "event": "canonical.created",
            "data": {
                "canonical_event": {
                    "event_id": str(event.event_id),
                    "tenant_id": str(event.tenant_id),
                    "event_type": event.event_type.value,
                    "traceability_lot_code": event.traceability_lot_code,
                    "product_reference": event.product_reference,
                    "quantity": event.quantity,
                    "unit_of_measure": event.unit_of_measure,
                    "event_timestamp": event.event_timestamp.isoformat(),
                    "from_facility_reference": event.from_facility_reference,
                    "to_facility_reference": event.to_facility_reference,
                    "from_entity_reference": event.from_entity_reference,
                    "to_entity_reference": event.to_entity_reference,
                    "source_system": event.source_system.value,
                    "confidence_score": event.confidence_score,
                    "schema_version": event.schema_version,
                    "sha256_hash": event.sha256_hash,
                },
            },
        }
        client.rpush("neo4j-sync", json.dumps(message, default=str))
    except Exception as exc:
        logger.warning("canonical_graph_sync_failed", extra={
            "event_id": str(event.event_id), "error": str(exc),
        })
