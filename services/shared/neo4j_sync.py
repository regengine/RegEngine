"""
Shared Neo4j graph-sync producer utilities (#1378).

This module is the single authoritative location for:

  - ``is_enabled()``  — should the producer write to Redis at all?
  - ``publish()``     — rpush + ltrim to the Neo4j sync queue.

Both ``services/shared/canonical_persistence/migration.py`` and
``services/ingestion/app/webhook_router_v2.py`` previously duplicated
this logic inline.  They now import from here.

TEMPORARY: this module (and everything it exports) will be deleted when
Neo4j is retired in favour of PostgreSQL-native graph queries.  See the
monolith consolidation plan for timing.

Behaviour matrix
----------------
- ``ENABLE_NEO4J_SYNC`` unset / ``"false"`` (default) → ``publish()``
  is a no-op.  The consumer at
  ``services/graph/scripts/fsma_sync_worker.py`` is not referenced by
  any deployment manifest; sending unconditionally would grow Redis
  unbounded (#1378).
- ``ENABLE_NEO4J_SYNC=true`` + ``REDIS_URL`` set → rpush then ltrim
  to ``NEO4J_SYNC_MAX_QUEUE`` (default 100 000) entries.
- ``ENABLE_NEO4J_SYNC=true`` + ``REDIS_URL`` unset → no-op with a
  one-line warning.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("shared.neo4j_sync")

# Name of the Redis list the producer writes to and the consumer reads from.
# Override with the NEO4J_SYNC_QUEUE env var if you have a non-default key.
QUEUE_KEY: str = os.getenv("NEO4J_SYNC_QUEUE", "neo4j-sync")


def is_enabled() -> bool:
    """Return True only when the operator has explicitly opted in.

    Defaults to False so a forgotten flag cannot silently recreate the
    unbounded-queue leak described in #1378.  Evaluated at call time so
    a long-running process picks up env changes without a restart.
    """
    raw = os.getenv("ENABLE_NEO4J_SYNC", "false").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _max_queue() -> int:
    """Upper bound on queued messages before the oldest are dropped.

    Only applied when the producer is enabled.  100 000 mirrors the
    canonical-persistence default — at ~1 KB per message this is ~100 MB
    worst-case, well within typical Redis limits.  Override with the
    NEO4J_SYNC_MAX_QUEUE env var.
    """
    try:
        return max(1, int(os.getenv("NEO4J_SYNC_MAX_QUEUE", "100000")))
    except ValueError:
        logger.warning(
            "neo4j_sync_max_queue_invalid_env_value value=%s",
            os.getenv("NEO4J_SYNC_MAX_QUEUE"),
        )
        return 100_000


def publish(
    message: Dict[str, Any],
    *,
    redis_url: Optional[str] = None,
    queue_key: Optional[str] = None,
) -> bool:
    """Publish *message* to the Neo4j sync Redis queue.

    Parameters
    ----------
    message:
        Serialisable dict that will be JSON-encoded and rpush-ed.
    redis_url:
        Override the ``REDIS_URL`` env var (mainly for tests).
    queue_key:
        Override ``QUEUE_KEY`` / ``NEO4J_SYNC_QUEUE`` (mainly for tests).

    Returns
    -------
    bool
        ``True`` if the message was successfully pushed, ``False`` for
        every other outcome (disabled, misconfigured, transient error).
        Callers should treat ``False`` as non-fatal — the canonical write
        in Postgres is the authoritative record.
    """
    if not is_enabled():
        return False

    url = redis_url or os.getenv("REDIS_URL")
    if not url:
        logger.warning("neo4j_sync_enabled_without_redis_url")
        return False

    key = queue_key or QUEUE_KEY

    try:
        import redis as redis_lib  # lazy import — not all services install redis

        client = redis_lib.from_url(url)
        client.rpush(key, json.dumps(message, default=str))

        # LTRIM keeps the NEWEST `max_queue` entries. If the consumer falls
        # far behind, the oldest messages drop on the floor instead of
        # exhausting Redis memory.  Losing stale graph-sync messages is
        # acceptable — the canonical write in Postgres is the authority.
        try:
            client.ltrim(key, -_max_queue(), -1)
        except Exception:
            # LTRIM is best-effort; a failure here must not be treated as a
            # publish failure — rpush already succeeded.
            logger.debug("neo4j_sync_ltrim_failed", exc_info=True)

        return True
    except Exception as exc:
        logger.warning("neo4j_sync_publish_failed error=%s", str(exc))
        return False
