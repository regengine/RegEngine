"""
Audit Logger — Tamper-Evident Event Capture
ISO 27001: 12.4.1, 12.4.2, 12.4.3

Every security-relevant event is logged with a SHA-256 hash chain.
Each entry's integrity_hash depends on the previous entry's hash,
making retroactive tampering detectable.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import desc, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .sqlalchemy_models import AuditLogModel

logger = structlog.get_logger("audit")


# Counter so the "best-effort" failure mode below is alertable.
# Without this, audit_logging_failed only emitted a structured log line
# with no metric, so an outage where the chain stopped writing was
# invisible to ops until the subsequent audit-export run. Pattern
# matches the duplicate guard used in review_consumer.py for
# double-import safety.
try:
    from prometheus_client import Counter

    AUDIT_LOG_FAILURES_COUNTER = Counter(
        "admin_audit_log_failures_total",
        "Audit log entries that failed to persist (caught at the swallow-and-return-None boundary in AuditLogger.log_event).",
        ["event_type", "error_class"],
    )
except ImportError:  # prometheus_client not installed
    AUDIT_LOG_FAILURES_COUNTER = None
except ValueError:  # already registered (double-import / module reload)
    from prometheus_client import REGISTRY

    AUDIT_LOG_FAILURES_COUNTER = REGISTRY._names_to_collectors.get("admin_audit_log_failures_total")


# #1415: audit chain integrity hash schema version. v1 hashed only
# tenant/timestamp/event_type/action/resource_id/metadata, which let a
# SQL-capable attacker rewrite actor_id/actor_email/severity/endpoint
# without breaking the chain — defeating the FDA-relevant "who did
# this" tamper-evidence guarantee. v2 folds all four actor/audit fields
# into the hash input. Existing v1 rows remain verifiable via a
# fallback in verify_chain.
#
# #2513: v3 folds the per-tenant ``sequence_num`` into the hash input.
# Without it, a forked or reordered chain (concurrent writers chaining
# off the same head) and a removed middle row could not be detected by
# the hash alone. The per-tenant advisory lock + UNIQUE (tenant_id,
# sequence_num) constraint serialize chain growth; binding the sequence
# into the hash makes reordering/removal break the hash too. v1/v2 rows
# remain verifiable via fallbacks in verify_chain.
_AUDIT_HASH_VERSION_V1 = 1
_AUDIT_HASH_VERSION_V2 = 2
_AUDIT_HASH_VERSION_V3 = 3


def compute_integrity_hash(
    prev_hash: Optional[str],
    tenant_id: str,
    timestamp: str,
    event_type: str,
    action: str,
    resource_id: Optional[str],
    metadata: dict,
    *,
    actor_id: Optional[str] = None,
    actor_email: Optional[str] = None,
    severity: Optional[str] = None,
    endpoint: Optional[str] = None,
    sequence_num: Optional[int] = None,
    version: int = _AUDIT_HASH_VERSION_V3,
) -> str:
    """
    SHA-256 hash chain. Each entry's hash depends on the previous entry,
    making retroactive tampering detectable.

    #1415: v2 folds ``actor_id``, ``actor_email``, ``severity``, and
    ``endpoint`` into the hash input. v1 kept only the
    tenant/timestamp/event fields, so actor fields could be rewritten
    in-place by a DB-capable attacker without breaking the chain.

    #2513: v3 (new default) additionally folds the per-tenant
    ``sequence_num`` into the hash input so a forked head (two entries
    sharing a ``prev_hash``) or a removed middle row is detectable from
    the hash, not just the prev_hash linkage. v1/v2 are still accepted
    by ``verify_chain`` for backwards compatibility with older rows.

    The payload is canonicalized (sorted keys, deterministic
    serialization) to ensure reproducibility across platforms.
    """
    body: dict = {
        "prev_hash": prev_hash or "GENESIS",
        "tenant_id": str(tenant_id),
        "timestamp": timestamp,
        "event_type": event_type,
        "action": action,
        "resource_id": str(resource_id) if resource_id else None,
        "metadata": metadata,
    }
    if version >= _AUDIT_HASH_VERSION_V2:
        # v2/v3 both carry the actor/audit fields. ``version`` records
        # the schema version actually used so verify_chain knows which
        # fields participated.
        body["version"] = version
        body["actor_id"] = str(actor_id) if actor_id else None
        body["actor_email"] = actor_email
        body["severity"] = severity
        body["endpoint"] = endpoint
    if version >= _AUDIT_HASH_VERSION_V3:
        body["sequence_num"] = sequence_num

    payload = json.dumps(body, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditLogger:
    """Tamper-evident audit logger with SHA-256 hash chain."""

    @staticmethod
    def _acquire_chain_lock(db: Session, tenant_id: UUID) -> None:
        """Serialize per-tenant chain growth with a transaction-scoped lock.

        #2513: ``_get_chain_head`` reads the current head with ``ORDER BY
        id DESC LIMIT 1`` and **locks nothing** (on a tenant's first
        event it returns zero rows). Two concurrent ``log_event`` calls
        for the same tenant would both observe the same head, chain off
        the same ``prev_hash`` and compute the same ``sequence_num``,
        forking the chain. ``pg_advisory_xact_lock(hashtext(tenant_id))``
        serializes the read-then-insert critical section per tenant; the
        lock releases automatically at COMMIT / ROLLBACK. Mirrors
        ``cte_persistence.writes`` (#1332) and ``canonical_persistence.
        writer`` (#1251). SQLite (test DB) is single-writer, so the lock
        is a no-op there.
        """
        if db.bind is not None and db.bind.dialect.name == "sqlite":
            return
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:tid))"), {"tid": str(tenant_id)})

    @staticmethod
    def _get_chain_head(db: Session, tenant_id: UUID) -> Tuple[Optional[str], int]:
        """Return ``(prev_hash, sequence_num)`` for this tenant's chain head.

        ``sequence_num`` is the contiguous per-tenant sequence to assign
        to the *next* entry (1 for a tenant's first entry). Must be
        called while holding the per-tenant advisory lock (#2513) so two
        concurrent writers cannot both compute the same next sequence.
        """
        stmt = (
            select(AuditLogModel.integrity_hash, AuditLogModel.sequence_num)
            .where(AuditLogModel.tenant_id == tenant_id)
            .order_by(desc(AuditLogModel.id))
            .limit(1)
        )
        row = db.execute(stmt).one_or_none()
        if row is None:
            return None, 1
        prev_hash, head_seq = row
        # head_seq is None only for legacy rows written before the #2513
        # backfill; treat the next sequence as best-effort 1-based on top
        # of the row count fallback so contiguity is preserved going
        # forward.
        next_seq = (head_seq + 1) if head_seq is not None else 1
        return prev_hash, next_seq

    @staticmethod
    def _get_prev_hash(db: Session, tenant_id: UUID) -> Optional[str]:
        """Fetch the integrity_hash of the most recent audit entry for this tenant.

        Retained for backwards compatibility with existing callers/tests;
        ``log_event`` now uses :meth:`_get_chain_head` to also obtain the
        per-tenant ``sequence_num`` (#2513).
        """
        prev_hash, _ = AuditLogger._get_chain_head(db, tenant_id)
        return prev_hash

    @staticmethod
    def log_event(
        db: Session,
        tenant_id: UUID,
        event_type: str,
        action: str,
        event_category: str,
        severity: str = "info",
        actor_id: Optional[UUID] = None,
        # actor_email is stored unmasked intentionally — FSMA 204 (21 CFR Part 1,
        # Subpart S) requires traceability of record actions to specific individuals.
        # This constitutes a legitimate interest basis under GDPR Art. 6(1)(f).
        actor_email: Optional[str] = None,
        actor_ip: Optional[str] = None,
        actor_ua: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        request_id: Optional[UUID] = None,
    ) -> Optional[int]:
        """
        Insert a tamper-evident audit log entry.

        The entry's integrity_hash is computed from the previous entry's hash
        plus the current entry's content, creating an unbreakable chain.

        Returns the new entry's ID, or None if logging fails.
        """
        meta = metadata or {}
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        try:
            # Serialize per-tenant chain growth before reading the head
            # (#2513) so concurrent same-tenant writers cannot fork the
            # chain off a shared prev_hash / sequence_num.
            AuditLogger._acquire_chain_lock(db, tenant_id)

            # Get previous hash + next contiguous per-tenant sequence.
            prev_hash, sequence_num = AuditLogger._get_chain_head(db, tenant_id)

            # Compute integrity hash (v3 — folds actor fields per #1415
            # and the per-tenant sequence_num per #2513 so SQL-rewrite of
            # actor_id / actor_email / severity / endpoint, or reordering
            # / removal of a chain entry, breaks the chain).
            integrity_hash = compute_integrity_hash(
                prev_hash=prev_hash,
                tenant_id=str(tenant_id),
                timestamp=now_iso,
                event_type=event_type,
                action=action,
                resource_id=resource_id,
                metadata=meta,
                actor_id=str(actor_id) if actor_id else None,
                actor_email=actor_email,
                severity=severity,
                endpoint=endpoint,
                sequence_num=sequence_num,
            )

            # Truncate user agent to prevent storage bloat
            if actor_ua and len(actor_ua) > 512:
                actor_ua = actor_ua[:512]

            entry = AuditLogModel(
                tenant_id=tenant_id,
                timestamp=now,
                actor_id=actor_id,
                actor_email=actor_email,
                actor_ip=actor_ip,
                actor_ua=actor_ua,
                event_type=event_type,
                event_category=event_category,
                action=action,
                severity=severity,
                resource_type=resource_type,
                resource_id=resource_id,
                endpoint=endpoint,
                metadata_=meta,
                request_id=request_id,
                prev_hash=prev_hash,
                sequence_num=sequence_num,
                integrity_hash=integrity_hash,
            )
            db.add(entry)
            # Flush to get the ID but don't commit — caller controls the transaction
            db.flush()

            logger.info(
                "audit_event_logged",
                event_type=event_type,
                action=action,
                actor_id=str(actor_id) if actor_id else "system",
                tenant_id=str(tenant_id),
                entry_id=entry.id,
                chain_hash=integrity_hash[:12],
            )
            return entry.id

        except (
            ValueError,
            RuntimeError,
            OSError,
            AttributeError,
            TypeError,
            KeyError,
            SQLAlchemyError,
        ) as e:
            # SQLAlchemyError covers ProgrammingError from schema drift
            # (e.g. audit_logs column type mismatch): without it, a failure
            # in _get_prev_hash or db.flush() propagates into the caller's
            # transaction, aborting subsequent queries with
            # InFailedSqlTransaction. Catching here keeps audit logging
            # best-effort; callers that continue using the same Session
            # after a None result must rollback before further writes. The
            # schema issues are root-cause fixed in Alembic v065/v070.
            if AUDIT_LOG_FAILURES_COUNTER is not None:
                AUDIT_LOG_FAILURES_COUNTER.labels(
                    event_type=event_type,
                    error_class=type(e).__name__,
                ).inc()
            logger.error(
                "audit_logging_failed",
                error=str(e),
                error_class=type(e).__name__,
                event_type=event_type,
                action=action,
                tenant_id=str(tenant_id),
            )
            return None
