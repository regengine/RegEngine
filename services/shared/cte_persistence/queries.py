"""Read path for the CTE persistence layer — FDA export and graph-sync queries.

Mechanically extracted from ``core.py`` (file split — no logic changes).
``core.CTEPersistence`` composes this mixin. Names that used to be module
globals of ``core.py`` (e.g. ``logger``) are resolved late through the
``core`` module (method-local ``from . import core as _core``) so existing
monkeypatch / ``patch("...cte_persistence.core.X")`` targets keep affecting
this code exactly as before the split.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.exc import (
    DatabaseError,
    OperationalError,
    ProgrammingError,
)


def _is_missing_table_error(exc: DatabaseError) -> bool:
    """True only for "relation/table does not exist" — the documented
    fresh-DB bootstrap case.

    Postgres: UndefinedTable, pgcode ``42P01`` (a ``ProgrammingError``).
    SQLite: "no such table" (an ``OperationalError``). Anything else —
    transient connectivity loss, permission/privilege errors, undefined
    columns — is NOT a bootstrap condition and must fail closed.
    """
    orig = getattr(exc, "orig", None)
    if getattr(orig, "pgcode", None) == "42P01":
        return True
    msg = str(orig if orig is not None else exc).lower()
    if "no such table" in msg:
        return True
    return "relation" in msg and "does not exist" in msg


class QueryPathMixin:
    """Read-path methods — mixed into :class:`core.CTEPersistence`."""

    # ------------------------------------------------------------------
    # Read Path — FDA Export Queries
    # ------------------------------------------------------------------

    # Default recursion depth for _expand_tlcs_via_transformation_links
    # / query_events_by_tlc.  Bounded for two reasons:
    #   1. Postgres recursive CTE cost grows fast with depth; >10 hops
    #      on a dense transformation graph can blow memory.
    #   2. FDA §1.1350(c) records requests must return within 24 hours;
    #      we don't want a single misbehaving lot to DoS export.
    # Kept as a class attribute so tests can monkey-patch it cleanly.
    DEFAULT_TRAVERSAL_DEPTH: int = 5

    def _expand_tlcs_via_transformation_links(
        self,
        tenant_id: str,
        seed_tlc: str,
        depth: Optional[int] = None,
    ) -> List[str]:
        """Return all TLCs reachable from seed_tlc through transformation_links.

        Walks both directions (forward: seed → outputs, backward: seed → inputs)
        using a breadth-first traversal capped at ``depth`` hops.  Returns the
        full set of TLCs including the seed itself.

        Args:
            tenant_id: RLS tenant identifier.
            seed_tlc: TLC to expand from.
            depth: Max recursion depth.  Defaults to
                ``DEFAULT_TRAVERSAL_DEPTH`` (5) — previously hard-coded
                in the signature, now a class attribute so callers and
                tests can raise/lower it without patching the signature
                (#1322).

        Falls back to ``[seed_tlc]`` ONLY when the transformation_links
        table does not exist (fresh DB bootstrapping). Every other SQL
        error — including transient connectivity loss mid-export — is
        re-raised so it surfaces in callers instead of silently
        truncating the trace to the seed lot while the export renders as
        complete. Prior code swallowed ``except Exception`` here, which
        masked real FDA export bugs (#1322); the unreachable-DB carve-out
        was removed for the same reason.
        """
        from . import core as _core

        max_depth = depth if depth is not None else self.DEFAULT_TRAVERSAL_DEPTH
        if max_depth < 0:
            raise ValueError(f"depth must be >= 0, got {max_depth}")

        try:
            # Note: use CAST(:tlc AS text) rather than :tlc::text — SQLAlchemy's
            # text() parameter parser misidentifies :param::cast as a single token,
            # silently dropping the :tlc binding and producing a SyntaxError.
            #
            # The recursive term MUST be a single branch. Postgres splits a
            # recursive CTE at the LAST top-level UNION, so writing the walk as
            # seed UNION forward UNION backward puts the forward branch inside
            # the non-recursive term and every execution fails with
            # InvalidRecursion ("recursive reference ... must not appear within
            # its non-recursive term"). Both directions are therefore walked in
            # one branch: join a link whichever side matches, emit the other.
            rows = self.session.execute(
                text("""
                    WITH RECURSIVE tlc_graph(tlc, depth) AS (
                        -- Seed
                        SELECT CAST(:tlc AS text), 0
                        UNION
                        -- Walk both directions: input → output and output → input
                        SELECT CASE WHEN tg.tlc = tl.input_tlc
                                    THEN tl.output_tlc
                                    ELSE tl.input_tlc
                               END,
                               tg.depth + 1
                        FROM   fsma.transformation_links tl
                        JOIN   tlc_graph tg ON tg.tlc IN (tl.input_tlc, tl.output_tlc)
                        WHERE  tl.tenant_id = :tid AND tg.depth < :max_depth
                    )
                    SELECT DISTINCT tlc FROM tlc_graph
                """),
                {"tid": tenant_id, "tlc": seed_tlc, "max_depth": max_depth},
            ).fetchall()
            return [r[0] for r in rows] if rows else [seed_tlc]
        except (ProgrammingError, OperationalError) as e:
            if not _is_missing_table_error(e):
                # Fail closed (#1322 spirit): transient connectivity loss or
                # permission errors mid-traversal must surface as an export
                # failure, not silently truncate the trace to the seed lot
                # while the export renders 200-complete.
                _core.logger.error(
                    "transformation_links_traversal_failed",
                    extra={
                        "tenant_id": tenant_id,
                        "seed_tlc": seed_tlc,
                        "error": str(e),
                    },
                )
                try:
                    self.session.rollback()
                except DatabaseError:
                    _core.logger.debug("Rollback failed in recovery handler", exc_info=True)
                raise
            # The transformation_links table does not exist — typical on
            # environments that have not run the v043+ migrations yet.
            # Degrade gracefully to "no graph" rather than failing the
            # FDA export entirely.  Rollback so the session is reusable.
            _core.logger.info(
                "transformation_links_table_missing",
                extra={
                    "tenant_id": tenant_id,
                    "seed_tlc": seed_tlc,
                    "error": str(e),
                },
            )
            try:
                self.session.rollback()
            except DatabaseError:
                _core.logger.debug("Rollback failed in recovery handler", exc_info=True)
            return [seed_tlc]

    def query_events_by_tlc(
        self,
        tenant_id: str,
        tlc: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        follow_transformations: bool = True,
        max_depth: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query CTE events for a TLC within a date range.

        When follow_transformations=True (default), also returns events for all
        TLCs linked via fsma.transformation_links — both upstream inputs and
        downstream outputs.  This satisfies FDA §1.1350(c): a 24-hour records
        request must include the full traceability chain through transformations.

        Set follow_transformations=False for point queries that should not
        expand the result set (e.g. internal dedup checks).

        Args:
            max_depth: Optional override for the transformation-link
                recursion depth.  Defaults to
                ``CTEPersistence.DEFAULT_TRAVERSAL_DEPTH`` (5 hops) —
                see #1322; previously hard-coded.  Raising this trades
                correctness-for-deep-chains against query cost.

        SECURITY (#1321): Previously this method did not call
        ``set_tenant_context``; it relied on the caller having set the
        RLS context and on the explicit ``tenant_id = :tid`` predicate
        in the WHERE.  A caller that forgot to set the context — or who
        passed an attacker-influenced ``tenant_id`` — could cross
        tenant boundaries when the RLS fail-closed default is not
        installed.  We now set the context unconditionally (matching
        ``query_all_events``) and keep the explicit predicate as
        defense-in-depth.
        """
        from . import core as _core

        self.set_tenant_context(tenant_id)

        # Resolve the full set of TLCs to query
        if follow_transformations:
            tlc_set = self._expand_tlcs_via_transformation_links(
                tenant_id,
                tlc,
                depth=max_depth,
            )
        else:
            tlc_set = [tlc]

        params: Dict[str, Any] = {"tid": tenant_id}
        tlc_placeholders = ", ".join(f":tlc_{i}" for i in range(len(tlc_set)))
        for i, t in enumerate(tlc_set):
            params[f"tlc_{i}"] = t

        where_clauses = [
            "tenant_id = :tid",
            f"traceability_lot_code IN ({tlc_placeholders})",
            "validation_status != 'rejected'",
        ]

        if start_date:
            where_clauses.append("event_timestamp >= :start_date")
            params["start_date"] = start_date
        if end_date:
            where_clauses.append("event_timestamp <= :end_date")
            params["end_date"] = end_date

        where = " AND ".join(where_clauses)

        rows = self.session.execute(
            text(f"""
                SELECT
                    e.id, e.event_type, e.traceability_lot_code,
                    e.product_description, e.quantity, e.unit_of_measure,
                    e.location_gln, e.location_name,
                    e.event_timestamp, e.sha256_hash, e.chain_hash,
                    e.source, e.validation_status, e.ingested_at,
                    e.event_entry_timestamp
                FROM fsma.cte_events e
                WHERE {where}
                ORDER BY e.event_timestamp ASC
            """),
            params,
        ).fetchall()

        # Tag each event with whether it's the queried TLC or a linked one
        seed_tlc = tlc  # original query TLC, before expansion
        events = []
        for row in rows:
            row_tlc = row[2]
            event = {
                "id": str(row[0]),
                "event_type": row[1],
                "traceability_lot_code": row_tlc,
                "product_description": row[3],
                "quantity": row[4],
                "unit_of_measure": row[5],
                "location_gln": row[6],
                "location_name": row[7],
                "event_timestamp": row[8].isoformat() if row[8] else None,
                "sha256_hash": row[9],
                "chain_hash": row[10],
                "source": row[11],
                "validation_status": row[12],
                "ingested_at": row[13].isoformat() if row[13] else None,
                "event_entry_timestamp": row[14].isoformat() if row[14] else None,
                "kdes": {},
                # Trace relationship metadata (used in FDA export CSV)
                "trace_seed_tlc": seed_tlc,
                "trace_relationship": ("queried" if row_tlc == seed_tlc else "linked_via_transformation"),
            }
            events.append(event)

        # Bulk-fetch KDEs for all events in one query (avoids N+1)
        if events:
            event_ids = [e["id"] for e in events]
            kde_map: Dict[str, Dict[str, str]] = {eid: {} for eid in event_ids}
            for chunk_start in range(0, len(event_ids), 100):
                chunk = event_ids[chunk_start : chunk_start + 100]
                placeholders = ", ".join(f":eid_{i}" for i in range(len(chunk)))
                kde_params: Dict[str, Any] = {f"eid_{i}": eid for i, eid in enumerate(chunk)}
                kde_params["tid"] = tenant_id
                kde_rows = self.session.execute(
                    text(f"""
                        SELECT cte_event_id, kde_key, kde_value
                        FROM fsma.cte_kdes
                        WHERE tenant_id = :tid AND cte_event_id IN ({placeholders})
                    """),
                    kde_params,
                ).fetchall()
                for kr in kde_rows:
                    kde_map[str(kr[0])][kr[1]] = kr[2]
            for event in events:
                event["kdes"] = kde_map.get(event["id"], {})

        # FSMA 204 / NIST AU-2 read-access audit (#1033)
        # Emit a structured log record for every KDE read so that
        # SIEM / log-aggregation can reconstruct who accessed which records.
        # We use structlog-style kwargs on the stdlib logger so the record
        # appears in the service's structured log stream without requiring
        # an async AuditLogger instance in this sync method.
        if events:
            _core.logger.info(
                "kde_read_access",
                extra={
                    "audit": True,
                    "event_type": "kde_read_access",
                    "tenant_id": tenant_id,
                    "query_tlc": tlc,
                    "event_count": len(events),
                    "event_ids": [e["id"] for e in events],
                    "source": "query_events_by_tlc",
                    "fsma_au2": True,
                },
            )

        return events

    def _expand_tlcs_via_transformation_links_batch(
        self,
        tenant_id: str,
        seed_tlcs: List[str],
        depth: Optional[int] = None,
    ) -> List[str]:
        """Batch variant of ``_expand_tlcs_via_transformation_links`` (#2515).

        Expands *all* ``seed_tlcs`` through ``fsma.transformation_links`` in a
        single ``WITH RECURSIVE`` traversal instead of one recursive-CTE
        round-trip per seed. The seed set is materialized as a ``VALUES`` list
        feeding the recursion base case; the bidirectional walk and depth cap
        are identical to the single-seed method. Returns the full reachable TLC
        set (including the seeds), de-duplicated.

        Degrades to the seed set ONLY when ``transformation_links`` does not
        exist (fresh DB bootstrapping) — mirroring the single-seed fallback.
        Any other SQL error, including transient connectivity loss, is
        re-raised (fail closed) rather than silently truncating the trace.
        """
        from . import core as _core

        if not seed_tlcs:
            return []

        max_depth = depth if depth is not None else self.DEFAULT_TRAVERSAL_DEPTH
        if max_depth < 0:
            raise ValueError(f"depth must be >= 0, got {max_depth}")

        seeds = list(dict.fromkeys(seed_tlcs))  # preserve order, drop dupes
        seed_placeholders = ", ".join(f"(:seed_{i})" for i in range(len(seeds)))
        params: Dict[str, Any] = {"tid": tenant_id, "max_depth": max_depth}
        for i, s in enumerate(seeds):
            params[f"seed_{i}"] = s

        try:
            # Single recursive branch for the same reason as the single-seed
            # twin above: Postgres splits a recursive CTE at the LAST top-level
            # UNION, so a seed/forward/backward three-branch UNION fails with
            # InvalidRecursion on every execution.
            rows = self.session.execute(
                text(f"""
                    WITH RECURSIVE seeds(tlc) AS (
                        VALUES {seed_placeholders}
                    ),
                    tlc_graph(tlc, depth) AS (
                        -- Seed set
                        SELECT CAST(tlc AS text), 0 FROM seeds
                        UNION
                        -- Walk both directions: input → output and output → input
                        SELECT CASE WHEN tg.tlc = tl.input_tlc
                                    THEN tl.output_tlc
                                    ELSE tl.input_tlc
                               END,
                               tg.depth + 1
                        FROM   fsma.transformation_links tl
                        JOIN   tlc_graph tg ON tg.tlc IN (tl.input_tlc, tl.output_tlc)
                        WHERE  tl.tenant_id = :tid AND tg.depth < :max_depth
                    )
                    SELECT DISTINCT tlc FROM tlc_graph
                """),
                params,
            ).fetchall()
            return [r[0] for r in rows] if rows else seeds
        except (ProgrammingError, OperationalError) as e:
            if not _is_missing_table_error(e):
                # Fail closed — see the single-seed twin above.
                _core.logger.error(
                    "transformation_links_traversal_failed",
                    extra={
                        "tenant_id": tenant_id,
                        "seed_count": len(seeds),
                        "error": str(e),
                    },
                )
                try:
                    self.session.rollback()
                except DatabaseError:
                    _core.logger.debug("Rollback failed in recovery handler", exc_info=True)
                raise
            _core.logger.info(
                "transformation_links_table_missing",
                extra={
                    "tenant_id": tenant_id,
                    "seed_count": len(seeds),
                    "error": str(e),
                },
            )
            try:
                self.session.rollback()
            except DatabaseError:
                _core.logger.debug("Rollback failed in recovery handler", exc_info=True)
            return seeds

    def query_events_by_tlcs(
        self,
        tenant_id: str,
        tlcs: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        follow_transformations: bool = True,
        max_depth: Optional[int] = None,
        limit: int = 10000,
    ) -> List[Dict[str, Any]]:
        """Batch-query CTE events for many TLCs in a bounded number of queries.

        This is the set-based replacement for calling ``query_events_by_tlc``
        once per distinct lot code (#2515). Regardless of how many seed TLCs
        are passed, it issues a constant number of DB round-trips:

          1. one recursive-CTE transformation-link expansion for the whole set
             (when ``follow_transformations`` is True),
          2. one bounded events ``SELECT`` over the expanded TLC set, and
          3. chunked KDE fetches (100 event ids per chunk, as elsewhere).

        ``limit`` caps the materialized event set so a tenant with many events
        per lot cannot exhaust memory; rows are ordered ``event_timestamp ASC``
        and truncated server-side. ``trace_relationship`` is set per row based
        on whether the row's TLC was one of the original seeds.

        Returns ``[]`` for an empty ``tlcs`` input without touching the DB.
        """
        from . import core as _core

        seeds = list(dict.fromkeys(tlcs))
        if not seeds:
            return []

        self.set_tenant_context(tenant_id)

        if follow_transformations:
            tlc_set = self._expand_tlcs_via_transformation_links_batch(
                tenant_id,
                seeds,
                depth=max_depth,
            )
        else:
            tlc_set = seeds

        seed_set = set(seeds)

        params: Dict[str, Any] = {"tid": tenant_id, "lim": limit}
        tlc_placeholders = ", ".join(f":tlc_{i}" for i in range(len(tlc_set)))
        for i, t in enumerate(tlc_set):
            params[f"tlc_{i}"] = t

        where_clauses = [
            "tenant_id = :tid",
            f"traceability_lot_code IN ({tlc_placeholders})",
            "validation_status != 'rejected'",
        ]
        if start_date:
            where_clauses.append("event_timestamp >= :start_date")
            params["start_date"] = start_date
        if end_date:
            where_clauses.append("event_timestamp <= :end_date")
            params["end_date"] = end_date

        where = " AND ".join(where_clauses)

        rows = self.session.execute(
            text(f"""
                SELECT
                    e.id, e.event_type, e.traceability_lot_code,
                    e.product_description, e.quantity, e.unit_of_measure,
                    e.location_gln, e.location_name,
                    e.event_timestamp, e.sha256_hash, e.chain_hash,
                    e.source, e.validation_status, e.ingested_at,
                    e.event_entry_timestamp
                FROM fsma.cte_events e
                WHERE {where}
                ORDER BY e.event_timestamp ASC
                LIMIT :lim
            """),
            params,
        ).fetchall()

        events = []
        for row in rows:
            row_tlc = row[2]
            events.append(
                {
                    "id": str(row[0]),
                    "event_type": row[1],
                    "traceability_lot_code": row_tlc,
                    "product_description": row[3],
                    "quantity": row[4],
                    "unit_of_measure": row[5],
                    "location_gln": row[6],
                    "location_name": row[7],
                    "event_timestamp": row[8].isoformat() if row[8] else None,
                    "sha256_hash": row[9],
                    "chain_hash": row[10],
                    "source": row[11],
                    "validation_status": row[12],
                    "ingested_at": row[13].isoformat() if row[13] else None,
                    "event_entry_timestamp": row[14].isoformat() if row[14] else None,
                    "kdes": {},
                    "trace_relationship": ("queried" if row_tlc in seed_set else "linked_via_transformation"),
                }
            )

        # Bulk-fetch KDEs for all events (chunked, avoids N+1) — same pattern
        # as query_events_by_tlc.
        if events:
            event_ids = [e["id"] for e in events]
            kde_map: Dict[str, Dict[str, str]] = {eid: {} for eid in event_ids}
            for chunk_start in range(0, len(event_ids), 100):
                chunk = event_ids[chunk_start : chunk_start + 100]
                placeholders = ", ".join(f":eid_{i}" for i in range(len(chunk)))
                kde_params: Dict[str, Any] = {f"eid_{i}": eid for i, eid in enumerate(chunk)}
                kde_params["tid"] = tenant_id
                kde_rows = self.session.execute(
                    text(f"""
                        SELECT cte_event_id, kde_key, kde_value
                        FROM fsma.cte_kdes
                        WHERE tenant_id = :tid AND cte_event_id IN ({placeholders})
                    """),
                    kde_params,
                ).fetchall()
                for kr in kde_rows:
                    kde_map[str(kr[0])][kr[1]] = kr[2]
            for event in events:
                event["kdes"] = kde_map.get(event["id"], {})

        # FSMA 204 / NIST AU-2 read-access audit (#1033)
        if events:
            _core.logger.info(
                "kde_read_access",
                extra={
                    "audit": True,
                    "event_type": "kde_read_access",
                    "tenant_id": tenant_id,
                    "seed_tlc_count": len(seeds),
                    "event_count": len(events),
                    "event_ids": [e["id"] for e in events],
                    "source": "query_events_by_tlcs",
                    "fsma_au2": True,
                },
            )

        return events

    def query_all_events(
        self,
        tenant_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Query CTE events with optional filters. Returns (events, total_count).

        Sets RLS tenant context for consistency with class contract. The explicit
        WHERE tenant_id clause is retained as defense-in-depth.
        """
        from . import core as _core

        self.set_tenant_context(tenant_id)
        params: Dict[str, Any] = {"tid": tenant_id, "lim": limit, "off": offset}
        where_clauses = ["tenant_id = :tid"]
        if start_date:
            where_clauses.append("event_timestamp >= :start_date")
            params["start_date"] = start_date
        if end_date:
            where_clauses.append("event_timestamp <= :end_date")
            params["end_date"] = end_date
        if event_type:
            where_clauses.append("event_type = :event_type")
            params["event_type"] = event_type

        # `where` is composed exclusively from static string literals above;
        # all dynamic values use :named bind parameters -- no user input is
        # ever interpolated into the SQL text itself.
        where = " AND ".join(where_clauses)

        # Get total count
        count_sql = "SELECT COUNT(*) FROM fsma.cte_events WHERE " + where
        count_row = self.session.execute(
            text(count_sql),
            params,
        ).fetchone()
        total = count_row[0] if count_row else 0

        # Get page of results
        select_sql = (
            "SELECT id, event_type, traceability_lot_code,"
            "       product_description, quantity, unit_of_measure,"
            "       event_timestamp, validation_status, sha256_hash"
            " FROM fsma.cte_events"
            " WHERE " + where + " ORDER BY event_timestamp DESC"
            " LIMIT :lim OFFSET :off"
        )
        rows = self.session.execute(
            text(select_sql),
            params,
        ).fetchall()

        events = [
            {
                "id": str(r[0]),
                "event_type": r[1],
                "traceability_lot_code": r[2],
                "product_description": r[3],
                "quantity": r[4],
                "unit_of_measure": r[5],
                "event_timestamp": r[6].isoformat() if r[6] else None,
                "validation_status": r[7],
                "sha256_hash": r[8],
            }
            for r in rows
        ]

        # FSMA 204 / NIST AU-2 read-access audit (#1033)
        if events:
            _core.logger.info(
                "kde_read_access",
                extra={
                    "audit": True,
                    "event_type": "kde_read_access",
                    "tenant_id": tenant_id,
                    "event_count": len(events),
                    "total_matching": total,
                    "event_ids": [e["id"] for e in events],
                    "source": "query_all_events",
                    "fsma_au2": True,
                },
            )

        return events, total

    # ------------------------------------------------------------------
    # Graph Sync Support
    # ------------------------------------------------------------------

    def get_unsynced_events(
        self,
        tenant_id: str,
        since_sequence: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get CTE events that need to be synced to Neo4j.

        Returns events with their KDEs, ordered by chain sequence,
        starting from the given sequence number.
        """
        rows = self.session.execute(
            text("""
                SELECT
                    e.id, e.event_type, e.traceability_lot_code,
                    e.product_description, e.quantity, e.unit_of_measure,
                    e.location_gln, e.location_name, e.event_timestamp,
                    e.source, h.sequence_num
                FROM fsma.cte_events e
                JOIN fsma.hash_chain h ON h.cte_event_id = e.id
                WHERE e.tenant_id = :tid
                  AND h.sequence_num > :since
                  AND e.validation_status != 'rejected'
                ORDER BY h.sequence_num ASC
                LIMIT :lim
            """),
            {"tid": tenant_id, "since": since_sequence, "lim": limit},
        ).fetchall()

        events = []
        for row in rows:
            events.append(
                {
                    "id": str(row[0]),
                    "event_type": row[1],
                    "traceability_lot_code": row[2],
                    "product_description": row[3],
                    "quantity": row[4],
                    "unit_of_measure": row[5],
                    "location_gln": row[6],
                    "location_name": row[7],
                    "event_timestamp": row[8].isoformat() if row[8] else None,
                    "source": row[9],
                    "sequence_num": row[10],
                    "kdes": {},
                }
            )

        # Bulk-fetch KDEs for all events in one query (avoids N+1)
        if events:
            event_ids = [e["id"] for e in events]
            kde_map: Dict[str, Dict[str, str]] = {eid: {} for eid in event_ids}
            for chunk_start in range(0, len(event_ids), 100):
                chunk = event_ids[chunk_start : chunk_start + 100]
                placeholders = ", ".join(f":eid_{i}" for i in range(len(chunk)))
                kde_params: Dict[str, Any] = {f"eid_{i}": eid for i, eid in enumerate(chunk)}
                kde_params["tid"] = tenant_id
                kde_rows = self.session.execute(
                    text(f"""
                        SELECT cte_event_id, kde_key, kde_value
                        FROM fsma.cte_kdes
                        WHERE tenant_id = :tid AND cte_event_id IN ({placeholders})
                    """),
                    kde_params,
                ).fetchall()
                for kr in kde_rows:
                    kde_map[str(kr[0])][kr[1]] = kr[2]
            for event in events:
                event["kdes"] = kde_map.get(event["id"], {})

        return events
