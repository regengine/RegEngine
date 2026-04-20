"""
NOT an Alembic migration. Bootstraps schema if tables absent. Use Alembic for versioned migrations.

TEMPORARY: Legacy dual-write and graph sync code.

This module exists ONLY for the migration period. It will be deleted
entirely when:
  1. All consumers (export, graph sync) read from fsma.traceability_events
     instead of fsma.cte_events
  2. Neo4j graph sync is replaced by direct PostgreSQL queries

To remove: delete this file and remove the two calls in writer.py:
  - schema_bootstrap.dual_write_legacy(...)
  - schema_bootstrap.publish_graph_sync(...)

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
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from sqlalchemy import event as sa_event, text
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from shared.canonical_event import TraceabilityEvent

logger = logging.getLogger("canonical-persistence.schema_bootstrap")


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


def dual_write_legacy(session: Session, event: "TraceabilityEvent") -> str:
    """
    Write to legacy fsma.cte_events for backward compatibility.

    During the migration period, both tables receive writes so that
    existing export and graph sync code continues to work.

    Returns the legacy event ID.

    Raises on failure. #1277: a swallowed dual-write meant the canonical
    row landed in ``fsma.traceability_events`` but NOT in
    ``fsma.cte_events`` — since existing FDA-export paths still read
    from the legacy table, the regulator-facing audit output would
    silently diverge from the canonical source of truth. Letting the
    exception propagate aborts the outer transaction so the canonical
    row is rolled back too, restoring the "both tables or neither"
    invariant until the legacy table is retired.

    Callers that genuinely don't need legacy write (e.g. some ingestion
    sub-paths, test fixtures) must opt out via
    ``CanonicalEventStore(..., dual_write=False)`` — silence via
    exception swallowing is no longer available.
    """
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

    # Write KDEs to legacy table. All KDE inserts are batched under a
    # single savepoint (#1292 — the previous per-KDE savepoint loop
    # issued one roundtrip per KDE). ON CONFLICT handles duplicate keys;
    # if the whole batch fails we roll back this savepoint and log, but
    # the CTE event row above is preserved.
    kde_rows = [
        {
            "tenant_id": str(event.tenant_id),
            "cte_event_id": legacy_id,
            "kde_key": kde_key,
            "kde_value": str(kde_value),
            "is_required": False,
        }
        for kde_key, kde_value in event.kdes.items()
        if kde_value is not None
    ]
    if kde_rows:
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
                kde_rows,
            )
        except Exception:
            logger.debug("KDE batch insert failed, rolling back savepoint", exc_info=True)
            nested.rollback()

    return legacy_id


def publish_graph_sync(event: "TraceabilityEvent") -> None:
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


# ---------------------------------------------------------------------------
# #1276 — Transactional-outbox deferral for graph sync
# ---------------------------------------------------------------------------
#
# Problem: ``persist_event`` used to call ``publish_graph_sync`` SYNCHRONOUSLY
# inside the active session, BEFORE the surrounding DB transaction committed.
# If the outer transaction rolled back (schema-validation failure, chain-hash
# conflict, anything), Redis had already received the ``canonical.created``
# message. The Neo4j sync worker then applied it, creating a ghost graph
# node whose canonical DB row did not exist — divergence that can corrupt
# trace-forward / trace-back queries and produce FDA reports referencing
# events that were never persisted.
#
# Fix: stage the event in ``session.info`` at call time and install
# ``after_commit`` / ``after_rollback`` listeners. Publishing runs only
# after the SQL-level commit succeeds; a rollback discards the staged
# events silently. This is effectively a transactional outbox whose
# "table" is the in-memory session, which is sufficient for a
# temporary migration shim (the whole module is scheduled for
# deletion when Neo4j is retired).
#
# The staging function is also the correct place for future transports
# (e.g. an in-DB outbox table for at-least-once durability across
# process restarts); everything flows through ``stage_graph_sync``.

# Keys we stash on ``session.info`` — underscore-prefixed so they stay
# well away from application keys that travel on the session.
_SESSION_PENDING_KEY = "_canonical_graph_sync_pending"
_SESSION_HOOKS_INSTALLED_KEY = "_canonical_graph_sync_hooks_installed"


def _drain_pending_graph_sync(session: Session) -> None:
    """after_commit listener: publish every event staged during the now-committed transaction.

    Called once per session commit. Pops the pending list so a subsequent
    commit on the same session does not re-publish. Any exception in a
    single publish is swallowed and logged — graph sync is best-effort
    and the canonical DB row is the authoritative record of truth.
    """
    pending: Optional[List[Any]] = session.info.pop(_SESSION_PENDING_KEY, None)
    if not pending:
        return
    for event in pending:
        try:
            publish_graph_sync(event)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "canonical_graph_sync_post_commit_failed",
                extra={"event_id": str(getattr(event, "event_id", "?")), "error": str(exc)},
            )


def _clear_pending_graph_sync(session: Session) -> None:
    """after_rollback listener: drop staged events so they never reach Redis.

    This is the core of the #1276 fix: if the transaction rolls back we
    MUST NOT publish — publishing would create the exact ghost event the
    issue calls out. Signature matches ``after_rollback(session)``.
    """
    dropped = session.info.pop(_SESSION_PENDING_KEY, None)
    if dropped:
        logger.info(
            "canonical_graph_sync_dropped_on_rollback",
            extra={"count": len(dropped)},
        )


def _clear_pending_graph_sync_soft(session: Session, previous_transaction: Any) -> None:
    """after_soft_rollback listener: same semantics as the hard-rollback
    drop, but SQLAlchemy dispatches this event with an extra
    ``previous_transaction`` argument (the SessionTransaction that just
    rolled back). A nested savepoint rollback counts as a "soft"
    rollback; anything staged inside that savepoint must also be
    dropped because the canonical row it referenced is gone.

    We keep this as a separate callable to match the event's 2-arg
    signature; a unified ``*args``-style handler would work but makes
    the signature intent less obvious in stack traces.
    """
    _clear_pending_graph_sync(session)


def stage_graph_sync(session: Session, event: "TraceabilityEvent") -> None:
    """Defer ``publish_graph_sync`` until after the session commits (#1276).

    Call from any code path that currently runs inside a DB transaction
    and used to call ``publish_graph_sync`` directly. Semantics:

    - On COMMIT: the event is published to Redis exactly once.
    - On ROLLBACK: the event is discarded; Redis never sees it.
    - If ``ENABLE_NEO4J_SYNC`` is off (the production default), this is
      a no-op and the staging dict is never even touched. The
      short-circuit keeps the hot path identical to the pre-fix
      behaviour when the feature is disabled.

    The function is idempotent across repeated calls on the same
    session: listeners are installed exactly once, subsequent events
    merely append to the pending list.
    """
    # Match the short-circuit in publish_graph_sync: if the operator has
    # not opted in, staging is pointless. Evaluating the env flag here
    # (rather than at publish time) avoids the per-call overhead of
    # dict mutation and listener installation in the default case, which
    # matters because persist_event is in the hot ingestion path.
    if not _neo4j_sync_enabled():
        return

    pending: List[Any] = session.info.setdefault(_SESSION_PENDING_KEY, [])

    # Install listeners once per session. SQLAlchemy allows multiple
    # listeners for the same event, so guard against double-install
    # on repeated calls; otherwise a batch of N events would register
    # N after_commit hooks and publish the same event N times.
    if not session.info.get(_SESSION_HOOKS_INSTALLED_KEY):
        session.info[_SESSION_HOOKS_INSTALLED_KEY] = True
        sa_event.listen(session, "after_commit", _drain_pending_graph_sync)
        sa_event.listen(session, "after_rollback", _clear_pending_graph_sync)
        sa_event.listen(session, "after_soft_rollback", _clear_pending_graph_sync_soft)

    pending.append(event)
