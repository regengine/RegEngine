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
from typing import Optional, Dict, Any
from uuid import UUID

import structlog
from sqlalchemy import select, desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .sqlalchemy_models import AuditLogModel

logger = structlog.get_logger("audit")


# #1415: audit chain integrity hash schema version. v1 hashed only
# tenant/timestamp/event_type/action/resource_id/metadata, which let a
# SQL-capable attacker rewrite actor_id/actor_email/severity/endpoint
# without breaking the chain — defeating the FDA-relevant "who did
# this" tamper-evidence guarantee. v2 folds all four actor/audit fields
# into the hash input. Existing v1 rows remain verifiable via a
# fallback in verify_chain.
_AUDIT_HASH_VERSION_V1 = 1
_AUDIT_HASH_VERSION_V2 = 2


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
    version: int = _AUDIT_HASH_VERSION_V2,
) -> str:
    """
    SHA-256 hash chain. Each entry's hash depends on the previous entry,
    making retroactive tampering detectable.

    #1415: v2 (new default) folds ``actor_id``, ``actor_email``,
    ``severity``, and ``endpoint`` into the hash input. v1 kept only
    the tenant/timestamp/event fields, so actor fields could be
    rewritten in-place by a DB-capable attacker without breaking the
    chain. v1 is still accepted by ``verify_chain`` for backwards
    compatibility with pre-#1415 rows.

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
        body["version"] = _AUDIT_HASH_VERSION_V2
        body["actor_id"] = str(actor_id) if actor_id else None
        body["actor_email"] = actor_email
        body["severity"] = severity
        body["endpoint"] = endpoint

    payload = json.dumps(body, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditLogger:
    """Tamper-evident audit logger with SHA-256 hash chain."""

    @staticmethod
    def _get_prev_hash(db: Session, tenant_id: UUID) -> Optional[str]:
        """Fetch the integrity_hash of the most recent audit entry for this tenant."""
        stmt = (
            select(AuditLogModel.integrity_hash)
            .where(AuditLogModel.tenant_id == tenant_id)
            .order_by(desc(AuditLogModel.id))
            .limit(1)
        )
        result = db.execute(stmt).scalar_one_or_none()
        return result

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
            # Get previous hash for chain
            prev_hash = AuditLogger._get_prev_hash(db, tenant_id)

            # Compute integrity hash (v2 — folds actor fields into the
            # hash input per #1415 so SQL-rewrite of actor_id /
            # actor_email / severity / endpoint breaks the chain).
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
            logger.error(
                "audit_logging_failed",
                error=str(e),
                event_type=event_type,
                action=action,
            )
            return None
