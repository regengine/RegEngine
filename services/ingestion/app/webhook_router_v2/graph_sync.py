"""Neo4j graph-sync publishing (Redis-backed, gated by #1378) and the
success/failure counters behind ``get_graph_sync_stats``.

Code moved verbatim from the original ``webhook_router_v2.py``. The
in-memory fallback counters (``_graph_sync_failures`` /
``_graph_sync_successes``) live on the package namespace — the original
module's globals — so tests reading/patching
``app.webhook_router_v2._graph_sync_failures`` (and ``_get_redis_client``)
keep working.
"""

from __future__ import annotations

import json
import os
import sys

from ..webhook_models import IngestEvent

_pkg = sys.modules[__package__]


# ---------------------------------------------------------------------------
# Neo4j Graph Sync
# ---------------------------------------------------------------------------

_SYNC_COUNTER_PREFIX = "regengine:graph_sync"


def _get_redis_client():
    """Get Redis client for counter persistence. Returns None if unavailable."""
    try:
        import redis
        redis_url = os.getenv("REDIS_URL", "rediss://redis:6379/0")
        return redis.from_url(redis_url, decode_responses=True, socket_timeout=1)
    except Exception:
        _pkg.logger.debug("redis_client_unavailable", exc_info=True)
        return None


def _incr_sync_counter(key: str) -> None:
    """Increment a graph sync counter in Redis with in-memory fallback."""
    try:
        client = _pkg._get_redis_client()
        if client:
            client.incr(f"{_pkg._SYNC_COUNTER_PREFIX}:{key}")
            return
    except Exception:
        _pkg.logger.debug("redis_sync_counter_failed", key=key, exc_info=True)
    # Fallback to in-memory (counters live on the package module — the
    # original file's ``global _graph_sync_failures, _graph_sync_successes``)
    if key == "failures":
        _pkg._graph_sync_failures += 1
    else:
        _pkg._graph_sync_successes += 1


def get_graph_sync_stats() -> dict:
    """Return graph sync success/failure counts from Redis or in-memory fallback."""
    try:
        client = _pkg._get_redis_client()
        if client:
            return {
                "successes": int(client.get(f"{_pkg._SYNC_COUNTER_PREFIX}:successes") or 0),
                "failures": int(client.get(f"{_pkg._SYNC_COUNTER_PREFIX}:failures") or 0),
            }
    except Exception:
        _pkg.logger.debug("redis_sync_stats_unavailable", exc_info=True)
    return {"successes": _pkg._graph_sync_successes, "failures": _pkg._graph_sync_failures}


# #1378 — Neo4j sync producer gating (mirrors shared.canonical_persistence.legacy_dual_write).
#
# The consumer (services/graph/scripts/fsma_sync_worker.py) is not started
# by any deployment manifest (Dockerfile, docker-compose, railway.toml).
# Publishing unconditionally caused the ``neo4j-sync`` Redis list to grow
# without bound, evicting hot keys (rate limit counters, idempotency
# records) under the ``allkeys-lru`` policy. Gate the producer behind
# ``ENABLE_NEO4J_SYNC`` (default off) and bound the queue with ``LTRIM``
# in case a dev/test environment opts in but the consumer falls behind.
_NEO4J_SYNC_QUEUE_KEY = "neo4j-sync"


def _neo4j_sync_enabled() -> bool:
    """Return True only if the operator has explicitly opted in.

    Defaults to False because the consumer is not deployed by any
    published manifest; writing to Redis without a reader lets the
    queue grow unbounded (#1378). Evaluated at call time so env
    changes on a long-running process take effect without restart.
    """
    raw = os.getenv("ENABLE_NEO4J_SYNC", "false").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _neo4j_sync_max_queue() -> int:
    """Upper bound on queued messages before we drop the oldest.

    Only applied when the producer is enabled. 100k mirrors the
    canonical-persistence default — see migration.py for the sizing
    rationale. Override with ``NEO4J_SYNC_MAX_QUEUE``.
    """
    try:
        return max(1, int(os.getenv("NEO4J_SYNC_MAX_QUEUE", "100000")))
    except ValueError:
        _pkg.logger.warning(
            "neo4j_sync_max_queue_invalid_env_value value=%s",
            os.getenv("NEO4J_SYNC_MAX_QUEUE"),
        )
        return 100_000


def _publish_graph_sync(event_id: str, event: IngestEvent, tenant_id: str) -> None:
    """Push a CTE creation event to Redis for Neo4j graph sync.

    Behaviour matrix (#1378 — matches shared.canonical_persistence.legacy_dual_write):

    - ``ENABLE_NEO4J_SYNC`` not set (default) → no-op. The consumer at
      ``services/graph/scripts/fsma_sync_worker.py`` is not in any
      deployment manifest, so sending here would grow Redis unbounded.
      Default in every environment to ensure a forgotten flag does not
      recreate the leak.
    - ``ENABLE_NEO4J_SYNC=true`` + ``REDIS_URL`` set → send, then
      ``LTRIM`` the list to ``NEO4J_SYNC_MAX_QUEUE`` entries so a
      stalled consumer cannot exhaust Redis memory.
    - ``ENABLE_NEO4J_SYNC=true`` + ``REDIS_URL`` unset → no-op.

    This function is temporary and will be deleted outright when Neo4j
    is retired in favour of PostgreSQL-native graph queries.
    """
    if not _pkg._neo4j_sync_enabled():
        return

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
        client.rpush(_pkg._NEO4J_SYNC_QUEUE_KEY, json.dumps(message, default=str))
        # Bound queue size. LTRIM keeps the NEWEST `max_queue` entries;
        # if the consumer falls far behind the oldest messages drop on
        # the floor instead of eating Redis. The canonical write in
        # Postgres is the authoritative record so losing stale graph
        # sync messages is acceptable.
        try:
            client.ltrim(_pkg._NEO4J_SYNC_QUEUE_KEY, -_pkg._neo4j_sync_max_queue(), -1)
        except Exception:
            # LTRIM bound is best-effort; a failure here must not be
            # treated as a publish failure since the rpush above did
            # succeed and the canonical row in Postgres is intact.
            _pkg.logger.debug("neo4j_sync_ltrim_failed", exc_info=True)
        _pkg._incr_sync_counter("successes")
    except (ImportError, ConnectionError, TimeoutError, OSError, ValueError, TypeError) as exc:
        _pkg._incr_sync_counter("failures")
        _pkg.logger.warning("graph_sync_publish_failed event_id=%s error=%s", event_id, str(exc))
