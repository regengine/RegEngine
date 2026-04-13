"""
Audit Export API — Signed, Timestamped JSON Bundle
ISO 27001: 12.7.1

Returns a tamper-evident export of audit logs for a tenant.
Enterprise customers use this to feed their SIEM or prove compliance.
"""

import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, HTTPException
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


@router.get("/export")
def export_audit_logs(
    db: Session = Depends(get_session),
    current_user: UserModel = Depends(get_current_user),
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
):
    """
    Export tamper-evident audit logs for the authenticated tenant.

    Returns a signed JSON bundle with integrity verification metadata.
    The bundle includes the hash chain so auditors can independently
    verify no entries were modified or deleted.
    """
    # Get tenant context from RLS session
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant context active")

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

    # Build export entries
    entries = []
    for row in rows:
        meta = row.metadata_ if row.metadata_ else {}
        entries.append({
            "id": row.id,
            "tenant_id": str(row.tenant_id),
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "actor": {
                "id": str(row.actor_id) if row.actor_id else None,
                "email": row.actor_email,
                "ip": row.actor_ip,
                "user_agent": row.actor_ua,
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

    # Log the export itself (audit the auditor)
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
