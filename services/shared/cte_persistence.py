"""
FSMA 204 CTE Persistence Layer.

Provides database-backed storage for Critical Tracking Events, replacing
the in-memory dicts that previously lost data on every restart.

This module is the single source of truth for CTE persistence. Both the
webhook router and EPCIS ingestion module write through this layer.

Usage:
    from services.shared.cte_persistence import CTEPersistence

    persistence = CTEPersistence(db_session)
    result = persistence.store_event(tenant_id, event, kdes, alerts)
    chain = persistence.verify_chain(tenant_id)
    events = persistence.query_for_export(tenant_id, tlc, start, end)
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger("cte-persistence")


# ---------------------------------------------------------------------------
# Data Transfer Objects
# ---------------------------------------------------------------------------

class CTERecord:
    """A persisted CTE event with all associated data."""

    __slots__ = (
        "id", "tenant_id", "event_type", "traceability_lot_code",
        "product_description", "quantity", "unit_of_measure",
        "location_gln", "location_name", "event_timestamp",
        "source", "idempotency_key", "sha256_hash", "chain_hash",
        "validation_status", "ingested_at", "kdes", "alerts",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))


class ChainEntry:
    """A single entry in the hash chain ledger."""

    __slots__ = (
        "id", "tenant_id", "cte_event_id", "sequence_num",
        "event_hash", "previous_chain_hash", "chain_hash", "created_at",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))


class StoreResult:
    """Result of storing a CTE event."""

    __slots__ = (
        "success", "event_id", "sha256_hash", "chain_hash",
        "idempotent", "errors", "kde_completeness", "alerts",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))


class ChainVerification:
    """Result of verifying a tenant's hash chain."""

    __slots__ = (
        "valid", "chain_length", "errors", "checked_at",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))


# ---------------------------------------------------------------------------
# Hashing Utilities
# ---------------------------------------------------------------------------

def compute_event_hash(
    event_id: str,
    event_type: str,
    tlc: str,
    product_description: str,
    quantity: float,
    unit_of_measure: str,
    location_gln: Optional[str],
    location_name: Optional[str],
    timestamp: str,
    kdes: Dict[str, Any],
) -> str:
    """
    Compute SHA-256 hash of an event using pipe-delimited canonical form.

    This is the same algorithm as the original webhook_router, now centralized.
    """
    canonical = "|".join([
        event_id,
        event_type,
        tlc,
        product_description,
        str(quantity),
        unit_of_measure,
        location_gln or "",
        location_name or "",
        timestamp,
        json.dumps(kdes, sort_keys=True, default=str),
    ])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_chain_hash(event_hash: str, previous_chain_hash: Optional[str]) -> str:
    """
    Chain this event's hash to the previous chain hash.

    Chain root uses 'GENESIS' as the seed value.
    """
    chain_input = f"{previous_chain_hash or 'GENESIS'}|{event_hash}"
    return hashlib.sha256(chain_input.encode("utf-8")).hexdigest()


def compute_idempotency_key(
    event_type: str,
    tlc: str,
    timestamp: str,
    source: str,
    kdes: Dict[str, Any],
    location_gln: Optional[str] = None,
    location_name: Optional[str] = None,
) -> str:
    """
    Compute a deduplication key from event content.

    Two identical events from the same source AND location produce the same key,
    preventing double-ingestion. Location is included because FSMA 204 treats
    location as critical to event identity — the same product shipped from two
    different warehouses at the same time are distinct events.
    """
    canonical = json.dumps(
        {
            "event_type": event_type,
            "tlc": tlc,
            "timestamp": timestamp,
            "source": source,
            "location_gln": location_gln or "",
            "location_name": location_name or "",
            "kdes": kdes,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Persistence Layer
# ---------------------------------------------------------------------------

class CTEPersistence:
    """
    Database-backed persistence for FSMA 204 CTE events.

    All methods expect a SQLAlchemy session that has already set
    the tenant context via: SET LOCAL regengine.tenant_id = '<uuid>';

    The RLS policies on the fsma.* tables enforce tenant isolation
    automatically — this module never needs to filter by tenant_id
    in WHERE clauses for read queries.
    """

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Tenant Context
    # ------------------------------------------------------------------

    def set_tenant_context(self, tenant_id: str) -> None:
        """Set the RLS tenant context for this session."""
        self.session.execute(
            text("SET LOCAL regengine.tenant_id = :tid"),
            {"tid": tenant_id},
        )

    # ------------------------------------------------------------------
    # Write Path
    # ------------------------------------------------------------------

    def store_event(
        self,
        tenant_id: str,
        event_type: str,
        traceability_lot_code: str,
        product_description: str,
        quantity: float,
        unit_of_measure: str,
        event_timestamp: str,
        source: str = "api",
        location_gln: Optional[str] = None,
        location_name: Optional[str] = None,
        kdes: Optional[Dict[str, Any]] = None,
        alerts: Optional[List[Dict[str, Any]]] = None,
        epcis_event_type: Optional[str] = None,
        epcis_action: Optional[str] = None,
        epcis_biz_step: Optional[str] = None,
        source_event_id: Optional[str] = None,
    ) -> StoreResult:
        """
        Persist a CTE event with its KDEs, hash chain entry, and alerts.

        This is an atomic operation — either everything is committed or
        nothing is. The caller is responsible for committing the session.

        Returns:
            StoreResult with event_id, hashes, and any alerts.
        """
        kdes = kdes or {}
        alerts = alerts or []
        event_id = str(uuid4())

        # --- Idempotency check ---
        idempotency_key = compute_idempotency_key(
            event_type, traceability_lot_code, event_timestamp, source, kdes,
            location_gln=location_gln, location_name=location_name,
        )

        existing = self.session.execute(
            text("""
                SELECT id, sha256_hash, chain_hash
                FROM fsma.cte_events
                WHERE idempotency_key = :key AND tenant_id = :tid
            """),
            {"key": idempotency_key, "tid": tenant_id},
        ).fetchone()

        if existing:
            logger.info(
                "idempotent_event_skipped",
                extra={
                    "existing_id": str(existing[0]),
                    "tlc": traceability_lot_code,
                },
            )
            return StoreResult(
                success=True,
                event_id=str(existing[0]),
                sha256_hash=existing[1],
                chain_hash=existing[2],
                idempotent=True,
                errors=[],
                kde_completeness=1.0,
                alerts=[],
            )

        # --- Compute hashes ---
        sha256_hash = compute_event_hash(
            event_id, event_type, traceability_lot_code,
            product_description, quantity, unit_of_measure,
            location_gln, location_name, event_timestamp, kdes,
        )

        # Get the current chain head for this tenant
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

        chain_hash = compute_chain_hash(sha256_hash, previous_chain_hash)

        # --- Insert CTE event ---
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
            """),
            {
                "id": event_id,
                "tenant_id": tenant_id,
                "event_type": event_type,
                "tlc": traceability_lot_code,
                "product_description": product_description,
                "quantity": quantity,
                "unit_of_measure": unit_of_measure,
                "location_gln": location_gln,
                "location_name": location_name,
                "event_timestamp": event_timestamp,
                "source": source,
                "source_event_id": source_event_id,
                "idempotency_key": idempotency_key,
                "sha256_hash": sha256_hash,
                "chain_hash": chain_hash,
                "epcis_event_type": epcis_event_type,
                "epcis_action": epcis_action,
                "epcis_biz_step": epcis_biz_step,
                "validation_status": "warning" if alerts else "valid",
            },
        )

        # --- Insert KDEs ---
        for kde_key, kde_value in kdes.items():
            if kde_value is None:
                continue
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
                    "tenant_id": tenant_id,
                    "cte_event_id": event_id,
                    "kde_key": kde_key,
                    "kde_value": str(kde_value),
                    "is_required": False,  # caller can override
                },
            )

        # --- Insert hash chain entry ---
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
                "sequence_num": next_sequence,
                "event_hash": sha256_hash,
                "previous_chain_hash": previous_chain_hash,
                "chain_hash": chain_hash,
            },
        )

        # --- Insert alerts ---
        for alert in alerts:
            self.session.execute(
                text("""
                    INSERT INTO fsma.compliance_alerts (
                        tenant_id, cte_event_id, severity, alert_type, message
                    ) VALUES (
                        :tenant_id, :cte_event_id, :severity, :alert_type, :message
                    )
                """),
                {
                    "tenant_id": tenant_id,
                    "cte_event_id": event_id,
                    "severity": alert.get("severity", "warning"),
                    "alert_type": alert.get("alert_type", "unknown"),
                    "message": alert.get("message", ""),
                },
            )

        logger.info(
            "cte_event_persisted",
            extra={
                "event_id": event_id,
                "event_type": event_type,
                "tlc": traceability_lot_code,
                "tenant_id": tenant_id,
                "chain_seq": next_sequence,
                "sha256": sha256_hash[:16],
            },
        )

        return StoreResult(
            success=True,
            event_id=event_id,
            sha256_hash=sha256_hash,
            chain_hash=chain_hash,
            idempotent=False,
            errors=[],
            kde_completeness=1.0,
            alerts=alerts,
        )

    # ------------------------------------------------------------------
    # Read Path — FDA Export Queries
    # ------------------------------------------------------------------

    def query_events_by_tlc(
        self,
        tenant_id: str,
        tlc: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query CTE events for a specific TLC within a date range.

        This is the query that backs the FDA export: "Give me all
        traceability records for lot code X between dates Y and Z."
        """
        params: Dict[str, Any] = {"tid": tenant_id, "tlc": tlc}
        where_clauses = [
            "tenant_id = :tid",
            "traceability_lot_code = :tlc",
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
                    e.source, e.validation_status, e.ingested_at
                FROM fsma.cte_events e
                WHERE {where}
                ORDER BY e.event_timestamp ASC
            """),
            params,
        ).fetchall()

        events = []
        for row in rows:
            event = {
                "id": str(row[0]),
                "event_type": row[1],
                "traceability_lot_code": row[2],
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
            }

            # Fetch KDEs for this event
            kdes = self.session.execute(
                text("""
                    SELECT kde_key, kde_value, is_required
                    FROM fsma.cte_kdes
                    WHERE cte_event_id = :eid AND tenant_id = :tid
                """),
                {"eid": str(row[0]), "tid": tenant_id},
            ).fetchall()

            event["kdes"] = {k[0]: k[1] for k in kdes}
            events.append(event)

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
        """
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

        where = " AND ".join(where_clauses)

        # Get total count
        count_row = self.session.execute(
            text(f"SELECT COUNT(*) FROM fsma.cte_events WHERE {where}"),
            params,
        ).fetchone()
        total = count_row[0] if count_row else 0

        # Get page of results
        rows = self.session.execute(
            text(f"""
                SELECT id, event_type, traceability_lot_code,
                       product_description, quantity, unit_of_measure,
                       event_timestamp, validation_status, sha256_hash
                FROM fsma.cte_events
                WHERE {where}
                ORDER BY event_timestamp DESC
                LIMIT :lim OFFSET :off
            """),
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

        return events, total

    # ------------------------------------------------------------------
    # Chain Verification
    # ------------------------------------------------------------------

    def verify_chain(self, tenant_id: str) -> ChainVerification:
        """
        Verify the integrity of a tenant's entire hash chain.

        Walks the chain from genesis to head, recomputing each chain_hash
        and comparing to the stored value. Any mismatch = tamper detected.
        """
        rows = self.session.execute(
            text("""
                SELECT sequence_num, event_hash, previous_chain_hash, chain_hash
                FROM fsma.hash_chain
                WHERE tenant_id = :tid
                ORDER BY sequence_num ASC
            """),
            {"tid": tenant_id},
        ).fetchall()

        if not rows:
            return ChainVerification(
                valid=True,
                chain_length=0,
                errors=[],
                checked_at=datetime.now(timezone.utc).isoformat(),
            )

        errors = []
        for i, row in enumerate(rows):
            seq, event_hash, stored_prev, stored_chain = row

            # Check sequence continuity
            expected_seq = i + 1
            if seq != expected_seq:
                errors.append(
                    f"Sequence gap: expected {expected_seq}, got {seq}"
                )

            # Check previous_chain_hash linkage
            if i == 0:
                if stored_prev is not None:
                    errors.append(
                        f"Genesis entry (seq={seq}) has non-null previous_chain_hash"
                    )
                expected_prev = None
            else:
                expected_prev = rows[i - 1][3]  # chain_hash of previous row
                if stored_prev != expected_prev:
                    errors.append(
                        f"Chain break at seq={seq}: stored prev "
                        f"{stored_prev[:16]}... != expected {expected_prev[:16]}..."
                    )

            # Recompute chain_hash and compare
            recomputed = compute_chain_hash(event_hash, stored_prev)
            if recomputed != stored_chain:
                errors.append(
                    f"Tamper detected at seq={seq}: recomputed chain_hash "
                    f"{recomputed[:16]}... != stored {stored_chain[:16]}..."
                )

        return ChainVerification(
            valid=len(errors) == 0,
            chain_length=len(rows),
            errors=errors,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    # ------------------------------------------------------------------
    # Export Support
    # ------------------------------------------------------------------

    def log_export(
        self,
        tenant_id: str,
        export_hash: str,
        record_count: int,
        query_tlc: Optional[str] = None,
        query_start_date: Optional[str] = None,
        query_end_date: Optional[str] = None,
        generated_by: Optional[str] = None,
    ) -> str:
        """Log an FDA export event and return the export log ID."""
        export_id = str(uuid4())
        self.session.execute(
            text("""
                INSERT INTO fsma.fda_export_log (
                    id, tenant_id, query_tlc, query_start_date, query_end_date,
                    record_count, export_hash, generated_by
                ) VALUES (
                    :id, :tid, :tlc, :start, :end, :count, :hash, :by
                )
            """),
            {
                "id": export_id,
                "tid": tenant_id,
                "tlc": query_tlc,
                "start": query_start_date,
                "end": query_end_date,
                "count": record_count,
                "hash": export_hash,
                "by": generated_by,
            },
        )
        return export_id

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
            event_id = str(row[0])
            kdes = self.session.execute(
                text("""
                    SELECT kde_key, kde_value
                    FROM fsma.cte_kdes
                    WHERE cte_event_id = :eid AND tenant_id = :tid
                """),
                {"eid": event_id, "tid": tenant_id},
            ).fetchall()

            events.append({
                "id": event_id,
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
                "kdes": {k[0]: k[1] for k in kdes},
            })

        return events
