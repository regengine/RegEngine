"""Best-effort audit emission for the remediation slice.

AuditLogger lives in the admin domain; in the consolidated monolith the
import always works, but the per-service ingestion CI matrix must not gain
an admin dependency, so the import is lazy and failures degrade to a log
line (AuditLogger.log_event is itself best-effort by design).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("remediation.audit")

EVENT_CATEGORY = "supplier_remediation"


def audit_event(
    db,
    *,
    tenant_id: str,
    event_type: str,
    action: str,
    severity: str = "info",
    actor_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    import uuid as _uuid

    actor_uuid: Optional[str] = None
    if actor_id is not None:
        try:
            actor_uuid = str(_uuid.UUID(str(actor_id)))
        except (ValueError, AttributeError, TypeError):
            # audit_logs.actor_id is UUID-typed; keep non-UUID actor labels
            # (e.g. API-key ids, "system") in metadata instead of failing
            # the hash-chain INSERT and poisoning the transaction.
            metadata = {**(metadata or {}), "actor_label": str(actor_id)}

    try:
        from services.admin.app.audit import AuditLogger

        # Savepoint so a failed audit INSERT cannot poison the caller's
        # transaction (AuditLogger swallows its own error but the aborted
        # DB transaction would otherwise kill every later statement).
        with db.begin_nested():
            AuditLogger.log_event(
                db,
                tenant_id=tenant_id,
                event_type=event_type,
                action=action,
                event_category=EVENT_CATEGORY,
                severity=severity,
                actor_id=actor_uuid,
                resource_type=resource_type,
                resource_id=resource_id,
                metadata=metadata or {},
            )
    except Exception as exc:  # pragma: no cover — degraded path
        logger.warning(
            "remediation_audit_degraded event_type=%s tenant=%s error=%s",
            event_type,
            tenant_id,
            exc,
        )
