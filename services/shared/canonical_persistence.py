"""
Canonical Event Persistence Layer.

Provides database-backed storage for TraceabilityEvents in the canonical
model (fsma.traceability_events). This replaces direct writes to
fsma.cte_events for new ingestion paths.

This module also writes to the legacy cte_events table during the migration
period (dual-write) to maintain backward compatibility with existing
export and graph sync code.

Usage:
    from shared.canonical_persistence import CanonicalEventStore

    store = CanonicalEventStore(db_session)
    result = store.persist_event(canonical_event)
    results = store.persist_events_batch(tenant_id, events)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.canonical_event import (
    TraceabilityEvent,
    IngestionRun,
    IngestionRunStatus,
)
from shared.cte_persistence import (
    compute_chain_hash,
    StoreResult,
    ChainVerification,
)

logger = logging.getLogger("canonical-persistence")


# ---------------------------------------------------------------------------
# Persistence Result
# ---------------------------------------------------------------------------

class CanonicalStoreResult:
    """Result of persisting a canonical event."""

    __slots__ = (
        "success", "event_id", "sha256_hash", "chain_hash",
        "idempotent", "errors", "legacy_event_id",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    def to_legacy_result(self) -> StoreResult:
        """Convert to legacy StoreResult for backward compatibility."""
        return StoreResult(
            success=self.success,
            event_id=self.event_id,
            sha256_hash=self.sha256_hash,
            chain_hash=self.chain_hash,
            idempotent=self.idempotent,
            errors=self.errors or [],
            kde_completeness=1.0,
            alerts=[],
        )


# ---------------------------------------------------------------------------
# Canonical Event Store
# ---------------------------------------------------------------------------

class CanonicalEventStore:
    """
    Database-backed persistence for canonical TraceabilityEvents.

    Writes to fsma.traceability_events (canonical) and optionally
    dual-writes to fsma.cte_events (legacy) during migration.
    """

    def __init__(self, session: Session, dual_write: bool = True, skip_chain_write: bool = False):
        """
        Args:
            session: SQLAlchemy session with tenant context.
            dual_write: If True, also writes to legacy cte_events table.
            skip_chain_write: If True, skips hash chain insertion. Use when
                the caller (e.g., EPCIS/webhook dual-write path) has already
                written the chain entry via the legacy CTEPersistence path.
        """
        self.session = session
        self.dual_write = dual_write
        self.skip_chain_write = skip_chain_write

    def set_tenant_context(self, tenant_id: str) -> None:
        """Set the RLS tenant context for this session."""
        self.session.execute(
            text("SET LOCAL app.tenant_id = :tid"),
            {"tid": tenant_id},
        )

    # ------------------------------------------------------------------
    # Ingestion Run Management
    # ------------------------------------------------------------------

    def create_ingestion_run(self, run: IngestionRun) -> str:
        """Create an ingestion run record. Returns the run ID."""
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
        self,
        run_id: str,
        accepted: int,
        rejected: int,
        errors: Optional[List[Dict]] = None,
    ) -> None:
        """Mark an ingestion run as completed."""
        status = "completed" if rejected == 0 else "partial"
        self.session.execute(
            text("""
                UPDATE fsma.ingestion_runs
                SET accepted_count = :accepted,
                    rejected_count = :rejected,
                    status = :status,
                    completed_at = NOW(),
                    errors = :errors
                WHERE id = :id
            """),
            {
                "id": run_id,
                "accepted": accepted,
                "rejected": rejected,
                "status": status,
                "errors": json.dumps(errors or []),
            },
        )

    # ------------------------------------------------------------------
    # Single Event Persistence
    # ------------------------------------------------------------------

    def persist_event(
        self,
        event: TraceabilityEvent,
    ) -> CanonicalStoreResult:
        """
        Persist a single canonical TraceabilityEvent.

        Handles:
        1. Idempotency check
        2. Hash chain computation
        3. Write to canonical table
        4. Dual-write to legacy table (if enabled)
        5. Hash chain entry

        Returns CanonicalStoreResult.
        """
        tenant_id = str(event.tenant_id)

        # Ensure hashes are computed
        if not event.sha256_hash:
            event.prepare_for_persistence()

        # --- Idempotency check ---
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
                    success=True,
                    event_id=str(existing[0]),
                    sha256_hash=existing[1],
                    chain_hash=existing[2],
                    idempotent=True,
                    errors=[],
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

        # --- Insert canonical event ---
        self._insert_canonical_event(event)

        # --- Mark superseded event ---
        if event.supersedes_event_id:
            # Guard: reject self-referencing amendments
            if event.supersedes_event_id == event.event_id:
                raise ValueError("Event cannot supersede itself")
            # Guard: reject superseding an already-superseded event
            target_status = self.session.execute(
                text("""
                    SELECT status FROM fsma.traceability_events
                    WHERE event_id = :superseded_id AND tenant_id = :tid
                """),
                {"superseded_id": str(event.supersedes_event_id), "tid": tenant_id},
            ).scalar()
            if target_status == "superseded":
                raise ValueError(
                    f"Cannot supersede event {event.supersedes_event_id}: already superseded"
                )
            self.session.execute(
                text("""
                    UPDATE fsma.traceability_events
                    SET status = 'superseded', amended_at = NOW()
                    WHERE event_id = :superseded_id
                      AND tenant_id = :tid
                      AND status = 'active'
                """),
                {
                    "superseded_id": str(event.supersedes_event_id),
                    "tid": tenant_id,
                },
            )

        # --- Insert hash chain entry ---
        # Skip if the caller already wrote the chain entry (e.g., EPCIS/webhook
        # dual-write paths that go through CTEPersistence.store_event() first).
        if not self.skip_chain_write:
            self._insert_chain_entry(
                tenant_id=tenant_id,
                event_id=str(event.event_id),
                sequence_num=next_sequence,
                event_hash=event.sha256_hash,
                previous_chain_hash=previous_chain_hash,
                chain_hash=chain_hash,
            )

        # --- Dual-write to legacy table ---
        legacy_id = None
        if self.dual_write:
            legacy_id = self._dual_write_legacy(event)

        # --- Create transformation links if this is a transformation event ---
        self._create_transformation_links(event)

        # --- Publish to graph sync queue ---
        self._publish_graph_sync(event)

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
            success=True,
            event_id=str(event.event_id),
            sha256_hash=event.sha256_hash,
            chain_hash=chain_hash,
            idempotent=False,
            errors=[],
            legacy_event_id=legacy_id,
        )

    # ------------------------------------------------------------------
    # Batch Persistence
    # ------------------------------------------------------------------

    def persist_events_batch(
        self,
        events: List[TraceabilityEvent],
    ) -> List[CanonicalStoreResult]:
        """
        Persist multiple canonical events in optimized batches.

        Follows the same pattern as CTEPersistence.store_events_batch:
        1. Batch idempotency check
        2. Sequential chain hash computation
        3. Batch INSERT
        """
        if not events:
            return []

        tenant_id = str(events[0].tenant_id)

        # Ensure all events have hashes
        for evt in events:
            if not evt.sha256_hash:
                evt.prepare_for_persistence()

        # --- Batch idempotency check ---
        idemp_keys = [e.idempotency_key for e in events if e.idempotency_key]
        existing_map: Dict[str, Tuple[str, str, str]] = {}
        for chunk_start in range(0, len(idemp_keys), 100):
            chunk = idemp_keys[chunk_start:chunk_start + 100]
            if not chunk:
                continue
            placeholders = ", ".join(f":k{i}" for i in range(len(chunk)))
            params = {f"k{i}": k for i, k in enumerate(chunk)}
            params["tid"] = tenant_id
            rows = self.session.execute(
                text(f"""
                    SELECT idempotency_key, event_id, sha256_hash, chain_hash
                    FROM fsma.traceability_events
                    WHERE tenant_id = :tid AND idempotency_key IN ({placeholders})
                """),
                params,
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

        # --- Batch INSERT canonical events ---
        for chunk_start in range(0, len(new_events), 50):
            chunk = new_events[chunk_start:chunk_start + 50]
            self._batch_insert_canonical_events(chunk)

        # --- Batch INSERT chain entries ---
        for chunk_start in range(0, len(chain_entries), 100):
            chunk = chain_entries[chunk_start:chunk_start + 100]
            self._batch_insert_chain_entries(chunk)

        # --- Create transformation links ---
        for evt in new_events:
            self._create_transformation_links(evt)

        # --- Dual-write legacy ---
        if self.dual_write and new_events:
            for evt in new_events:
                try:
                    self._dual_write_legacy(evt)
                except Exception as e:
                    logger.warning(
                        "legacy_dual_write_failed",
                        extra={"event_id": str(evt.event_id), "error": str(e)},
                    )

        logger.info(
            "canonical_batch_persisted",
            extra={
                "tenant_id": tenant_id,
                "total": len(events),
                "new": len(new_events),
                "idempotent": len(events) - len(new_events),
            },
        )

        return results

    # ------------------------------------------------------------------
    # Graph Sync
    # ------------------------------------------------------------------

    def _publish_graph_sync(self, event: TraceabilityEvent) -> None:
        """Publish canonical event to Redis for Neo4j graph sync."""
        import os
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
            import json as _json
            client.rpush("neo4j-sync", _json.dumps(message, default=str))
        except Exception as exc:
            logger.warning("canonical_graph_sync_failed", extra={
                "event_id": str(event.event_id), "error": str(exc),
            })

    # ------------------------------------------------------------------
    # Transformation Links
    # ------------------------------------------------------------------

    def _create_transformation_links(self, event: TraceabilityEvent) -> None:
        """
        If this is a transformation event with input_lot_codes in KDEs,
        create adjacency rows in fsma.transformation_links.

        Each input TLC gets one row linking it to the output TLC
        (the event's own traceability_lot_code).
        """
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
                # Resolve input_event_id if the input TLC exists in our DB
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
                        "event_id": event_id,
                        "input_tlc": input_tlc,
                        "output_tlc": output_tlc,
                        "error": str(exc),
                    },
                )

        if input_lot_codes:
            logger.info(
                "transformation_links_created",
                extra={
                    "event_id": event_id,
                    "output_tlc": output_tlc,
                    "input_count": len(input_lot_codes),
                    "tenant_id": tenant_id,
                },
            )

    # ------------------------------------------------------------------
    # Trace Queries
    # ------------------------------------------------------------------

    def trace_forward(self, tenant_id: str, tlc: str, max_depth: int = 5) -> List[Dict[str, Any]]:
        """
        Forward trace: Given an input TLC, find all output TLCs it contributed to.
        Recursively follows the adjacency graph up to max_depth hops.
        Returns list of {output_tlc, transformation_event_id, depth, process_type}.
        """
        results = []
        visited = set()
        queue = [(tlc, 0)]

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
                output_tlc = row[0]
                results.append({
                    "input_tlc": current_tlc,
                    "output_tlc": output_tlc,
                    "transformation_event_id": str(row[1]),
                    "process_type": row[2],
                    "output_quantity": float(row[3]) if row[3] else None,
                    "output_unit": row[4],
                    "confidence_score": float(row[5]) if row[5] else 1.0,
                    "depth": depth + 1,
                })
                if output_tlc not in visited:
                    queue.append((output_tlc, depth + 1))

        return results

    def trace_backward(self, tenant_id: str, tlc: str, max_depth: int = 5) -> List[Dict[str, Any]]:
        """
        Backward trace: Given an output TLC, find all input TLCs that contributed to it.
        Recursively follows the adjacency graph up to max_depth hops.
        """
        results = []
        visited = set()
        queue = [(tlc, 0)]

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
                input_tlc = row[0]
                results.append({
                    "input_tlc": input_tlc,
                    "output_tlc": current_tlc,
                    "transformation_event_id": str(row[1]),
                    "process_type": row[2],
                    "input_quantity": float(row[3]) if row[3] else None,
                    "input_unit": row[4],
                    "confidence_score": float(row[5]) if row[5] else 1.0,
                    "depth": depth + 1,
                })
                if input_tlc not in visited:
                    queue.append((input_tlc, depth + 1))

        return results

    # ------------------------------------------------------------------
    # Read Path
    # ------------------------------------------------------------------

    def get_event(self, tenant_id: str, event_id: str) -> Optional[Dict[str, Any]]:
        """Get a single canonical event with full provenance."""
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

        return {
            "event_id": str(row[0]),
            "tenant_id": str(row[1]),
            "source_system": row[2],
            "source_record_id": row[3],
            "event_type": row[4],
            "event_timestamp": row[5].isoformat() if row[5] else None,
            "event_timezone": row[6],
            "product_reference": row[7],
            "lot_reference": row[8],
            "traceability_lot_code": row[9],
            "quantity": float(row[10]) if row[10] else 0,
            "unit_of_measure": row[11],
            "from_entity_reference": row[12],
            "to_entity_reference": row[13],
            "from_facility_reference": row[14],
            "to_facility_reference": row[15],
            "transport_reference": row[16],
            "kdes": row[17] if isinstance(row[17], dict) else json.loads(row[17] or "{}"),
            "raw_payload": row[18] if isinstance(row[18], dict) else json.loads(row[18] or "{}"),
            "normalized_payload": row[19] if isinstance(row[19], dict) else json.loads(row[19] or "{}"),
            "provenance_metadata": row[20] if isinstance(row[20], dict) else json.loads(row[20] or "{}"),
            "confidence_score": float(row[21]) if row[21] else 1.0,
            "status": row[22],
            "supersedes_event_id": str(row[23]) if row[23] else None,
            "schema_version": row[24],
            "sha256_hash": row[25],
            "chain_hash": row[26],
            "created_at": row[27].isoformat() if row[27] else None,
            "amended_at": row[28].isoformat() if row[28] else None,
        }

    def query_events_by_tlc(
        self,
        tenant_id: str,
        tlc: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query canonical events for a TLC within a date range."""
        params: Dict[str, Any] = {"tid": tenant_id, "tlc": tlc}
        where_clauses = [
            "tenant_id = :tid",
            "traceability_lot_code = :tlc",
            "status = 'active'",
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
                SELECT event_id, event_type, traceability_lot_code,
                       product_reference, quantity, unit_of_measure,
                       from_facility_reference, to_facility_reference,
                       event_timestamp, sha256_hash, chain_hash,
                       source_system, status, kdes, provenance_metadata,
                       confidence_score, created_at
                FROM fsma.traceability_events
                WHERE {where}
                ORDER BY event_timestamp ASC
            """),
            params,
        ).fetchall()

        return [
            {
                "event_id": str(r[0]),
                "event_type": r[1],
                "traceability_lot_code": r[2],
                "product_reference": r[3],
                "quantity": float(r[4]) if r[4] else 0,
                "unit_of_measure": r[5],
                "from_facility_reference": r[6],
                "to_facility_reference": r[7],
                "event_timestamp": r[8].isoformat() if r[8] else None,
                "sha256_hash": r[9],
                "chain_hash": r[10],
                "source_system": r[11],
                "status": r[12],
                "kdes": r[13] if isinstance(r[13], dict) else json.loads(r[13] or "{}"),
                "provenance_metadata": r[14] if isinstance(r[14], dict) else json.loads(r[14] or "{}"),
                "confidence_score": float(r[15]) if r[15] else 1.0,
                "created_at": r[16].isoformat() if r[16] else None,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _insert_canonical_event(self, event: TraceabilityEvent) -> None:
        """Insert a single canonical event."""
        self.session.execute(
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
            """),
            self._event_to_params(event),
        )

    def _event_to_params(self, event: TraceabilityEvent) -> Dict[str, Any]:
        """Convert a TraceabilityEvent to SQL parameter dict."""
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
            "raw_payload": json.dumps(event.raw_payload, default=str),
            "normalized_payload": json.dumps(event.normalized_payload, default=str),
            "provenance_metadata": json.dumps(event.provenance_metadata.to_dict(), default=str),
            "confidence_score": event.confidence_score,
            "status": event.status.value,
            "supersedes_event_id": str(event.supersedes_event_id) if event.supersedes_event_id else None,
            "schema_version": event.schema_version,
            "sha256_hash": event.sha256_hash,
            "chain_hash": event.chain_hash,
            "idempotency_key": event.idempotency_key,
            "epcis_event_type": event.epcis_event_type,
            "epcis_action": event.epcis_action,
            "epcis_biz_step": event.epcis_biz_step,
        }

    def _batch_insert_canonical_events(self, events: List[TraceabilityEvent]) -> None:
        """Batch insert canonical events."""
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
        """
        self.session.execute(text(sql), params)

    def _insert_chain_entry(
        self,
        tenant_id: str,
        event_id: str,
        sequence_num: int,
        event_hash: str,
        previous_chain_hash: Optional[str],
        chain_hash: str,
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
                "tenant_id": tenant_id,
                "cte_event_id": event_id,
                "sequence_num": sequence_num,
                "event_hash": event_hash,
                "previous_chain_hash": previous_chain_hash,
                "chain_hash": chain_hash,
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
                f"tid_{i}": entry["tenant_id"],
                f"eid_{i}": entry["cte_event_id"],
                f"seq_{i}": entry["sequence_num"],
                f"eh_{i}": entry["event_hash"],
                f"pch_{i}": entry["previous_chain_hash"],
                f"ch_{i}": entry["chain_hash"],
            })
        sql = f"""
            INSERT INTO fsma.hash_chain (
                tenant_id, cte_event_id, sequence_num,
                event_hash, previous_chain_hash, chain_hash
            ) VALUES {', '.join(values_clauses)}
        """
        self.session.execute(text(sql), params)

    def _dual_write_legacy(self, event: TraceabilityEvent) -> Optional[str]:
        """
        Write to legacy fsma.cte_events for backward compatibility.

        During the migration period, both tables receive writes so that
        existing export and graph sync code continues to work.
        """
        try:
            legacy_id = str(event.event_id)
            self.session.execute(
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
                nested = self.session.begin_nested()
                try:
                    self.session.execute(
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
