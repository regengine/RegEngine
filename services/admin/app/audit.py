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
from sqlalchemy.orm import Session

from app.sqlalchemy_models import AuditLogModel

logger = structlog.get_logger("audit")


def compute_integrity_hash(
    prev_hash: Optional[str],
    tenant_id: str,
    timestamp: str,
    event_type: str,
    action: str,
    resource_id: Optional[str],
    metadata: dict,
) -> str:
    """
    SHA-256 hash chain. Each entry's hash depends on the previous entry,
    making retroactive tampering detectable.

    The payload is canonicalized (sorted keys, deterministic serialization)
    to ensure reproducibility across platforms.
    """
    payload = json.dumps(
        {
            "prev_hash": prev_hash or "GENESIS",
            "tenant_id": str(tenant_id),
            "timestamp": timestamp,
            "event_type": event_type,
            "action": action,
            "resource_id": str(resource_id) if resource_id else None,
            "metadata": metadata,
        },
        sort_keys=True,
        default=str,
    )
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

            # Compute integrity hash
            integrity_hash = compute_integrity_hash(
                prev_hash=prev_hash,
                tenant_id=str(tenant_id),
                timestamp=now_iso,
                event_type=event_type,
                action=action,
                resource_id=resource_id,
                metadata=meta,
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

        except (ValueError, RuntimeError, OSError, AttributeError, TypeError, KeyError) as e:
            logger.error(
                "audit_logging_failed",
                error=str(e),
                event_type=event_type,
                action=action,
            )
            return None
