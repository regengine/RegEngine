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

## Operational note — Neo4j graph sync (#1378)

``publish_graph_sync`` ``rpush``-es each canonical write to a Redis
list keyed ``neo4j-sync``.  A consumer exists
(``services/graph/scripts/fsma_sync_worker.py``) but is NOT
referenced by any deployment manifest (railway.toml,
docker-compose) — meaning in production the queue has historically
been a write-only sink that grows unbounded.

Decision: the producer is now **gated OFF by default** via the
``ENABLE_NEO4J_SYNC`` env flag.  In parallel, the monolith
consolidation (``CONSOLIDATION.md``) is retiring Neo4j in favour of
PostgreSQL-native graph queries, so the graph-sync producer has no
long-term home.  Until the producer can be deleted outright:

  - ``ENABLE_NEO4J_SYNC`` defaults to ``"false"``; in that mode the
    function is a short-circuit no-op (no Redis call, no
    serialization cost).
  - When explicitly enabled in a dev / test environment that DOES
    run the consumer, the queue is bounded via ``LTRIM`` to at most
    ``NEO4J_SYNC_MAX_QUEUE`` entries (default 100_000) so a stalled
    consumer cannot OOM the Redis instance.

When Neo4j is retired entirely, delete the function and its call
site in ``writer.py``.
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


# ---------------------------------------------------------------------------
# #1378: Neo4j sync producer gating
# ---------------------------------------------------------------------------

# Name of the Redis list the producer writes to.  The worker at
# services/graph/scripts/fsma_sync_worker.py reads the same key.
_NEO4J_SYNC_QUEUE_KEY = os.getenv("NEO4J_SYNC_QUEUE", "neo4j-sync")


def _neo4j_sync_enabled() -> bool:
    """Return True only if the operator has explicitly opted in.

    Defaults to False because the consumer is not deployed by any
    published manifest; writing to Redis without a reader lets the
    queue grow unbounded.  Evaluated at call time so env changes on
    a long-running process take effect without a restart.
    """
    raw = os.getenv("ENABLE_NEO4J_SYNC", "false").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _neo4j_sync_max_queue() -> int:
    """Upper bound on queued messages before we drop the oldest.

    Only applied when the producer is enabled.  100k was chosen as a
    practical cap — ~50 MB at 500 bytes/message in Redis, enough to
    absorb a few hours of production ingest while the consumer is
    briefly down, but below the point where Redis memory pressure
    becomes an ops problem.  Override with NEO4J_SYNC_MAX_QUEUE.
    """
    try:
        return max(1, int(os.getenv("NEO4J_SYNC_MAX_QUEUE", "100000")))
    except ValueError:
        logger.warning(
            "neo4j_sync_max_queue_invalid_env_value",
            extra={"NEO4J_SYNC_MAX_QUEUE": os.getenv("NEO4J_SYNC_MAX_QUEUE")},
        )
        return 100_000


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
    """Publish canonical event to Redis for Neo4j graph sync.

    Behaviour matrix (see module docstring for the full explanation):

    - ``ENABLE_NEO4J_SYNC`` not set (default) → no-op.  The consumer
      at ``services/graph/scripts/fsma_sync_worker.py`` is not in any
      deployment manifest, so sending here would grow Redis
      unbounded.  This is the default **in every environment**
      including dev, to ensure a forgotten flag does not recreate
      the #1378 leak.
    - ``ENABLE_NEO4J_SYNC=true`` + ``REDIS_URL`` set → send, then
      trim the list to ``NEO4J_SYNC_MAX_QUEUE`` entries so a stalled
      consumer cannot exhaust Redis memory.
    - ``ENABLE_NEO4J_SYNC=true`` + ``REDIS_URL`` unset → no-op with a
      one-line warning.  The producer has been opted-in but Redis
      is unreachable, so we cannot publish but should surface the
      misconfiguration.

    This function is temporary and will be deleted outright when
    Neo4j is retired in favour of PostgreSQL-native graph queries
    (see monolith consolidation plan).
    """
    if not _neo4j_sync_enabled():
        return

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.warning(
            "neo4j_sync_enabled_without_redis_url",
            extra={"event_id": str(event.event_id)},
        )
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
        client.rpush(_NEO4J_SYNC_QUEUE_KEY, json.dumps(message, default=str))

        # Bound queue size.  LTRIM keeps the NEWEST `max_queue`
        # entries; if the consumer falls far behind the oldest
        # messages drop on the floor instead of eating Redis.
        # Losing stale graph-sync messages is acceptable — the
        # canonical write in Postgres is the authoritative record.
        max_queue = _neo4j_sync_max_queue()
        client.ltrim(_NEO4J_SYNC_QUEUE_KEY, -max_queue, -1)
    except Exception as exc:
        logger.warning("canonical_graph_sync_failed", extra={
            "event_id": str(event.event_id), "error": str(exc),
        })
