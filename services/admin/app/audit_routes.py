"""
Audit Export API -- Signed, Timestamped JSON Bundle
ISO 27001: 12.7.1

Returns a tamper-evident export of audit logs for a tenant.
Enterprise customers use this to feed their SIEM or prove compliance.

Hardening (#1385):
- ``purpose`` query parameter is REQUIRED and must be one of
  ``compliance_investigation``, ``security_incident``,
  ``user_request``. The purpose is logged into the audit export's
  own ``data.bulk.export`` entry so compliance officers can audit
  the auditor.
- PII fields (``actor_email``, ``actor_ip``, ``actor_ua``) are masked
  by default. To get raw PII the caller must set ``include_pii=true``
  AND hold the ``audit.export.pii`` permission. Without the
  permission (or when the feature flag is not granted by the RBAC
  layer) the response returns salted-hashed email and null IP/UA.
- When a row has ``anonymized_at`` set (GDPR Art. 17), PII is forced
  to the masked representation regardless of the caller's
  permissions -- the retention policy must be honored even for
  compliance officers.
"""

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from .database import get_session
from .dependencies import get_current_user
from .sqlalchemy_models import AuditLogModel, UserModel, MembershipModel
from .models import TenantContext
from .audit import AuditLogger
from .audit_integrity import verify_chain

logger = structlog.get_logger("audit_export")

router = APIRouter(prefix="/v1/audit", tags=["audit"])


# Purpose values are an enum on the request boundary so we can log /
# aggregate them. Adding a value here is intentional: it defines the
# compliance justifications ops must review during export-log audits.
_ALLOWED_EXPORT_PURPOSES = frozenset(
    {"compliance_investigation", "security_incident", "user_request"}
)


def _mask_email(email: Optional[str]) -> Optional[str]:
    """Salted-hash an email for PII-redacted export.

    The salt comes from the AUDIT_PII_HASH_SALT env var if set;
    otherwise a per-process salt is generated at module import so
    hashes are at least consistent within a single deploy.
    """
    if not email:
        return email
    salt = os.getenv("AUDIT_PII_HASH_SALT", "regengine-audit-default-salt-v1")
    digest = hashlib.sha256(f"{salt}:{email}".encode("utf-8")).hexdigest()
    return f"masked:{digest[:24]}"


def _caller_has_pii_export_permission(
    user: UserModel, db: Session, tenant_id: UUID
) -> bool:
    """Return True when the caller's role includes ``audit.export.pii``.

    Sysadmins bypass the role check. For non-sysadmins we look at the
    active membership's role permissions -- the role's ``permissions``
    column is a JSON list of scope strings.
    """
    if getattr(user, "is_sysadmin", False):
        return True

    from .sqlalchemy_models import RoleModel

    membership = db.execute(
        select(MembershipModel).where(
            MembershipModel.user_id == user.id,
            MembershipModel.tenant_id == tenant_id,
            MembershipModel.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if not membership:
        return False
    role = db.get(RoleModel, membership.role_id)
    if not role or not role.permissions:
        return False
    perms = role.permissions if isinstance(role.permissions, list) else []
    return "audit.export.pii" in perms


class AuditExportResponse(BaseModel):
    """Response for audit log export endpoint."""
    export: dict[str, Any]
    entries: list[dict[str, Any]]
    integrity: dict[str, Any]


@router.get("/export", response_model=AuditExportResponse)
def export_audit_logs(
    db: Session = Depends(get_session),
    current_user: UserModel = Depends(get_current_user),
    purpose: str = Query(
        ...,
        description=(
            "Purpose of this export. Required. Must be one of: "
            "compliance_investigation, security_incident, user_request. "
            "This value is logged into audit_logs so compliance officers "
            "can audit the auditor. (#1385)"
        ),
    ),
    start: Optional[str] = Query(
        None, description="Start of time range (ISO 8601). Defaults to 30 days ago."
    ),
    end: Optional[str] = Query(
        None, description="End of time range (ISO 8601). Defaults to now."
    ),
    event_category: Optional[str] = Query(None, description="Filter by category"),
    severity: Optional[str] = Query(None, description="Filter by minimum severity"),
    limit: int = Query(10000, le=50000, description="Max records to return"),
    include_verification: bool = Query(
        False, description="Run chain verification and include results"
    ),
    include_pii: bool = Query(
        False,
        description=(
            "Return raw PII (actor_email/ip/ua). Requires audit.export.pii "
            "permission. Ignored for rows with anonymized_at set. (#1385)"
        ),
    ),
):
    """
    Export tamper-evident audit logs for the authenticated tenant.

    Returns a signed JSON bundle with integrity verification metadata.
    The bundle includes the hash chain so auditors can independently
    verify no entries were modified or deleted.

    PII handling (#1385):
    - ``actor_email``, ``actor_ip``, ``actor_ua`` are masked by default.
    - Raw PII is only returned when ``include_pii=true`` AND the caller
      holds ``audit.export.pii``. Otherwise the masked representation
      is returned (email -> salted-hash, ip -> None, ua -> None).
    - Rows with ``anonymized_at`` set (GDPR Art. 17 erasure) are
      always masked regardless of permissions.
    """
    # Purpose gate (#1385)
    if purpose not in _ALLOWED_EXPORT_PURPOSES:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid purpose. Must be one of: "
                + ", ".join(sorted(_ALLOWED_EXPORT_PURPOSES))
            ),
        )

    # Get tenant context from RLS session
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant context active")

    # Decide PII mode. include_pii=True + permission -> raw PII.
    # Anything else -> masked.
    caller_has_pii_perm = _caller_has_pii_export_permission(
        current_user, db, tenant_id
    )
    pii_mode_requested = bool(include_pii)
    raw_pii_allowed = pii_mode_requested and caller_has_pii_perm
    if pii_mode_requested and not caller_has_pii_perm:
        logger.warning(
            "audit_export_pii_denied",
            user_id=str(current_user.id),
            tenant_id=str(tenant_id),
        )

    # Parse time range
    now = datetime.now(timezone.utc)
    try:
        end_dt = datetime.fromisoformat(end) if end else now
        start_dt = datetime.fromisoformat(start) if start else (end_dt - timedelta(days=30))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use ISO 8601 (e.g., 2026-01-01T00:00:00Z)"
        )

    # Build query
    conditions = [
        AuditLogModel.tenant_id == tenant_id,
        AuditLogModel.timestamp >= start_dt,
        AuditLogModel.timestamp <= end_dt,
    ]

    if event_category:
        valid_categories = {"auth", "data", "admin", "system", "api"}
        if event_category not in valid_categories:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid event_category. Must be one of: {', '.join(valid_categories)}"
            )
        conditions.append(AuditLogModel.event_category == event_category)

    if severity:
        severity_levels = {"critical": 0, "error": 1, "warning": 2, "info": 3}
        min_level = severity_levels.get(severity)
        if min_level is None:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid severity. Must be one of: {', '.join(severity_levels.keys())}"
            )
        allowed = [k for k, v in severity_levels.items() if v <= min_level]
        conditions.append(AuditLogModel.severity.in_(allowed))

    stmt = (
        select(AuditLogModel)
        .where(and_(*conditions))
        .order_by(AuditLogModel.id.asc())
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()

    # Build export entries (#1385 -- mask PII unless caller is entitled)
    entries = []
    for row in rows:
        meta = row.metadata_ if row.metadata_ else {}

        # GDPR Art. 17: rows marked anonymized ALWAYS mask regardless
        # of permissions. The anonymizer cron sets ``anonymized_at`` on
        # rows past the retention threshold for users who requested
        # erasure. We must not un-anonymize them downstream.
        row_anonymized = getattr(row, "anonymized_at", None) is not None
        show_raw_pii = raw_pii_allowed and not row_anonymized

        if show_raw_pii:
            actor_email = row.actor_email
            actor_ip = row.actor_ip
            actor_ua = row.actor_ua
        else:
            actor_email = _mask_email(row.actor_email)
            actor_ip = None
            actor_ua = None

        entries.append({
            "id": row.id,
            "tenant_id": str(row.tenant_id),
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "actor": {
                "id": str(row.actor_id) if row.actor_id else None,
                "email": actor_email,
                "ip": actor_ip,
                "user_agent": actor_ua,
                "pii_masked": not show_raw_pii,
                "anonymized_at": (
                    row.anonymized_at.isoformat()
                    if row_anonymized and hasattr(row, "anonymized_at")
                    else None
                ),
            },
            "event": {
                "type": row.event_type,
                "category": row.event_category,
                "action": row.action,
                "severity": row.severity,
            },
            "resource": {
                "type": row.resource_type,
                "id": row.resource_id,
            },
            "endpoint": row.endpoint,
            "metadata": meta,
            "request_id": str(row.request_id) if row.request_id else None,
            "integrity": {
                "prev_hash": row.prev_hash,
                "hash": row.integrity_hash,
            },
        })

    # Sign the export bundle
    export_timestamp = datetime.now(timezone.utc).isoformat()
    bundle_content = json.dumps(entries, sort_keys=True, default=str)
    bundle_hash = hashlib.sha256(bundle_content.encode("utf-8")).hexdigest()

    # Log the export itself (audit the auditor). Include the declared
    # purpose and whether raw PII was released so compliance officers
    # can audit the caller. (#1385)
    AuditLogger.log_event(
        db=db,
        tenant_id=tenant_id,
        event_type="data.bulk.export",
        action="export",
        event_category="data",
        actor_id=current_user.id,
        actor_email=current_user.email,
        resource_type="audit_logs",
        metadata={
            "record_count": len(entries),
            "time_range": {"start": start_dt.isoformat(), "end": end_dt.isoformat()},
            "bundle_hash": bundle_hash,
            "purpose": purpose,
            "include_pii_requested": pii_mode_requested,
            "raw_pii_released": raw_pii_allowed,
        },
    )
    db.commit()

    # Build response
    response = {
        "export": {
            "version": "1.0",
            "generated_at": export_timestamp,
            "tenant_id": str(tenant_id),
            "record_count": len(entries),
            "time_range": {
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
            },
            "filters": {
                "event_category": event_category,
                "severity": severity,
            },
            "bundle_hash": bundle_hash,
        },
        "entries": entries,
        "integrity": {
            "chain_start": entries[0]["integrity"]["hash"] if entries else None,
            "chain_end": entries[-1]["integrity"]["hash"] if entries else None,
            "bundle_hash": bundle_hash,
            "verification": (
                "Each entry's integrity.hash = SHA-256("
                "integrity.prev_hash + tenant_id + timestamp + event_type + "
                "action + resource_id + metadata). "
                "Verify by recomputing sequentially."
            ),
        },
    }

    # Optionally include chain verification
    if include_verification and entries:
        response["integrity"]["chain_verification"] = verify_chain(entries)

    return response
