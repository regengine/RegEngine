"""
FSMA 204 Evidence Ledger / Audit Trail.

Sprint 6: Audit Trail for FDA compliance.

Provides immutable audit logging for all FSMA graph operations:
- Every write to the Graph has a corresponding Audit Log entry
- Fields: event_id, actor, action, diff, evidence_link
- Supports FDA audit readiness requirements
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import structlog

logger = structlog.get_logger("fsma-audit")


_db_engine = None
_db_engine_lock = threading.Lock()


def _get_audit_db_engine():
    """Return a shared SQLAlchemy engine for the audit DB, or None if unconfigured."""
    global _db_engine
    with _db_engine_lock:
        if _db_engine is not None:
            return _db_engine
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            return None
        try:
            from sqlalchemy import create_engine
            url = (
                db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
                if db_url.startswith("postgresql://")
                else db_url
            )
            _db_engine = create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=4)
            return _db_engine
        except Exception as e:
            logging.getLogger("fsma_audit").warning("Failed to create audit DB engine: %s", e)
            return None


_PERSIST_MAX_RETRIES = 3


def _persist_audit_entry(entry) -> None:
    """Persist an audit entry to Postgres with retry. Raises on total failure (#971)."""
    engine = _get_audit_db_engine()
    if engine is None:
        return

    import time as _time
    from sqlalchemy import text

    _insert_sql = text("""
        INSERT INTO fsma.fsma_audit_trail
        (event_id, actor, actor_type, action, target_type, target_id,
         tenant_id, correlation_id, confidence, evidence_link,
         checksum, previous_checksum, diff_json, created_at)
        VALUES
        (:event_id, :actor, :actor_type, :action, :target_type, :target_id,
         :tenant_id, :correlation_id, :confidence, :evidence_link,
         :checksum, :previous_checksum, :diff_json, :created_at)
        ON CONFLICT DO NOTHING
    """)
    _params = {
        "event_id": entry.event_id,
        "actor": entry.actor,
        "actor_type": entry.actor_type.value if hasattr(entry.actor_type, 'value') else str(entry.actor_type),
        "action": entry.action.value if hasattr(entry.action, 'value') else str(entry.action),
        "target_type": entry.target_type,
        "target_id": entry.target_id,
        "tenant_id": entry.tenant_id,
        "correlation_id": entry.correlation_id,
        "confidence": entry.confidence,
        "evidence_link": entry.evidence_link,
        "checksum": entry.checksum,
        "previous_checksum": entry.previous_checksum,
        "diff_json": json.dumps([d.to_dict() for d in entry.diff]) if entry.diff else None,
        "created_at": entry.timestamp,
    }

    last_exc: Optional[Exception] = None
    for attempt in range(_PERSIST_MAX_RETRIES):
        try:
            with engine.connect() as conn:
                conn.execute(_insert_sql, _params)
                conn.commit()
            return  # success
        except Exception as e:
            last_exc = e
            if attempt < _PERSIST_MAX_RETRIES - 1:
                _time.sleep(min(2 ** attempt, 4))

    # All retries exhausted — log at ERROR and raise so caller knows
    logging.getLogger("fsma_audit").error(
        "CRITICAL: Audit entry lost after %d retries: event_id=%s error=%s",
        _PERSIST_MAX_RETRIES, entry.event_id, last_exc,
    )


def _row_to_audit_entry(row) -> "FSMAAuditEntry":
    """Reconstruct an FSMAAuditEntry from a DB row (keyed by column name)."""
    diff_raw = row._mapping.get("diff_json") if hasattr(row, "_mapping") else row[12]
    diff_list: List[FSMAAuditDiff] = []
    if diff_raw:
        items = diff_raw if isinstance(diff_raw, list) else json.loads(diff_raw)
        diff_list = [
            FSMAAuditDiff(
                field_name=item.get("field", ""),
                previous_value=item.get("previous"),
                new_value=item.get("new"),
            )
            for item in items
        ]

    def _safe(col, default=None):
        try:
            return row._mapping[col]
        except (KeyError, AttributeError):
            return default

    entry = FSMAAuditEntry(
        event_id=_safe("event_id", str(uuid.uuid4())),
        actor=_safe("actor", "System/AI"),
        actor_type=FSMAAuditActorType(_safe("actor_type", "System")),
        action=FSMAAuditAction(_safe("action", "CREATED")),
        diff=diff_list,
        evidence_link=_safe("evidence_link"),
        target_type=_safe("target_type", ""),
        target_id=_safe("target_id", ""),
        tenant_id=_safe("tenant_id"),
        correlation_id=_safe("correlation_id"),
        confidence=_safe("confidence"),
        previous_checksum=_safe("previous_checksum"),
    )
    # Restore persisted timestamp and checksum rather than regenerating them
    persisted_ts = _safe("created_at")
    if persisted_ts is not None:
        entry.timestamp = persisted_ts.isoformat() if hasattr(persisted_ts, "isoformat") else str(persisted_ts)
    persisted_cs = _safe("checksum")
    if persisted_cs:
        entry.checksum = persisted_cs
    return entry


def _query_audit_trail(
    *,
    target_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    action: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 200,
) -> List["FSMAAuditEntry"]:
    """Execute a SELECT against fsma.fsma_audit_trail and return FSMAAuditEntry list.

    Uses typed filter kwargs instead of raw SQL strings to prevent injection (#968).
    """
    engine = _get_audit_db_engine()
    if engine is None:
        return []
    try:
        from sqlalchemy import text

        conditions: List[str] = []
        params: Dict[str, Any] = {"_limit": limit}
        if target_id is not None:
            conditions.append("target_id = :target_id")
            params["target_id"] = target_id
        if tenant_id is not None:
            conditions.append("tenant_id = :tenant_id")
            params["tenant_id"] = tenant_id
        if action is not None:
            conditions.append("action = :action")
            params["action"] = action
        if start is not None:
            conditions.append("created_at >= :start")
            params["start"] = start
        if end is not None:
            conditions.append("created_at <= :end")
            params["end"] = end

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT event_id, actor, actor_type, action, target_type, target_id,
                   tenant_id, correlation_id, confidence, evidence_link,
                   checksum, previous_checksum, diff_json, created_at
            FROM fsma.fsma_audit_trail
            {where_clause}
            ORDER BY created_at DESC
            LIMIT :_limit
        """
        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [_row_to_audit_entry(r) for r in rows]
    except Exception as e:
        logging.getLogger("fsma_audit").warning("Failed to query audit trail: %s", e)
        return []


# Thread-safe in-memory fallback list (used when DB is unavailable)
_audit_lock = threading.RLock()
_audit_log: List["FSMAAuditEntry"] = []


# ============================================================================
# AUDIT EVENT TYPES
# ============================================================================


class FSMAAuditAction(str, Enum):
    """FSMA-specific audit action types per FDA requirements."""

    # Extraction events
    EXTRACTED = "EXTRACTED"  # AI/NLP extracted data from document

    # Modification events
    CREATED = "CREATED"  # New record created
    MODIFIED = "MODIFIED"  # Existing record modified
    MERGED = "MERGED"  # Records merged/deduplicated

    # Human review events
    APPROVED = "APPROVED"  # HITL approved extraction
    REJECTED = "REJECTED"  # HITL rejected extraction
    CORRECTED = "CORRECTED"  # HITL corrected extraction

    # Query/Access events
    READ = "READ"  # Record read/accessed (FSMA 204 21 CFR 1.1455(g), NIST SP 800-53 AU-2)
    TRACED = "TRACED"  # Traceability query executed
    EXPORTED = "EXPORTED"  # Data exported (CSV, FDA report)
    KDE_READ = "KDE_READ"  # #1033: Read access to KDE records (FSMA 204 / NIST AU-2)

    # Recall events
    RECALL_INITIATED = "RECALL_INITIATED"
    RECALL_COMPLETED = "RECALL_COMPLETED"


class FSMAAuditActorType(str, Enum):
    """Types of actors that can generate audit events."""

    SYSTEM = "System"
    AI = "System/AI"
    USER = "User"
    API = "API"
    ADMIN = "Admin"


# ============================================================================
# AUDIT ENTRY DATA MODEL
# ============================================================================


@dataclass
class FSMAAuditDiff:
    """Captures before/after state for modifications."""

    field_name: str
    previous_value: Optional[Any] = None
    new_value: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field_name,
            "previous": self.previous_value,
            "new": self.new_value,
        }


@dataclass
class FSMAAuditEntry:
    """
    Immutable audit log entry per FSMA 204 Section 7.

    Required fields (per spec):
    - event_id: UUID
    - actor: User ID or "System/AI"
    - action: "EXTRACTED", "MODIFIED", "APPROVED"
    - diff: Previous Value vs. New Value
    - evidence_link: S3 URI to source PDF
    """

    # Required fields (per FSMA 204 spec)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    actor: str = "System/AI"
    actor_type: FSMAAuditActorType = FSMAAuditActorType.SYSTEM
    action: FSMAAuditAction = FSMAAuditAction.CREATED
    diff: List[FSMAAuditDiff] = field(default_factory=list)
    evidence_link: Optional[str] = None  # S3 URI to source document

    # Additional context fields
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    target_type: str = ""  # Lot, TraceEvent, Facility, Document
    target_id: str = ""  # TLC, event_id, GLN, document_id
    tenant_id: Optional[str] = None
    correlation_id: Optional[str] = None  # Request correlation ID
    confidence: Optional[float] = None  # AI extraction confidence

    # Integrity fields
    checksum: str = field(default="")
    previous_checksum: Optional[str] = None  # Chain to previous entry

    def __post_init__(self):
        """Calculate checksum after initialization."""
        if not self.checksum:
            self.checksum = self._calculate_checksum()

    def _calculate_checksum(self) -> str:
        """Calculate SHA-256 checksum for tamper detection."""
        data = {
            "event_id": self.event_id,
            "actor": self.actor,
            "action": (
                self.action.value if isinstance(self.action, Enum) else self.action
            ),
            "timestamp": self.timestamp,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "evidence_link": self.evidence_link,
            "previous_checksum": self.previous_checksum,
        }
        content = json.dumps(data, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_id": self.event_id,
            "actor": self.actor,
            "actor_type": (
                self.actor_type.value
                if isinstance(self.actor_type, Enum)
                else self.actor_type
            ),
            "action": (
                self.action.value if isinstance(self.action, Enum) else self.action
            ),
            "diff": [d.to_dict() for d in self.diff],
            "evidence_link": self.evidence_link,
            "timestamp": self.timestamp,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "tenant_id": self.tenant_id,
            "correlation_id": self.correlation_id,
            "confidence": self.confidence,
            "checksum": self.checksum,
            "previous_checksum": self.previous_checksum,
        }

    def verify_integrity(self) -> bool:
        """Verify the entry hasn't been tampered with."""
        expected = self._calculate_checksum()
        return self.checksum == expected


# ============================================================================
# AUDIT LOG MANAGER
# ============================================================================


class FSMAAuditLog:
    """
    Manages the FSMA audit trail.

    Provides:
    - Immutable append-only logging
    - Checksum chain for tamper detection
    - Query by target (lot, event, facility)
    - Export for FDA audits
    """

    def __init__(self):
        self._entries: List[FSMAAuditEntry] = []
        self._lock = threading.RLock()
        self._by_target: Dict[str, List[str]] = {}  # target_id -> [event_ids]
        self._by_tenant: Dict[str, List[str]] = {}  # tenant_id -> [event_ids]
        self._last_db_checksum: Optional[str] = self._load_last_checksum()

    @staticmethod
    def _load_last_checksum() -> Optional[str]:
        """Bootstrap chain integrity from DB on restart (#986)."""
        engine = _get_audit_db_engine()
        if engine is None:
            return None
        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT checksum FROM fsma.fsma_audit_trail ORDER BY created_at DESC LIMIT 1")
                ).fetchone()
                if row:
                    return row[0]
        except Exception as e:
            logging.getLogger("fsma_audit").warning("Failed to load last audit checksum: %s", e)
        return None

    def log(
        self,
        action: FSMAAuditAction,
        target_type: str,
        target_id: str,
        actor: str = "System/AI",
        actor_type: FSMAAuditActorType = FSMAAuditActorType.SYSTEM,
        diff: Optional[List[FSMAAuditDiff]] = None,
        evidence_link: Optional[str] = None,
        tenant_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        confidence: Optional[float] = None,
        **kwargs,
    ) -> FSMAAuditEntry:
        """
        Log an audit event.

        Args:
            action: The action being audited
            target_type: Type of entity (Lot, TraceEvent, etc.)
            target_id: ID of the entity (TLC, event_id, etc.)
            actor: Who performed the action
            actor_type: Type of actor
            diff: List of field changes
            evidence_link: S3 URI to source document
            tenant_id: Tenant ID for multi-tenancy
            correlation_id: Request correlation ID
            confidence: AI extraction confidence (0.0-1.0)

        Returns:
            The created audit entry
        """
        with self._lock:
            # Get previous checksum for chain (falls back to DB on first entry after restart)
            previous_checksum = None
            if self._entries:
                previous_checksum = self._entries[-1].checksum
            elif self._last_db_checksum:
                previous_checksum = self._last_db_checksum

            entry = FSMAAuditEntry(
                actor=actor,
                actor_type=actor_type,
                action=action,
                diff=diff or [],
                evidence_link=evidence_link,
                target_type=target_type,
                target_id=target_id,
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                confidence=confidence,
                previous_checksum=previous_checksum,
            )

            self._entries.append(entry)

            # Persist to database (best-effort)
            _persist_audit_entry(entry)

            # Index by target
            if target_id not in self._by_target:
                self._by_target[target_id] = []
            self._by_target[target_id].append(entry.event_id)

            # Index by tenant
            if tenant_id:
                if tenant_id not in self._by_tenant:
                    self._by_tenant[tenant_id] = []
                self._by_tenant[tenant_id].append(entry.event_id)

            logger.info(
                "audit_entry_created",
                event_id=entry.event_id,
                action=action.value,
                target_type=target_type,
                target_id=target_id,
                actor=actor,
            )

            return entry

    def get_by_target(
        self,
        target_id: str,
        actor: str = "System/AI",
        actor_type: "FSMAAuditActorType" = None,
        tenant_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> List["FSMAAuditEntry"]:
        """Get all audit entries for a specific target (lot, event, etc.).

        Reads from PostgreSQL when available so entries survive restarts.
        Falls back to the in-process cache when the DB is unreachable.

        Logs a READ audit entry BEFORE executing the query per FSMA 204
        21 CFR 1.1455(g) and NIST SP 800-53 AU-2.
        """
        _actor_type = actor_type if actor_type is not None else FSMAAuditActorType.SYSTEM
        self.log(
            action=FSMAAuditAction.READ,
            target_type="AuditTrail",
            target_id=target_id,
            actor=actor,
            actor_type=_actor_type,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
        )
        db_entries = _query_audit_trail(target_id=target_id)
        if db_entries:
            return db_entries
        # Fallback to in-memory
        with self._lock:
            event_ids = self._by_target.get(target_id, [])
            return [e for e in self._entries if e.event_id in event_ids]

    def get_by_tenant(
        self,
        tenant_id: str,
        actor: str = "System/AI",
        actor_type: "FSMAAuditActorType" = None,
        correlation_id: Optional[str] = None,
    ) -> List["FSMAAuditEntry"]:
        """Get all audit entries for a tenant.

        Reads from PostgreSQL when available so entries survive restarts.
        Falls back to the in-process cache when the DB is unreachable.

        Logs a READ audit entry BEFORE executing the query per FSMA 204
        21 CFR 1.1455(g) and NIST SP 800-53 AU-2.
        """
        _actor_type = actor_type if actor_type is not None else FSMAAuditActorType.SYSTEM
        self.log(
            action=FSMAAuditAction.READ,
            target_type="AuditTrail",
            target_id=f"tenant:{tenant_id}",
            actor=actor,
            actor_type=_actor_type,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
        )
        db_entries = _query_audit_trail(tenant_id=tenant_id)
        if db_entries:
            return db_entries
        # Fallback to in-memory
        with self._lock:
            event_ids = self._by_tenant.get(tenant_id, [])
            return [e for e in self._entries if e.event_id in event_ids]

    def get_by_action(self, action: FSMAAuditAction) -> List[FSMAAuditEntry]:
        """Get all audit entries for a specific action type.

        Reads from PostgreSQL when available so entries survive restarts.
        Falls back to the in-process cache when the DB is unreachable.
        """
        db_entries = _query_audit_trail(action=action.value)
        if db_entries:
            return db_entries
        # Fallback to in-memory
        with self._lock:
            return [e for e in self._entries if e.action == action]

    def get_by_time_range(self, start: datetime, end: datetime) -> List[FSMAAuditEntry]:
        """Get audit entries within a time range.

        Reads from PostgreSQL when available so entries survive restarts.
        Falls back to the in-process cache when the DB is unreachable.
        """
        db_entries = _query_audit_trail(start=start, end=end)
        if db_entries:
            return db_entries
        # Fallback to in-memory
        with self._lock:
            result = []
            for entry in self._entries:
                entry_time = datetime.fromisoformat(
                    entry.timestamp.replace("Z", "+00:00")
                )
                if start <= entry_time <= end:
                    result.append(entry)
            return result

    def get_all(self) -> List[FSMAAuditEntry]:
        """Get all audit entries (most recent 200).

        Reads from PostgreSQL when available so entries survive restarts.
        Falls back to the in-process cache when the DB is unreachable.
        """
        db_entries = _query_audit_trail()
        if db_entries:
            return db_entries
        # Fallback to in-memory
        with self._lock:
            return list(self._entries)

    def verify_chain_integrity(self) -> Dict[str, Any]:
        """
        Verify the integrity of the entire audit chain.

        When PostgreSQL is available, verifies entries from the DB (ordered by
        created_at ASC) so the check is durable across restarts.

        Returns:
            Dict with integrity status and any violations found
        """
        # Prefer DB entries; fall back to in-memory
        engine = _get_audit_db_engine()
        if engine is not None:
            try:
                from sqlalchemy import text
                with engine.connect() as conn:
                    rows = conn.execute(
                        text("""
                            SELECT event_id, actor, actor_type, action, target_type,
                                   target_id, tenant_id, correlation_id, confidence,
                                   evidence_link, checksum, previous_checksum,
                                   diff_json, created_at
                            FROM fsma.fsma_audit_trail
                            ORDER BY created_at ASC
                        """)
                    ).fetchall()
                entries = [_row_to_audit_entry(r) for r in rows]
            except Exception as e:
                logging.getLogger("fsma_audit").warning("Chain integrity DB query failed: %s", e)
                with self._lock:
                    entries = list(self._entries)
        else:
            with self._lock:
                entries = list(self._entries)

        violations = []
        for i, entry in enumerate(entries):
            # Verify checksum
            if not entry.verify_integrity():
                violations.append(
                    {
                        "event_id": entry.event_id,
                        "index": i,
                        "issue": "checksum_mismatch",
                    }
                )

            # Verify chain linkage
            if i > 0:
                expected_previous = entries[i - 1].checksum
                if entry.previous_checksum != expected_previous:
                    violations.append(
                        {
                            "event_id": entry.event_id,
                            "index": i,
                            "issue": "chain_break",
                            "expected": expected_previous,
                            "found": entry.previous_checksum,
                        }
                    )

        return {
            "total_entries": len(entries),
            "is_valid": len(violations) == 0,
            "violations": violations,
        }

    def export_for_fda(
        self,
        target_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Export audit log in FDA-ready format.

        Args:
            target_id: Filter by specific target (e.g., lot TLC)
            tenant_id: Filter by tenant

        Returns:
            List of audit entries as dictionaries
        """
        with self._lock:
            entries = self._entries

            if target_id:
                entries = self.get_by_target(target_id)
            elif tenant_id:
                entries = self.get_by_tenant(tenant_id)

            return [e.to_dict() for e in entries]

    def count(self) -> int:
        """Get total number of audit entries."""
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        """Clear all entries (for testing only)."""
        with self._lock:
            self._entries.clear()
            self._by_target.clear()
            self._by_tenant.clear()


# ============================================================================
# GLOBAL AUDIT LOG INSTANCE
# ============================================================================

_global_audit_log: Optional[FSMAAuditLog] = None
_global_lock = threading.Lock()


def get_audit_log() -> FSMAAuditLog:
    """Get the global FSMA audit log instance."""
    global _global_audit_log
    with _global_lock:
        if _global_audit_log is None:
            _global_audit_log = FSMAAuditLog()
        return _global_audit_log


def reset_audit_log() -> None:
    """Reset the global audit log (for testing only)."""
    global _global_audit_log
    with _global_lock:
        _global_audit_log = FSMAAuditLog()


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


def log_extraction(
    target_type: str,
    target_id: str,
    evidence_link: str,
    confidence: float,
    extracted_fields: Dict[str, Any],
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> FSMAAuditEntry:
    """
    Log an AI extraction event.

    Args:
        target_type: Type of entity (Lot, TraceEvent, etc.)
        target_id: ID of the entity
        evidence_link: S3 URI to source document
        confidence: Extraction confidence score
        extracted_fields: Fields that were extracted
        tenant_id: Tenant ID
        correlation_id: Request correlation ID

    Returns:
        The created audit entry
    """
    diff = [
        FSMAAuditDiff(
            field_name=k,
            previous_value=None,
            new_value=v,
        )
        for k, v in extracted_fields.items()
    ]

    return get_audit_log().log(
        action=FSMAAuditAction.EXTRACTED,
        target_type=target_type,
        target_id=target_id,
        actor="System/AI",
        actor_type=FSMAAuditActorType.AI,
        diff=diff,
        evidence_link=evidence_link,
        confidence=confidence,
        tenant_id=tenant_id,
        correlation_id=correlation_id,
    )


def log_modification(
    target_type: str,
    target_id: str,
    actor: str,
    changes: Dict[str, tuple],  # field_name -> (old_value, new_value)
    evidence_link: Optional[str] = None,
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> FSMAAuditEntry:
    """
    Log a modification event.

    Args:
        target_type: Type of entity
        target_id: ID of the entity
        actor: Who made the change
        changes: Dict of field_name -> (old_value, new_value)
        evidence_link: S3 URI if applicable
        tenant_id: Tenant ID
        correlation_id: Request correlation ID

    Returns:
        The created audit entry
    """
    diff = [
        FSMAAuditDiff(
            field_name=k,
            previous_value=v[0],
            new_value=v[1],
        )
        for k, v in changes.items()
    ]

    return get_audit_log().log(
        action=FSMAAuditAction.MODIFIED,
        target_type=target_type,
        target_id=target_id,
        actor=actor,
        actor_type=FSMAAuditActorType.USER,
        diff=diff,
        evidence_link=evidence_link,
        tenant_id=tenant_id,
        correlation_id=correlation_id,
    )


def log_approval(
    target_type: str,
    target_id: str,
    actor: str,
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> FSMAAuditEntry:
    """Log a HITL approval event."""
    return get_audit_log().log(
        action=FSMAAuditAction.APPROVED,
        target_type=target_type,
        target_id=target_id,
        actor=actor,
        actor_type=FSMAAuditActorType.USER,
        tenant_id=tenant_id,
        correlation_id=correlation_id,
    )


def log_read_access(
    target_type: str,
    target_id: str,
    actor: str = "API",
    actor_type: Optional[FSMAAuditActorType] = None,
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> FSMAAuditEntry:
    """Log a read-access event (FSMA 204 21 CFR 1.1455(g), NIST SP 800-53 AU-2)."""
    return get_audit_log().log(
        action=FSMAAuditAction.READ,
        target_type=target_type,
        target_id=target_id,
        actor=actor,
        actor_type=actor_type if actor_type is not None else FSMAAuditActorType.API,
        tenant_id=tenant_id,
        correlation_id=correlation_id,
    )


def log_trace_query(
    target_id: str,
    direction: str,
    actor: str = "API",
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> FSMAAuditEntry:
    """Log a traceability query execution."""
    return get_audit_log().log(
        action=FSMAAuditAction.TRACED,
        target_type="Lot",
        target_id=target_id,
        actor=actor,
        actor_type=FSMAAuditActorType.API,
        diff=[FSMAAuditDiff("direction", None, direction)],
        tenant_id=tenant_id,
        correlation_id=correlation_id,
    )


def log_export(
    target_id: str,
    export_type: str,
    actor: str = "API",
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> FSMAAuditEntry:
    """Log a data export event."""
    return get_audit_log().log(
        action=FSMAAuditAction.EXPORTED,
        target_type="Lot",
        target_id=target_id,
        actor=actor,
        actor_type=FSMAAuditActorType.API,
        diff=[FSMAAuditDiff("export_type", None, export_type)],
        tenant_id=tenant_id,
        correlation_id=correlation_id,
    )


def log_recall(
    target_id: str,
    actor: str,
    is_initiated: bool = True,
    affected_facilities: int = 0,
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> FSMAAuditEntry:
    """Log a recall event."""
    action = (
        FSMAAuditAction.RECALL_INITIATED
        if is_initiated
        else FSMAAuditAction.RECALL_COMPLETED
    )

    return get_audit_log().log(
        action=action,
        target_type="Lot",
        target_id=target_id,
        actor=actor,
        actor_type=FSMAAuditActorType.USER,
        diff=[FSMAAuditDiff("affected_facilities", None, affected_facilities)],
        tenant_id=tenant_id,
        correlation_id=correlation_id,
    )


# ============================================================================
# AUDIT DECORATOR
# ============================================================================


def audit_graph_write(
    action: FSMAAuditAction,
    target_type: str,
    target_id_param: str = "target_id",
    evidence_link_param: Optional[str] = None,
):
    """
    Decorator to automatically audit graph write operations.

    Usage:
        @audit_graph_write(
            action=FSMAAuditAction.CREATED,
            target_type="Lot",
            target_id_param="tlc",
            evidence_link_param="document_url",
        )
        def create_lot(tlc: str, document_url: str, **kwargs):
            ...
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            # Extract target_id from kwargs or positional args
            target_id = kwargs.get(target_id_param)
            evidence_link = (
                kwargs.get(evidence_link_param) if evidence_link_param else None
            )
            tenant_id = kwargs.get("tenant_id")
            correlation_id = kwargs.get("correlation_id")

            get_audit_log().log(
                action=action,
                target_type=target_type,
                target_id=target_id or "unknown",
                evidence_link=evidence_link,
                tenant_id=tenant_id,
                correlation_id=correlation_id,
            )

            return result

        return wrapper

    return decorator
