"""
Canonical Event Store — write orchestration, read path, and trace queries.

Persists TraceabilityEvents to fsma.traceability_events with idempotency,
hash chain integrity, and ingestion run tracking.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from shared.canonical_event import (
    TraceabilityEvent,
    IngestionRun,
    IngestionRunStatus,
    RawPayloadTooLargeError,
    _raw_payload_max_bytes,
)
from shared.cte_persistence import compute_chain_hash
from shared.canonical_persistence.models import CanonicalStoreResult
from shared.canonical_persistence import legacy_dual_write as migration

logger = logging.getLogger("canonical-persistence")


class CanonicalEventStore:
    """
    Database-backed persistence for canonical TraceabilityEvents.

    Writes to fsma.traceability_events (canonical) and optionally
    dual-writes to fsma.cte_events (legacy) during migration.
    """

    def __init__(self, session: Session, dual_write: bool = True, skip_chain_write: bool = False):
        self.session = session
        self.dual_write = dual_write
        self.skip_chain_write = skip_chain_write

    def _session_dialect_name(self) -> str:
        bind = getattr(self.session, "bind", None)
        if bind is None:
            try:
                bind = self.session.get_bind()
            except Exception:
                return ""
        dialect = getattr(bind, "dialect", None)
        name = getattr(dialect, "name", "") if dialect is not None else ""
        return str(name or "").lower()

    def set_tenant_context(self, tenant_id: str) -> None:
        """Set the RLS tenant context for this session."""
        if self._session_dialect_name() == "sqlite":
            return
        self.session.execute(
            text("SET LOCAL app.tenant_id = :tid"),
            {"tid": tenant_id},
        )

    # ------------------------------------------------------------------
    # Per-tenant Chain Serialization (fix #1251)
    # ------------------------------------------------------------------

    def _acquire_chain_lock(self, tenant_id: str) -> None:
        """Acquire a per-tenant transaction-scoped advisory lock.

        Two writers inserting events for the same tenant concurrently
        would otherwise both read the same chain head and compute the
        same ``next_sequence``, producing duplicate sequence numbers
        (or a UNIQUE violation if a defense-in-depth constraint is
        added).  pg_advisory_xact_lock serializes the chain-growth
        critical section per tenant; the lock is released automatically
        at COMMIT / ROLLBACK.

        hashtext() returns an int4 which is what pg_advisory_xact_lock
        expects.  Collisions across tenants are harmless — they just
        serialize unrelated tenants occasionally, never cross-write.
        """
        if self._session_dialect_name() == "sqlite":
            return
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:tid))"),
            {"tid": tenant_id},
        )

    # ------------------------------------------------------------------
    # Ingestion Run Management
    # ------------------------------------------------------------------

    def create_ingestion_run(self, run: IngestionRun) -> str:
        """Create an ingestion run record. Returns the run ID."""
        # --- Set RLS tenant context (fix #1265) ---
        # INSERTs on fsma.ingestion_runs are governed by tenant_isolation
        # policies; set the GUC so the INSERT is not silently rejected.
        self.set_tenant_context(str(run.tenant_id))
        self.session.execute(
            text("""
                INSERT INTO fsma.ingestion_runs (
                    id, tenant_id, source_system, source_file_name,
                    source_file_hash, source_file_size, record_count,
                    mapper_version, schema_version, status, initiated_by
                ) VALUES (
                    :id, :tenant_id, :source_system, :source_file_name,
                    :source_file_hash, :source_file_size, :record_count,
                    :mapper_version, :schema_version, :status, :initiated_by
                )
            """),
            {
                "id": str(run.id),
                "tenant_id": str(run.tenant_id),
                "source_system": run.source_system.value,
                "source_file_name": run.source_file_name,
                "source_file_hash": run.source_file_hash,
                "source_file_size": run.source_file_size,
                "record_count": run.record_count,
                "mapper_version": run.mapper_version,
                "schema_version": run.schema_version,
                "status": run.status.value,
                "initiated_by": run.initiated_by,
            },
        )
        return str(run.id)

    def complete_ingestion_run(
        self, run_id: str, tenant_id: str, accepted: int, rejected: int,
        errors: Optional[List[Dict]] = None,
    ) -> None:
        """Mark an ingestion run as completed.

        ``tenant_id`` is required (#1263). The previous signature
        accepted only ``run_id`` and the WHERE clause matched only ``id``
        — a caller passing a run_id that belonged to another tenant
        silently mutated cross-tenant state. RLS is not a sufficient
        backstop here because ``set_tenant_context`` is not called by
        callers of this method, only by ``persist_event``.

        Raises:
            ValueError: when no row matched (run does not exist or
                belongs to a different tenant). Fail-loud is preferred to
                a silent UPDATE 0 — callers always have a real run id.
        """
        status = "completed" if rejected == 0 else "partial"
        # Defence in depth: also set RLS context so the policy filter
        # would catch any future regression that stripped the WHERE
        # clause.
        self.set_tenant_context(tenant_id)
        result = self.session.execute(
            text("""
                UPDATE fsma.ingestion_runs
                SET accepted_count = :accepted,
                    rejected_count = :rejected,
                    status = :status,
                    completed_at = NOW(),
                    errors = :errors
                WHERE id = :id
                  AND tenant_id = :tenant_id
            """),
            {
                "id": run_id,
                "tenant_id": tenant_id,
                "accepted": accepted,
                "rejected": rejected,
                "status": status,
                "errors": json.dumps(errors or []),
            },
        )
        if getattr(result, "rowcount", 0) == 0:
            raise ValueError(
                f"complete_ingestion_run: no run matched id={run_id!r} for "
                f"tenant={tenant_id!r}. Either the run does not exist or "
                f"belongs to a different tenant — refusing silent no-op "
                "write (#1263)."
            )

    # ------------------------------------------------------------------
    # Single Event Persistence
    # ------------------------------------------------------------------

    def persist_event(self, event: TraceabilityEvent) -> CanonicalStoreResult:
        """
        Persist a single canonical TraceabilityEvent.

        Handles: idempotency check, hash chain, canonical write,
        dual-write (legacy), hash chain entry, transformation links.
        """
        tenant_id = str(event.tenant_id)

        # --- Set RLS tenant context (fix #1265) ---
        # Every SQL this method runs depends on RLS policies resolving
        # ``get_tenant_context()`` correctly. Call sites can forget to
        # pre-set the GUC, in which case fail-hard policies raise
        # `insufficient_privilege`. Bind it here idempotently so the
        # RLS posture is defence-in-depth, not callsite-discipline.
        self.set_tenant_context(tenant_id)

        if not event.sha256_hash:
            event.prepare_for_persistence()

        # --- Serialize chain growth per-tenant (fix #1251) ---
        # A transaction-scoped advisory lock keyed on the tenant_id hash
        # prevents concurrent persist_event calls from reading the same
        # chain head and producing duplicate sequence_num entries.  The
        # lock is released automatically at COMMIT / ROLLBACK.
        self._acquire_chain_lock(tenant_id)

        # --- Idempotency check (fix #1252) ---
        # We moved the check into the INSERT via ON CONFLICT .. DO NOTHING
        # RETURNING event_id so a losing writer in a race does not abort
        # the transaction with a UNIQUE violation.  If the INSERT returns
        # zero rows we re-SELECT the existing row and return idempotent.
        # However we still short-circuit on an obvious pre-existing key
        # to avoid computing a pointless chain hash when idempotent.
        if event.idempotency_key:
            existing = self.session.execute(
                text("""
                    SELECT event_id, sha256_hash, chain_hash
                    FROM fsma.traceability_events
                    WHERE idempotency_key = :key AND tenant_id = :tid
                """),
                {"key": event.idempotency_key, "tid": tenant_id},
            ).fetchone()

            if existing:
                return CanonicalStoreResult(
                    success=True, event_id=str(existing[0]),
                    sha256_hash=existing[1], chain_hash=existing[2],
                    idempotent=True, errors=[],
                )

        # --- Get chain head ---
        chain_head = self.session.execute(
            text("""
                SELECT chain_hash, sequence_num
                FROM fsma.hash_chain
                WHERE tenant_id = :tid
                ORDER BY sequence_num DESC
                LIMIT 1
                FOR UPDATE
            """),
            {"tid": tenant_id},
        ).fetchone()

        previous_chain_hash = chain_head[0] if chain_head else None
        next_sequence = (chain_head[1] + 1) if chain_head else 1

        chain_hash = compute_chain_hash(event.sha256_hash, previous_chain_hash)
        event.chain_hash = chain_hash

        # --- Insert canonical event (fix #1252: ON CONFLICT DO NOTHING) ---
        # Returns the inserted event_id, sha256_hash, chain_hash on success,
        # or None when a concurrent writer won the idempotency race.  In
        # that case we re-SELECT the winner's row and return idempotent
        # without aborting the surrounding transaction.
        inserted = self._insert_canonical_event(event)
        if inserted is None and event.idempotency_key:
            existing = self.session.execute(
                text("""
                    SELECT event_id, sha256_hash, chain_hash
                    FROM fsma.traceability_events
                    WHERE idempotency_key = :key AND tenant_id = :tid
                """),
                {"key": event.idempotency_key, "tid": tenant_id},
            ).fetchone()
            if existing:
                return CanonicalStoreResult(
                    success=True, event_id=str(existing[0]),
                    sha256_hash=existing[1], chain_hash=existing[2],
                    idempotent=True, errors=[],
                )

        # --- Mark superseded event (fix #1262) ---
        # The previous implementation was check-then-update:
        #   SELECT status ...  then  UPDATE ... WHERE status='active'
        # Between the SELECT and UPDATE another writer could supersede the
        # same row, producing a spurious "already superseded" ValueError
        # for the race-loser even though the intended state change had
        # already been applied.  We collapse to a single authoritative
        # UPDATE ... RETURNING; an empty result (target already superseded
        # or absent for this tenant) is treated as idempotent, not an error.
        if event.supersedes_event_id:
            if event.supersedes_event_id == event.event_id:
                raise ValueError("Event cannot supersede itself")
            self.session.execute(
                text("""
                    UPDATE fsma.traceability_events
                    SET status = 'superseded', amended_at = NOW()
                    WHERE event_id = :superseded_id
                      AND tenant_id = :tid
                      AND status = 'active'
                    RETURNING event_id
                """),
                {"superseded_id": str(event.supersedes_event_id), "tid": tenant_id},
            ).fetchone()
            # No rows => target was already superseded (or does not belong
            # to this tenant).  Both are safe / idempotent outcomes.

        # --- Insert hash chain entry ---
        if not self.skip_chain_write:
            self._insert_chain_entry(
                tenant_id=tenant_id, event_id=str(event.event_id),
                sequence_num=next_sequence, event_hash=event.sha256_hash,
                previous_chain_hash=previous_chain_hash, chain_hash=chain_hash,
            )

        # --- Dual-write to legacy table (TEMPORARY — see migration.py) ---
        # #1277: dual_write_legacy now raises on failure instead of
        # silently returning None. That's intentional — the FDA-export
        # path still reads from the legacy table during migration, so
        # a swallowed failure would silently desync the export from
        # canonical. Letting the exception propagate rolls the
        # surrounding transaction back, so either BOTH tables have
        # the event or NEITHER does. Callers that don't want legacy
        # writes at all must opt out via ``dual_write=False``.
        legacy_id = None
        if self.dual_write:
            legacy_id = migration.dual_write_legacy(self.session, event)

        # --- Create transformation links ---
        self._create_transformation_links(event)

        # --- Stage graph sync for POST-COMMIT publish (fix #1276) ---
        # Previously we called migration.publish_graph_sync(event) here
        # synchronously, which meant Redis received the 'canonical.created'
        # message BEFORE the outer DB transaction committed. If the caller
        # later rolled back (schema violation, chain-hash conflict, any
        # downstream error) the canonical row disappeared but the Neo4j
        # worker had already applied the message, producing a ghost graph
        # node with no authoritative DB backing. stage_graph_sync installs
        # SQLAlchemy after_commit / after_rollback hooks on the session:
        # a commit triggers the publish, a rollback discards it silently.
        migration.stage_graph_sync(self.session, event)

        logger.info(
            "canonical_event_persisted",
            extra={
                "event_id": str(event.event_id),
                "event_type": event.event_type.value,
                "tlc": event.traceability_lot_code,
                "tenant_id": tenant_id,
                "chain_seq": next_sequence,
                "source_system": event.source_system.value,
            },
        )

        return CanonicalStoreResult(
            success=True, event_id=str(event.event_id),
            sha256_hash=event.sha256_hash, chain_hash=chain_hash,
            idempotent=False, errors=[], legacy_event_id=legacy_id,
        )

    # ------------------------------------------------------------------
    # Batch Persistence
    # ------------------------------------------------------------------

    def persist_events_batch(self, events: List[TraceabilityEvent]) -> List[CanonicalStoreResult]:
        """Persist multiple canonical events in optimized batches."""
        if not events:
            return []

        tenant_id = str(events[0].tenant_id)

        # --- Enforce single-tenant batch invariant (fix #1265) ---
        # A batch that mixes tenants would set the GUC for one tenant
        # and then write rows for another — with RLS forced, writes for
        # the "wrong" tenant are silently rejected; without FORCE the
        # owner connection would succeed and cross-tenant leak. Fail
        # loud instead.
        for evt in events[1:]:
            if str(evt.tenant_id) != tenant_id:
                raise ValueError(
                    "persist_events_batch requires a single-tenant batch; "
                    f"got tenant_id={tenant_id!r} and {evt.tenant_id!r}"
                )

        # --- Set RLS tenant context (fix #1265) ---
        self.set_tenant_context(tenant_id)

        # --- Serialize chain growth per-tenant (fix #1251) ---
        self._acquire_chain_lock(tenant_id)

        for evt in events:
            if not evt.sha256_hash:
                evt.prepare_for_persistence()

        # --- Batch idempotency check (fix #1254) ---
        # Previous implementation built placeholder names via f-string
        # (``:k0, :k1, ...``). The names themselves were not user input,
        # but the pattern normalizes dynamic SQL assembly in this module.
        # We replace it with SQLAlchemy's expanding bind parameter which
        # generates the IN (...) list safely at prepare time.
        idemp_keys = [e.idempotency_key for e in events if e.idempotency_key]
        existing_map: Dict[str, Tuple[str, str, str]] = {}
        _idemp_select = text(
            """
            SELECT idempotency_key, event_id, sha256_hash, chain_hash
            FROM fsma.traceability_events
            WHERE tenant_id = :tid AND idempotency_key IN :keys
            """
        ).bindparams(bindparam("keys", expanding=True))
        for chunk_start in range(0, len(idemp_keys), 100):
            chunk = idemp_keys[chunk_start:chunk_start + 100]
            if not chunk:
                continue
            rows = self.session.execute(
                _idemp_select,
                {"tid": tenant_id, "keys": chunk},
            ).fetchall()
            for row in rows:
                existing_map[row[0]] = (str(row[1]), row[2], row[3])

        # --- Get chain head ---
        chain_head = self.session.execute(
            text("""
                SELECT chain_hash, sequence_num
                FROM fsma.hash_chain
                WHERE tenant_id = :tid
                ORDER BY sequence_num DESC
                LIMIT 1
                FOR UPDATE
            """),
            {"tid": tenant_id},
        ).fetchone()

        previous_chain_hash = chain_head[0] if chain_head else None
        next_sequence = (chain_head[1] + 1) if chain_head else 1

        # --- Process events ---
        results: List[CanonicalStoreResult] = []
        new_events: List[TraceabilityEvent] = []
        chain_entries: List[Dict[str, Any]] = []

        for evt in events:
            if evt.idempotency_key and evt.idempotency_key in existing_map:
                eid, sha, ch = existing_map[evt.idempotency_key]
                results.append(CanonicalStoreResult(
                    success=True, event_id=eid, sha256_hash=sha,
                    chain_hash=ch, idempotent=True, errors=[],
                ))
                continue

            chain_hash = compute_chain_hash(evt.sha256_hash, previous_chain_hash)
            evt.chain_hash = chain_hash

            chain_entries.append({
                "tenant_id": tenant_id,
                "cte_event_id": str(evt.event_id),
                "sequence_num": next_sequence,
                "event_hash": evt.sha256_hash,
                "previous_chain_hash": previous_chain_hash,
                "chain_hash": chain_hash,
            })

            new_events.append(evt)
            results.append(CanonicalStoreResult(
                success=True, event_id=str(evt.event_id),
                sha256_hash=evt.sha256_hash, chain_hash=chain_hash,
                idempotent=False, errors=[],
            ))

            previous_chain_hash = chain_hash
            next_sequence += 1

        # --- Batch INSERT with ON CONFLICT tolerance (#1266) ---
        # _batch_insert_canonical_events returns the set of event_ids
        # that actually landed; anything missing from that set is a row
        # that lost the idempotency race to a concurrent writer between
        # our pre-flight check at line ~310 and this INSERT. Those rows
        # must be reconciled: re-select the existing row and mark our
        # per-event result as idempotent so the caller sees accurate
        # sha256_hash / chain_hash values for them (#1266).
        inserted_event_ids: set[str] = set()
        for chunk_start in range(0, len(new_events), 50):
            chunk = new_events[chunk_start:chunk_start + 50]
            inserted_event_ids |= self._batch_insert_canonical_events(chunk)

        lost_race_events = [
            evt for evt in new_events
            if str(evt.event_id) not in inserted_event_ids
        ]

        if lost_race_events:
            # Re-select the winning rows (by idempotency_key) and patch
            # the per-event result from the matching entry in ``results``.
            # Build a lookup from idempotency_key -> result index so we
            # can update in place.
            idemp_to_result_idx: Dict[str, int] = {}
            for idx, evt in enumerate(events):
                if evt.idempotency_key:
                    idemp_to_result_idx[evt.idempotency_key] = idx
            idemp_keys = [
                evt.idempotency_key for evt in lost_race_events
                if evt.idempotency_key
            ]
            if idemp_keys:
                _winner_select = text(
                    """
                    SELECT idempotency_key, event_id, sha256_hash, chain_hash
                    FROM fsma.traceability_events
                    WHERE tenant_id = :tid AND idempotency_key IN :keys
                    """
                ).bindparams(bindparam("keys", expanding=True))
                for chunk_start in range(0, len(idemp_keys), 100):
                    chunk_keys = idemp_keys[chunk_start:chunk_start + 100]
                    rows = self.session.execute(
                        _winner_select,
                        {"tid": tenant_id, "keys": chunk_keys},
                    ).fetchall()
                    for idemp_key, winner_event_id, sha256, chain_h in rows:
                        result_idx = idemp_to_result_idx.get(idemp_key)
                        if result_idx is None:
                            continue
                        results[result_idx] = CanonicalStoreResult(
                            success=True,
                            event_id=str(winner_event_id),
                            sha256_hash=sha256,
                            chain_hash=chain_h,
                            idempotent=True,
                            errors=[],
                        )
            logger.info(
                "canonical_batch_reconciled_lost_race",
                extra={"tenant_id": tenant_id, "lost_race": len(lost_race_events)},
            )

        # Only write chain entries for events we actually inserted. A
        # row we lost to a concurrent writer already has its chain entry
        # written by the winner, so emitting another would double-grow
        # the chain.
        chain_entries_to_write = [
            ce for ce in chain_entries
            if str(ce["cte_event_id"]) in inserted_event_ids
        ]
        for chunk_start in range(0, len(chain_entries_to_write), 100):
            chunk = chain_entries_to_write[chunk_start:chunk_start + 100]
            self._batch_insert_chain_entries(chunk)

        inserted_events = [
            evt for evt in new_events if str(evt.event_id) in inserted_event_ids
        ]
        for evt in inserted_events:
            self._create_transformation_links(evt)

        # --- Dual-write legacy (TEMPORARY — see migration.py) ---
        # Only dual-write events that actually inserted here; an event
        # we lost to a concurrent writer was (presumably) dual-written
        # by that winner and re-writing would just duplicate in legacy.
        #
        # #1277: previously this loop wrapped dual_write_legacy in a
        # try/except and logged-and-continued on failure. That swallowed
        # the invariant "canonical row landed → legacy row landed",
        # which in turn meant the FDA-export path (still reading from
        # the legacy table during migration) silently diverged from the
        # canonical source of truth. The fix is to let the exception
        # propagate — the surrounding transaction rolls back, the
        # canonical INSERTs are reverted, and the caller gets a loud
        # failure instead of a silent data-integrity violation.
        if self.dual_write and inserted_events:
            for evt in inserted_events:
                migration.dual_write_legacy(self.session, evt)

        logger.info(
            "canonical_batch_persisted",
            extra={
                "tenant_id": tenant_id,
                "total": len(events),
                "new_inserted": len(inserted_events),
                "lost_race": len(new_events) - len(inserted_events),
                "idempotent_preflight": len(events) - len(new_events),
            },
        )

        return results

    # ------------------------------------------------------------------
    # Transformation Links
    # ------------------------------------------------------------------

    def _create_transformation_links(self, event: TraceabilityEvent) -> None:
        """Create adjacency rows in fsma.transformation_links for transformation events."""
        if event.event_type.value != "transformation":
            return

        input_lot_codes = event.kdes.get("input_lot_codes", [])
        if not input_lot_codes or not isinstance(input_lot_codes, list):
            return

        tenant_id = str(event.tenant_id)
        output_tlc = event.traceability_lot_code
        event_id = str(event.event_id)
        process_type = event.kdes.get("process_type")

        for input_tlc in input_lot_codes:
            if not input_tlc or not isinstance(input_tlc, str):
                continue
            try:
                input_event_row = self.session.execute(
                    text("""
                        SELECT event_id FROM fsma.traceability_events
                        WHERE tenant_id = :tid AND traceability_lot_code = :tlc
                        ORDER BY event_timestamp DESC LIMIT 1
                    """),
                    {"tid": tenant_id, "tlc": input_tlc.strip()},
                ).fetchone()

                input_event_id = str(input_event_row[0]) if input_event_row else None

                self.session.execute(
                    text("""
                        INSERT INTO fsma.transformation_links (
                            tenant_id, transformation_event_id,
                            input_tlc, input_event_id,
                            output_tlc, output_event_id,
                            output_quantity, output_unit,
                            process_type, confidence_score, link_source
                        ) VALUES (
                            :tenant_id, :transformation_event_id,
                            :input_tlc, :input_event_id,
                            :output_tlc, :output_event_id,
                            :output_quantity, :output_unit,
                            :process_type, :confidence, :link_source
                        )
                        ON CONFLICT (tenant_id, transformation_event_id, input_tlc, output_tlc)
                        DO NOTHING
                    """),
                    {
                        "tenant_id": tenant_id,
                        "transformation_event_id": event_id,
                        "input_tlc": input_tlc.strip(),
                        "input_event_id": input_event_id,
                        "output_tlc": output_tlc,
                        "output_event_id": event_id,
                        "output_quantity": event.quantity,
                        "output_unit": event.unit_of_measure,
                        "process_type": process_type,
                        "confidence": 1.0,
                        "link_source": "explicit",
                    },
                )
            except Exception as exc:
                logger.warning(
                    "transformation_link_create_failed",
                    extra={
                        "event_id": event_id, "input_tlc": input_tlc,
                        "output_tlc": output_tlc, "error": str(exc),
                    },
                )

        if input_lot_codes:
            logger.info(
                "transformation_links_created",
                extra={
                    "event_id": event_id, "output_tlc": output_tlc,
                    "input_count": len(input_lot_codes), "tenant_id": tenant_id,
                },
            )

    # ------------------------------------------------------------------
    # Trace Queries
    # ------------------------------------------------------------------

    # ``max_results`` default: caps BFS result accumulation at 10_000
    # links per traversal. A legitimate enterprise transformation graph
    # rarely exceeds ~1k at depth 5; 10_000 gives 10× headroom. The cap
    # exists to prevent OOM under adversarial inputs — see #1282.
    _TRACE_DEFAULT_MAX_RESULTS = 10_000

    def trace_forward(
        self,
        tenant_id: str,
        tlc: str,
        max_depth: int = 5,
        max_results: int = _TRACE_DEFAULT_MAX_RESULTS,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """Forward trace: find all output TLCs an input TLC contributed to.

        Returns ``(links, truncated)``. ``truncated=True`` means the BFS
        stopped at ``max_results`` — the link list is still valid data,
        just incomplete. Callers MUST check the flag and either surface
        truncation to the end user or fail-closed if completeness is
        required (e.g. regulator traceback export).

        #1282: without a cap, ``results`` could grow to O(depth × fan-out)
        with no ceiling, letting a malicious or misconfigured tenant OOM
        the worker with a wide transformation tree. ``visited`` prevents
        cycles but does not bound result size, so we add an explicit
        ``max_results`` gate distinct from ``max_depth``.
        """
        results: List[Dict[str, Any]] = []
        visited: set[str] = set()
        queue: List[Tuple[str, int]] = [(tlc, 0)]
        truncated = False

        while queue:
            current_tlc, depth = queue.pop(0)
            if depth >= max_depth or current_tlc in visited:
                continue
            visited.add(current_tlc)

            rows = self.session.execute(
                text("""
                    SELECT output_tlc, transformation_event_id, process_type,
                           output_quantity, output_unit, confidence_score
                    FROM fsma.transformation_links
                    WHERE tenant_id = :tid AND input_tlc = :tlc
                """),
                {"tid": tenant_id, "tlc": current_tlc},
            ).fetchall()

            for row in rows:
                if len(results) >= max_results:
                    truncated = True
                    break
                output_tlc = row[0]
                results.append({
                    "input_tlc": current_tlc, "output_tlc": output_tlc,
                    "transformation_event_id": str(row[1]), "process_type": row[2],
                    "output_quantity": float(row[3]) if row[3] else None,
                    "output_unit": row[4],
                    "confidence_score": float(row[5]) if row[5] else 1.0,
                    "depth": depth + 1,
                })
                if output_tlc not in visited:
                    queue.append((output_tlc, depth + 1))

            if truncated:
                # Drop remaining BFS frontier — we've already accepted we
                # can't complete this trace, so further DB round-trips
                # just burn budget without adding surfaced rows.
                break

        if truncated:
            logger.warning(
                "trace_forward_truncated",
                extra={
                    "tenant_id": tenant_id,
                    "tlc": tlc,
                    "max_results": max_results,
                    "max_depth": max_depth,
                    "returned": len(results),
                },
            )

        return results, truncated

    def trace_backward(
        self,
        tenant_id: str,
        tlc: str,
        max_depth: int = 5,
        max_results: int = _TRACE_DEFAULT_MAX_RESULTS,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """Backward trace: find all input TLCs that contributed to an output TLC.

        Returns ``(links, truncated)``. See ``trace_forward`` for the
        cap rationale (#1282).
        """
        results: List[Dict[str, Any]] = []
        visited: set[str] = set()
        queue: List[Tuple[str, int]] = [(tlc, 0)]
        truncated = False

        while queue:
            current_tlc, depth = queue.pop(0)
            if depth >= max_depth or current_tlc in visited:
                continue
            visited.add(current_tlc)

            rows = self.session.execute(
                text("""
                    SELECT input_tlc, transformation_event_id, process_type,
                           input_quantity, input_unit, confidence_score
                    FROM fsma.transformation_links
                    WHERE tenant_id = :tid AND output_tlc = :tlc
                """),
                {"tid": tenant_id, "tlc": current_tlc},
            ).fetchall()

            for row in rows:
                if len(results) >= max_results:
                    truncated = True
                    break
                input_tlc = row[0]
                results.append({
                    "input_tlc": input_tlc, "output_tlc": current_tlc,
                    "transformation_event_id": str(row[1]), "process_type": row[2],
                    "input_quantity": float(row[3]) if row[3] else None,
                    "input_unit": row[4],
                    "confidence_score": float(row[5]) if row[5] else 1.0,
                    "depth": depth + 1,
                })
                if input_tlc not in visited:
                    queue.append((input_tlc, depth + 1))

            if truncated:
                break

        if truncated:
            logger.warning(
                "trace_backward_truncated",
                extra={
                    "tenant_id": tenant_id,
                    "tlc": tlc,
                    "max_results": max_results,
                    "max_depth": max_depth,
                    "returned": len(results),
                },
            )

        return results, truncated

    # ------------------------------------------------------------------
    # Read Path
    # ------------------------------------------------------------------

    def get_event(
        self,
        tenant_id: str,
        event_id: str,
        *,
        include_raw_payload: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Get a single canonical event with full provenance.

        #1297: ``raw_payload`` is the original supplier record and can
        contain PII (grower names, addresses, phone numbers). Default
        to OMIT it so any new consumer that forgets to scope tenant
        doesn't accidentally leak upstream payloads. Callers that
        legitimately need the raw payload (audit endpoints,
        chain-of-custody views) must opt in with
        ``include_raw_payload=True``.

        The SQL still SELECTs the column — filtering on the Python
        side keeps the SQL text constant for prepared-statement
        caching and keeps the returned dict shape predictable across
        callers.
        """
        row = self.session.execute(
            text("""
                SELECT event_id, tenant_id, source_system, source_record_id,
                       event_type, event_timestamp, event_timezone,
                       product_reference, lot_reference, traceability_lot_code,
                       quantity, unit_of_measure,
                       from_entity_reference, to_entity_reference,
                       from_facility_reference, to_facility_reference,
                       transport_reference, kdes, raw_payload, normalized_payload,
                       provenance_metadata, confidence_score, status,
                       supersedes_event_id, schema_version,
                       sha256_hash, chain_hash, created_at, amended_at
                FROM fsma.traceability_events
                WHERE tenant_id = :tid AND event_id = :eid
            """),
            {"tid": tenant_id, "eid": event_id},
        ).fetchone()

        if not row:
            return None

        result: Dict[str, Any] = {
            "event_id": str(row[0]), "tenant_id": str(row[1]),
            "source_system": row[2], "source_record_id": row[3],
            "event_type": row[4],
            "event_timestamp": row[5].isoformat() if row[5] else None,
            "event_timezone": row[6],
            "product_reference": row[7], "lot_reference": row[8],
            "traceability_lot_code": row[9],
            "quantity": float(row[10]) if row[10] else 0,
            "unit_of_measure": row[11],
            "from_entity_reference": row[12], "to_entity_reference": row[13],
            "from_facility_reference": row[14], "to_facility_reference": row[15],
            "transport_reference": row[16],
            "kdes": row[17] if isinstance(row[17], dict) else json.loads(row[17] or "{}"),
            "normalized_payload": row[19] if isinstance(row[19], dict) else json.loads(row[19] or "{}"),
            "provenance_metadata": row[20] if isinstance(row[20], dict) else json.loads(row[20] or "{}"),
            "confidence_score": float(row[21]) if row[21] else 1.0,
            "status": row[22],
            "supersedes_event_id": str(row[23]) if row[23] else None,
            "schema_version": row[24], "sha256_hash": row[25], "chain_hash": row[26],
            "created_at": row[27].isoformat() if row[27] else None,
            "amended_at": row[28].isoformat() if row[28] else None,
        }

        # #1297: opt-in raw_payload. Safer default prevents accidental
        # PII leaks when a new consumer is added without thinking about
        # tenant scope / auth posture.
        if include_raw_payload:
            result["raw_payload"] = (
                row[18] if isinstance(row[18], dict)
                else json.loads(row[18] or "{}")
            )

        return result

    def query_events_by_tlc(
        self, tenant_id: str, tlc: str,
        start_date: Optional[str] = None, end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query canonical events for a TLC within a date range.

        Fix #1254: no f-string interpolation of predicate text.  Date
        filters are toggled via nullable bind parameters in the WHERE
        clause (``:start_date IS NULL OR event_timestamp >= :start_date``).
        This shape is constant SQL text regardless of inputs, so there
        is no dynamic predicate assembly and no injection vector.
        """
        params: Dict[str, Any] = {
            "tid": tenant_id,
            "tlc": tlc,
            "start_date": start_date,
            "end_date": end_date,
        }

        rows = self.session.execute(
            text("""
                SELECT event_id, event_type, traceability_lot_code,
                       product_reference, quantity, unit_of_measure,
                       from_facility_reference, to_facility_reference,
                       event_timestamp, sha256_hash, chain_hash,
                       source_system, status, kdes, provenance_metadata,
                       confidence_score, created_at
                FROM fsma.traceability_events
                WHERE tenant_id = :tid
                  AND traceability_lot_code = :tlc
                  AND status = 'active'
                  AND (CAST(:start_date AS timestamptz) IS NULL
                       OR event_timestamp >= CAST(:start_date AS timestamptz))
                  AND (CAST(:end_date AS timestamptz) IS NULL
                       OR event_timestamp <= CAST(:end_date AS timestamptz))
                ORDER BY event_timestamp ASC
            """),
            params,
        ).fetchall()

        return [
            {
                "event_id": str(r[0]), "event_type": r[1],
                "traceability_lot_code": r[2], "product_reference": r[3],
                "quantity": float(r[4]) if r[4] else 0, "unit_of_measure": r[5],
                "from_facility_reference": r[6], "to_facility_reference": r[7],
                "event_timestamp": r[8].isoformat() if r[8] else None,
                "sha256_hash": r[9], "chain_hash": r[10],
                "source_system": r[11], "status": r[12],
                "kdes": r[13] if isinstance(r[13], dict) else json.loads(r[13] or "{}"),
                "provenance_metadata": r[14] if isinstance(r[14], dict) else json.loads(r[14] or "{}"),
                "confidence_score": float(r[15]) if r[15] else 1.0,
                "created_at": r[16].isoformat() if r[16] else None,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Internal Write Helpers
    # ------------------------------------------------------------------

    def _insert_canonical_event(self, event: TraceabilityEvent) -> Optional[Tuple[str, str, str]]:
        """Insert a single canonical event.

        Uses ``ON CONFLICT (tenant_id, idempotency_key) DO NOTHING RETURNING``
        so a concurrent writer winning the idempotency race does not abort
        the surrounding transaction with a UNIQUE violation (fix #1252).

        Returns the inserted (event_id, sha256_hash, chain_hash) tuple on
        success, or None when the row already existed.
        """
        row = self.session.execute(
            text("""
                INSERT INTO fsma.traceability_events (
                    event_id, tenant_id, source_system, source_record_id,
                    source_file_id, ingestion_run_id,
                    event_type, event_timestamp, event_timezone,
                    product_reference, lot_reference, traceability_lot_code,
                    quantity, unit_of_measure,
                    from_entity_reference, to_entity_reference,
                    from_facility_reference, to_facility_reference,
                    transport_reference, kdes, raw_payload, normalized_payload,
                    provenance_metadata, confidence_score, status,
                    supersedes_event_id, schema_version,
                    sha256_hash, chain_hash, idempotency_key,
                    epcis_event_type, epcis_action, epcis_biz_step
                ) VALUES (
                    :event_id, :tenant_id, :source_system, :source_record_id,
                    :source_file_id, :ingestion_run_id,
                    :event_type, :event_timestamp, :event_timezone,
                    :product_reference, :lot_reference, :traceability_lot_code,
                    :quantity, :unit_of_measure,
                    :from_entity_reference, :to_entity_reference,
                    :from_facility_reference, :to_facility_reference,
                    :transport_reference, :kdes, :raw_payload, :normalized_payload,
                    :provenance_metadata, :confidence_score, :status,
                    :supersedes_event_id, :schema_version,
                    :sha256_hash, :chain_hash, :idempotency_key,
                    :epcis_event_type, :epcis_action, :epcis_biz_step
                )
                ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                RETURNING event_id, sha256_hash, chain_hash
            """),
            self._event_to_params(event),
        ).fetchone()
        if row is None:
            return None
        return (str(row[0]), row[1], row[2])

    def _event_to_params(self, event: TraceabilityEvent) -> Dict[str, Any]:
        """Convert a TraceabilityEvent to SQL parameter dict.

        #1290: enforce the raw_payload size cap HERE as defense-in-depth.
        ``prepare_for_persistence`` already checks the size, but that
        only runs when ``sha256_hash`` is unset — a developer who
        mutates ``raw_payload`` after prepping (e.g. in tests or a
        custom ingestion pipeline) would otherwise slip past the check.
        Serializing once and measuring the bytes we're about to write
        makes the check authoritative.
        """
        raw_payload_serialized = json.dumps(event.raw_payload, default=str)
        max_bytes = _raw_payload_max_bytes()
        raw_size = len(raw_payload_serialized.encode("utf-8"))
        if raw_size > max_bytes:
            raise RawPayloadTooLargeError(raw_size, max_bytes)
        return {
            "event_id": str(event.event_id),
            "tenant_id": str(event.tenant_id),
            "source_system": event.source_system.value,
            "source_record_id": event.source_record_id,
            "source_file_id": str(event.source_file_id) if event.source_file_id else None,
            "ingestion_run_id": str(event.ingestion_run_id) if event.ingestion_run_id else None,
            "event_type": event.event_type.value,
            "event_timestamp": event.event_timestamp.isoformat(),
            "event_timezone": event.event_timezone,
            "product_reference": event.product_reference,
            "lot_reference": event.lot_reference,
            "traceability_lot_code": event.traceability_lot_code,
            "quantity": event.quantity,
            "unit_of_measure": event.unit_of_measure,
            "from_entity_reference": event.from_entity_reference,
            "to_entity_reference": event.to_entity_reference,
            "from_facility_reference": event.from_facility_reference,
            "to_facility_reference": event.to_facility_reference,
            "transport_reference": event.transport_reference,
            "kdes": json.dumps(event.kdes, default=str),
            "raw_payload": raw_payload_serialized,
            "normalized_payload": json.dumps(event.normalized_payload, default=str),
            "provenance_metadata": json.dumps(event.provenance_metadata.to_dict(), default=str),
            "confidence_score": event.confidence_score,
            "status": event.status.value,
            "supersedes_event_id": str(event.supersedes_event_id) if event.supersedes_event_id else None,
            # #1197: ``schema_version`` is now an ``int`` on the Pydantic
            # model (envelope-version dispatch). The DB column is still
            # TEXT for backward-compat with pre-#1197 rows; cast here at
            # the boundary. A column type-migration to INT can follow on
            # its own schedule.
            "schema_version": str(event.schema_version),
            "sha256_hash": event.sha256_hash,
            "chain_hash": event.chain_hash,
            "idempotency_key": event.idempotency_key,
            "epcis_event_type": event.epcis_event_type,
            "epcis_action": event.epcis_action,
            "epcis_biz_step": event.epcis_biz_step,
        }

    def _batch_insert_canonical_events(
        self, events: List[TraceabilityEvent]
    ) -> set[str]:
        """Batch insert canonical events, tolerant of idempotency races.

        Appends ``ON CONFLICT (tenant_id, idempotency_key) DO NOTHING`` so
        that if a concurrent writer won the idempotency race for any
        event in this chunk, the whole chunk does not abort with a
        UNIQUE violation — the other 49 rows still land (#1266).

        Returns the set of ``event_id`` strings that were actually
        inserted (the complement of that set are the duplicates, which
        the caller may re-select to obtain the existing row's
        ``sha256_hash`` / ``chain_hash`` for the per-event result).
        """
        values_clauses = []
        params: Dict[str, Any] = {}
        for i, evt in enumerate(events):
            p = self._event_to_params(evt)
            suffixed = {f"{k}_{i}": v for k, v in p.items()}
            params.update(suffixed)
            cols = [f":{k}_{i}" for k in p.keys()]
            values_clauses.append(f"({', '.join(cols)})")

        col_names = list(self._event_to_params(events[0]).keys())
        sql = f"""
            INSERT INTO fsma.traceability_events ({', '.join(col_names)})
            VALUES {', '.join(values_clauses)}
            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            RETURNING event_id
        """
        rows = self.session.execute(text(sql), params).fetchall()
        return {str(r[0]) for r in rows}

    def _insert_chain_entry(
        self, tenant_id: str, event_id: str, sequence_num: int,
        event_hash: str, previous_chain_hash: Optional[str], chain_hash: str,
    ) -> None:
        """Insert a hash chain entry."""
        self.session.execute(
            text("""
                INSERT INTO fsma.hash_chain (
                    tenant_id, cte_event_id, sequence_num,
                    event_hash, previous_chain_hash, chain_hash
                ) VALUES (
                    :tenant_id, :cte_event_id, :sequence_num,
                    :event_hash, :previous_chain_hash, :chain_hash
                )
            """),
            {
                "tenant_id": tenant_id, "cte_event_id": event_id,
                "sequence_num": sequence_num, "event_hash": event_hash,
                "previous_chain_hash": previous_chain_hash, "chain_hash": chain_hash,
            },
        )

    def _batch_insert_chain_entries(self, entries: List[Dict[str, Any]]) -> None:
        """Batch insert hash chain entries."""
        values_clauses = []
        params: Dict[str, Any] = {}
        for i, entry in enumerate(entries):
            values_clauses.append(
                f"(:tid_{i}, :eid_{i}, :seq_{i}, :eh_{i}, :pch_{i}, :ch_{i})"
            )
            params.update({
                f"tid_{i}": entry["tenant_id"], f"eid_{i}": entry["cte_event_id"],
                f"seq_{i}": entry["sequence_num"], f"eh_{i}": entry["event_hash"],
                f"pch_{i}": entry["previous_chain_hash"], f"ch_{i}": entry["chain_hash"],
            })
        sql = f"""
            INSERT INTO fsma.hash_chain (
                tenant_id, cte_event_id, sequence_num,
                event_hash, previous_chain_hash, chain_hash
            ) VALUES {', '.join(values_clauses)}
        """
        self.session.execute(text(sql), params)
