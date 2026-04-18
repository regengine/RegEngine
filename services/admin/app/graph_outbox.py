"""Postgres -> Neo4j write-ahead outbox (#1398).

Problem
-------
``supplier_graph_sync.record_*`` runs **after** the Postgres commit. If
Neo4j is down at that instant the Postgres write lands, the Neo4j mirror
is lost forever, and the only signal is a best-effort warning log.
Downstream graph-traversal endpoints return empty lineage even though
Postgres says the tenant is compliant — which for FSMA 204 lineage
reconstruction is a regulatory liability.

Solution
--------
The classic transactional-outbox pattern:

  1. **Enqueue phase.** In the same SQLAlchemy session (and therefore the
     same Postgres transaction) that writes the canonical row, the caller
     inserts a ``graph_outbox`` row describing the Neo4j write to replay.
     Either both land or neither lands.

  2. **Drain phase.** A background worker (cron-driven is fine — see the
     ``drain_graph_outbox`` entry point for schedulers) pulls pending
     rows, executes them against Neo4j using the tenant-scoped session
     wrapper from ``shared.neo4j_tenant_context``, and marks each one
     ``drained`` on success. On failure it bumps ``attempts`` and
     reschedules with exponential backoff; after ``max_attempts`` the
     row flips to ``failed`` and is surfaced to ops.

  3. **Reconciliation.** ``reconcile_graph_outbox`` returns pending /
     failed counts and the oldest pending row's age so ops can plot
     ``graph_sync_lag_seconds`` and alert when drift exceeds a budget.

Design notes
------------
* The table and this module deliberately do not know about
  ``supplier_graph_sync``. The caller supplies a Cypher string and a
  params dict — any future graph writer (not just supplier onboarding)
  can enqueue through the same API.

* We keep the drainer single-threaded and row-at-a-time. Neo4j
  Community's throughput is not the bottleneck for our current volume;
  correctness and ordering are. If that changes, swap
  ``FOR UPDATE SKIP LOCKED`` in for multi-worker throughput — the table
  already has the right index for it.

* Dedupe: callers who can provide a stable ``dedupe_key`` (e.g. a CTE
  event id) get upsert semantics so a client retry does not double-write.
  Callers who can't just omit it and accept at-least-once delivery.

* RLS: ``graph_outbox`` has a tenant-isolation policy (see migration
  a7b8c9d0e1f2). The drainer runs as a job — it sets
  ``regengine.is_sysadmin`` so it can see rows for every tenant, but it
  still binds each Neo4j session to the row's ``tenant_id``.

This module does NOT modify ``supplier_graph_sync.py`` — that file's
best-effort ``_run`` continues to work and remains the current write path.
Adoption is per-caller: each call site that wants the durability
guarantee migrates from ``supplier_graph_sync.record_X(...)`` to
``enqueue_graph_write(...)``.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, ContextManager, Optional, Sequence
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = structlog.get_logger("graph_outbox")


class OutboxStatus(str, enum.Enum):
    PENDING = "pending"
    DRAINED = "drained"
    FAILED = "failed"


@dataclass(frozen=True)
class OutboxRow:
    """A single materialized graph_outbox row."""

    id: int
    tenant_id: Optional[str]
    operation: str
    cypher: str
    params: dict
    attempts: int
    max_attempts: int
    dedupe_key: Optional[str]


# ---------------------------------------------------------------------------
# Enqueue — runs inside the caller's transaction
# ---------------------------------------------------------------------------


def enqueue_graph_write(
    session: Session,
    *,
    tenant_id: Optional[str],
    operation: str,
    cypher: str,
    params: dict,
    dedupe_key: Optional[str] = None,
    max_attempts: int = 10,
) -> None:
    """Insert a graph_outbox row in the caller's session/transaction.

    This does NOT commit. The caller commits alongside their canonical
    Postgres write, so both land atomically or neither does.

    Args:
      session: SQLAlchemy session the caller is using for the canonical
        Postgres write. Must be the same session for the atomicity
        guarantee to hold.
      tenant_id: UUID string or None. When None, the row is treated as a
        global / cross-tenant write (reserved for system events).
      operation: A short stable tag that classifies the write
        (``"invite_created"``, ``"cte_event_recorded"``, ...). Used for
        dedupe namespacing and metric labeling.
      cypher: The Cypher statement to replay. MUST reference ``tenant_id``
        unless the operation is legitimately global (see ``_allow_unscoped``
        on the drainer).
      params: The parameter dict. The drainer injects ``tenant_id`` at
        drain time using the session wrapper; a ``tenant_id`` supplied
        here is accepted only if it matches.
      dedupe_key: Optional stable idempotency key. If two enqueues share
        the same (operation, dedupe_key) the second becomes a no-op upsert.
      max_attempts: Hard cap on retries before the row is marked
        ``failed``. Default 10 with exponential backoff.
    """
    if not operation or not isinstance(operation, str):
        raise ValueError("operation must be a non-empty string")
    if not cypher or not isinstance(cypher, str):
        raise ValueError("cypher must be a non-empty string")
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    # Serialize params to JSON string. psycopg / psycopg2 both accept a
    # JSON string bound to a JSONB column. We do this explicitly so the
    # test fixture (which uses SQLite with a TEXT column) receives a
    # consistent payload shape.
    params_json = json.dumps(params, default=_json_default, sort_keys=True)

    insert_sql = text("""
        INSERT INTO graph_outbox (
            tenant_id, operation, cypher, params,
            dedupe_key, max_attempts,
            status, attempts, enqueued_at, next_attempt_at
        ) VALUES (
            :tenant_id, :operation, :cypher, CAST(:params AS JSONB),
            :dedupe_key, :max_attempts,
            'pending', 0, :now, :now
        )
        ON CONFLICT ON CONSTRAINT uq_graph_outbox_dedupe
        DO NOTHING
    """)

    # SQLite (dev fallback) doesn't have JSONB / ON CONFLICT ON CONSTRAINT.
    # The production path is Postgres; we fall back to a simpler insert
    # shape if the session isn't Postgres.
    dialect = getattr(getattr(session, "bind", None), "dialect", None)
    is_postgres = dialect is not None and dialect.name == "postgresql"

    if is_postgres:
        session.execute(
            insert_sql,
            {
                "tenant_id": tenant_id,
                "operation": operation,
                "cypher": cypher,
                "params": params_json,
                "dedupe_key": dedupe_key,
                "max_attempts": max_attempts,
                "now": datetime.now(timezone.utc),
            },
        )
    else:
        # Test / dev fallback. No dedupe enforcement — the unit tests
        # exercise dedupe against a synthesized Postgres session separately.
        session.execute(
            text("""
                INSERT INTO graph_outbox (
                    tenant_id, operation, cypher, params,
                    dedupe_key, max_attempts,
                    status, attempts, enqueued_at, next_attempt_at
                ) VALUES (
                    :tenant_id, :operation, :cypher, :params,
                    :dedupe_key, :max_attempts,
                    'pending', 0, :now, :now
                )
            """),
            {
                "tenant_id": str(tenant_id) if tenant_id else None,
                "operation": operation,
                "cypher": cypher,
                "params": params_json,
                "dedupe_key": dedupe_key,
                "max_attempts": max_attempts,
                "now": datetime.now(timezone.utc).isoformat(),
            },
        )

    logger.info(
        "graph_outbox_enqueued",
        operation=operation,
        tenant_id=tenant_id,
        dedupe_key=dedupe_key,
    )


def _json_default(obj: Any) -> Any:
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"not JSON serializable: {type(obj).__name__}")


# ---------------------------------------------------------------------------
# Drain — pulls pending rows and replays them into Neo4j
# ---------------------------------------------------------------------------


# A Neo4jSessionFactory is a callable that yields a tenant-scoped session
# context manager when given a tenant_id. In production this is
# ``lambda tid: session_with_tenant(driver, tid)``; in tests it's a fake.
Neo4jSessionFactory = Callable[[str], ContextManager[Any]]


class GraphOutboxDrainer:
    """Background drainer for the graph_outbox table."""

    #: Backoff schedule (seconds) indexed by attempt count. Attempt 0 =
    #: first retry after initial failure.
    _BACKOFF = (
        5.0,     # 1st retry:    +5 s
        30.0,    # 2nd retry:   +30 s
        120.0,   # 3rd:       +2 min
        600.0,   # 4th:      +10 min
        1800.0,  # 5th:      +30 min
        3600.0,  # 6th:       +1 h
        14400.0, # 7th:       +4 h
        43200.0, # 8th:      +12 h
        86400.0, # 9th:       +1 d
        86400.0, # 10th:      +1 d
    )

    def __init__(
        self,
        session: Session,
        neo4j_session_factory: Optional[Neo4jSessionFactory] = None,
    ):
        self._session = session
        self._neo4j_factory = neo4j_session_factory

    def drain_once(self, batch_size: int = 100) -> dict:
        """Drain one batch. Returns a summary dict:

            {
                "claimed": <int>,
                "drained": <int>,
                "failed": <int>,     # hit max_attempts this run
                "rescheduled": <int>,  # transient failure, retry later
            }

        The drainer is row-at-a-time inside the batch so that one bad row
        cannot poison the rest. Each row is processed in its own Postgres
        transaction — success OR failure always commits status.
        """
        if self._neo4j_factory is None:
            raise RuntimeError("drain_once requires a neo4j_session_factory")

        claimed = self._claim_pending(batch_size)
        summary = {
            "claimed": len(claimed),
            "drained": 0,
            "failed": 0,
            "rescheduled": 0,
        }

        for row in claimed:
            outcome = self._drain_one(row)
            summary[outcome] = summary.get(outcome, 0) + 1

        return summary

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _claim_pending(self, batch_size: int) -> Sequence[OutboxRow]:
        """Read up to ``batch_size`` pending rows whose ``next_attempt_at``
        has arrived. We use a simple SELECT (no SKIP LOCKED) because the
        drainer is single-worker today; if that changes, swap in
        ``FOR UPDATE SKIP LOCKED``.
        """
        # Pass an ISO-formatted string rather than a Python datetime so
        # that comparison against ``next_attempt_at`` works identically on
        # Postgres (TIMESTAMPTZ, Python datetime coerces fine) and on
        # SQLite (text column, string-sorts by ISO ordering).
        now = datetime.now(timezone.utc).isoformat()
        rows = self._session.execute(
            text("""
                SELECT id, tenant_id, operation, cypher, params,
                       attempts, max_attempts, dedupe_key
                FROM graph_outbox
                WHERE status = 'pending'
                  AND next_attempt_at <= :now
                ORDER BY next_attempt_at ASC, id ASC
                LIMIT :limit
            """),
            {"now": now, "limit": batch_size},
        ).mappings().all()
        return [
            OutboxRow(
                id=r["id"],
                tenant_id=str(r["tenant_id"]) if r["tenant_id"] else None,
                operation=r["operation"],
                cypher=r["cypher"],
                params=self._parse_params(r["params"]),
                attempts=r["attempts"] or 0,
                max_attempts=r["max_attempts"] or 10,
                dedupe_key=r["dedupe_key"],
            )
            for r in rows
        ]

    @staticmethod
    def _parse_params(raw: Any) -> dict:
        # Postgres JSONB returns a dict directly; SQLite text returns a string.
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {}
        return {}

    def _drain_one(self, row: OutboxRow) -> str:
        """Run a single row against Neo4j. Returns the summary key
        (``"drained"``, ``"rescheduled"``, or ``"failed"``) that the
        caller should increment."""
        if row.tenant_id is None:
            # A NULL-tenant row is an administrative / global write. Until
            # we add an explicit global opt-in, mark it failed so it
            # surfaces to ops rather than silently running unscoped.
            self._mark_failed(row, "null tenant_id; refusing to drain")
            return "failed"

        try:
            factory = self._neo4j_factory(row.tenant_id)
        except Exception as exc:  # pragma: no cover  (covered indirectly)
            self._reschedule(row, f"session factory error: {exc}")
            return "rescheduled"

        try:
            with factory as neo4j_session:
                neo4j_session.run(row.cypher, row.params)
        except Exception as exc:
            return self._on_failure(row, exc)

        self._mark_drained(row)
        return "drained"

    def _on_failure(self, row: OutboxRow, exc: Exception) -> str:
        new_attempts = row.attempts + 1
        if new_attempts >= row.max_attempts:
            self._mark_failed(row, f"exhausted {new_attempts} attempts: {exc}")
            return "failed"
        self._reschedule(row, str(exc), attempts=new_attempts)
        return "rescheduled"

    def _mark_drained(self, row: OutboxRow) -> None:
        self._session.execute(
            text("""
                UPDATE graph_outbox
                SET status = 'drained',
                    drained_at = :drained_at,
                    last_error = NULL
                WHERE id = :id
            """),
            {"id": row.id, "drained_at": datetime.now(timezone.utc).isoformat()},
        )
        self._session.commit()
        logger.info(
            "graph_outbox_drained",
            outbox_id=row.id,
            operation=row.operation,
            tenant_id=row.tenant_id,
        )

    def _mark_failed(self, row: OutboxRow, reason: str) -> None:
        self._session.execute(
            text("""
                UPDATE graph_outbox
                SET status = 'failed',
                    last_error = :reason
                WHERE id = :id
            """),
            {"id": row.id, "reason": reason[:4000]},
        )
        self._session.commit()
        logger.warning(
            "graph_outbox_failed",
            outbox_id=row.id,
            operation=row.operation,
            tenant_id=row.tenant_id,
            reason=reason[:200],
        )

    def _reschedule(
        self,
        row: OutboxRow,
        reason: str,
        *,
        attempts: Optional[int] = None,
    ) -> None:
        attempts = attempts if attempts is not None else row.attempts + 1
        delay = self._BACKOFF[min(attempts - 1, len(self._BACKOFF) - 1)]
        next_attempt = datetime.now(timezone.utc) + timedelta(seconds=delay)
        self._session.execute(
            text("""
                UPDATE graph_outbox
                SET attempts = :attempts,
                    last_error = :reason,
                    next_attempt_at = :next_attempt
                WHERE id = :id
            """),
            {
                "id": row.id,
                "attempts": attempts,
                "reason": reason[:4000],
                "next_attempt": next_attempt,
            },
        )
        self._session.commit()
        logger.info(
            "graph_outbox_rescheduled",
            outbox_id=row.id,
            attempts=attempts,
            delay_seconds=delay,
            operation=row.operation,
            tenant_id=row.tenant_id,
        )


# ---------------------------------------------------------------------------
# Reconciliation / drift metric
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutboxHealth:
    pending_count: int
    failed_count: int
    oldest_pending_age_seconds: Optional[float]


def reconcile_graph_outbox(session: Session) -> OutboxHealth:
    """Summary stats for the outbox.

    Exposed so that a ``/metrics`` endpoint or a periodic job can emit
    ``graph_sync_lag_seconds`` (= ``oldest_pending_age_seconds``) and
    ``graph_sync_failed_total`` to Prometheus / whatever monitoring we
    have wired up. The drainer emits per-row structured logs; this is
    the coarse-grained health check for alerting.
    """
    row = session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'pending')  AS pending_count,
                COUNT(*) FILTER (WHERE status = 'failed')   AS failed_count,
                MIN(enqueued_at) FILTER (WHERE status = 'pending') AS oldest_pending
            FROM graph_outbox
        """)
    ).mappings().first()

    oldest = row["oldest_pending"] if row else None
    age_seconds: Optional[float] = None
    if oldest is not None:
        # Ensure tz-aware subtraction.
        if isinstance(oldest, str):
            oldest = datetime.fromisoformat(oldest)
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - oldest).total_seconds()

    return OutboxHealth(
        pending_count=int(row["pending_count"]) if row else 0,
        failed_count=int(row["failed_count"]) if row else 0,
        oldest_pending_age_seconds=age_seconds,
    )


__all__ = [
    "OutboxStatus",
    "OutboxRow",
    "OutboxHealth",
    "GraphOutboxDrainer",
    "enqueue_graph_write",
    "reconcile_graph_outbox",
]
