"""GDPR Art. 15 / 20 — right-to-access and data portability.

Provides GET /v1/account/export for authenticated users to obtain a
structured, machine-readable copy of their personal data.  Secrets
(password hashes, TOTP seeds, refresh tokens) are never included.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from .dependencies import get_current_user
from .database import get_session
from .audit import AuditLogger
from .sqlalchemy_models import (
    AuditLogModel,
    MembershipModel,
    MFARecoveryCodeModel,
    RoleModel,
    SessionModel,
    SupplierCTEEventModel,
    SupplierFacilityModel,
    SupplierFunnelEventModel,
    SupplierTraceabilityLotModel,
    UserModel,
)
from shared.rate_limit import limiter

logger = structlog.get_logger("data_export")

router = APIRouter(prefix="/v1/account", tags=["Account"])

# Maximum audit log rows returned inline (GDPR Art. 12(3): respond within one month)
_AUDIT_LOG_LIMIT = 100


def _serialize(val: Any) -> Any:
    """Convert non-JSON-serialisable objects (UUID, datetime) to strings."""
    if val is None:
        return None
    if hasattr(val, "isoformat"):  # datetime
        return val.isoformat()
    return str(val)


def _build_user_export(db: Session, user_id: str) -> Dict[str, Any]:
    """Collect all personal data for *user_id* and return a scrubbed dict.

    Secrets (password_hash, mfa_secret, mfa_secret_ciphertext, refresh_token_hash)
    are explicitly excluded from every query.
    """
    try:
        user_uuid = uuid.UUID(str(user_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid user identifier")

    # -------------------------------------------------------------------------
    # 1. User account — exclude password_hash, mfa_secret*, token_version
    # -------------------------------------------------------------------------
    user: Optional[UserModel] = db.get(UserModel, user_uuid)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    account_data: Dict[str, Any] = {
        "id": _serialize(user.id),
        "email": user.email,
        "status": user.status,
        "is_sysadmin": user.is_sysadmin,
        "created_at": _serialize(user.created_at),
        "updated_at": _serialize(user.updated_at),
        "last_login_at": _serialize(user.last_login_at),
    }

    # -------------------------------------------------------------------------
    # 2. Memberships with role names (two separate queries for easy mocking)
    # -------------------------------------------------------------------------
    membership_rows = (
        db.query(MembershipModel)
        .filter(MembershipModel.user_id == user_uuid)
        .all()
    )
    memberships: List[Dict[str, Any]] = []
    for m in membership_rows:
        role = db.get(RoleModel, m.role_id)
        role_name = role.name if role else str(m.role_id)
        memberships.append(
            {
                "tenant_id": _serialize(m.tenant_id),
                "role": role_name,
                "is_active": m.is_active,
                "created_at": _serialize(m.created_at),
            }
        )

    # -------------------------------------------------------------------------
    # 3. Sessions metadata — exclude refresh_token_hash
    # -------------------------------------------------------------------------
    sessions_rows = (
        db.query(SessionModel)
        .filter(SessionModel.user_id == user_uuid)
        .order_by(SessionModel.created_at.desc())
        .limit(50)
        .all()
    )
    sessions: List[Dict[str, Any]] = []
    for s in sessions_rows:
        sessions.append(
            {
                "id": _serialize(s.id),
                "created_at": _serialize(s.created_at),
                "last_used_at": _serialize(s.last_used_at),
                "expires_at": _serialize(s.expires_at),
                "is_revoked": s.is_revoked,
                "user_agent": s.user_agent,
                "ip_address": s.ip_address,
            }
        )

    # -------------------------------------------------------------------------
    # 4. MFA status — enrolled yes/no + recovery codes count only; no secrets
    # -------------------------------------------------------------------------
    mfa_enrolled = bool(user.mfa_secret or user.mfa_secret_ciphertext)
    recovery_code_count = (
        db.query(MFARecoveryCodeModel)
        .filter(
            MFARecoveryCodeModel.user_id == user_uuid,
            MFARecoveryCodeModel.used_at.is_(None),
        )
        .count()
    )
    mfa_data: Dict[str, Any] = {
        "enrolled": mfa_enrolled,
        "unused_recovery_codes": recovery_code_count,
    }

    # -------------------------------------------------------------------------
    # 5. tool_leads rows — keyed on user email, raw SQL (no ORM model)
    # -------------------------------------------------------------------------
    tool_leads: List[Dict[str, Any]] = []
    try:
        rows = db.execute(
            text(
                "SELECT email, domain, first_tool_used, access_count, created_at, verified_at "
                "FROM tool_leads WHERE LOWER(email) = LOWER(:email)"
            ),
            {"email": user.email},
        ).mappings().all()
        for row in rows:
            tool_leads.append(
                {
                    "email": row["email"],
                    "domain": row["domain"],
                    "first_tool_used": row["first_tool_used"],
                    "access_count": row["access_count"],
                    "created_at": _serialize(row["created_at"]),
                    "verified_at": _serialize(row["verified_at"]),
                }
            )
    except Exception as exc:  # noqa: BLE001
        # Table may not exist in all environments (e.g. SQLite test DB without migration)
        logger.debug("data_export_tool_leads_unavailable", error=str(exc))

    # -------------------------------------------------------------------------
    # 6. Supplier-scoped rows
    # -------------------------------------------------------------------------
    supplier_facilities = [
        {
            "id": _serialize(f.id),
            "tenant_id": _serialize(f.tenant_id),
            "name": f.name,
            "street": f.street,
            "city": f.city,
            "state": f.state,
            "postal_code": f.postal_code,
            "fda_registration_number": f.fda_registration_number,
            "roles": f.roles,
            "created_at": _serialize(f.created_at),
            "updated_at": _serialize(f.updated_at),
        }
        for f in db.query(SupplierFacilityModel)
        .filter(SupplierFacilityModel.supplier_user_id == user_uuid)
        .all()
    ]

    supplier_traceability_lots = [
        {
            "id": _serialize(tl.id),
            "tenant_id": _serialize(tl.tenant_id),
            "facility_id": _serialize(tl.facility_id),
            "tlc_code": tl.tlc_code,
            "product_description": tl.product_description,
            "status": tl.status,
            "created_at": _serialize(tl.created_at),
            "updated_at": _serialize(tl.updated_at),
        }
        for tl in db.query(SupplierTraceabilityLotModel)
        .filter(SupplierTraceabilityLotModel.supplier_user_id == user_uuid)
        .limit(500)
        .all()
    ]

    supplier_cte_events_count = (
        db.query(SupplierCTEEventModel)
        .filter(SupplierCTEEventModel.supplier_user_id == user_uuid)
        .count()
    )

    supplier_funnel_events = [
        {
            "id": _serialize(fe.id),
            "tenant_id": _serialize(fe.tenant_id),
            "event_name": fe.event_name,
            "step": fe.step,
            "status": fe.status,
            "created_at": _serialize(fe.created_at),
        }
        for fe in db.query(SupplierFunnelEventModel)
        .filter(SupplierFunnelEventModel.supplier_user_id == user_uuid)
        .limit(200)
        .all()
    ]

    # -------------------------------------------------------------------------
    # 7. Audit log rows where actor_id = user_id (last 100)
    # -------------------------------------------------------------------------
    audit_entries: List[Dict[str, Any]] = []
    try:
        audit_rows = (
            db.query(AuditLogModel)
            .filter(AuditLogModel.actor_id == user_uuid)
            .order_by(AuditLogModel.timestamp.desc())
            .limit(_AUDIT_LOG_LIMIT)
            .all()
        )
        for row in audit_rows:
            audit_entries.append(
                {
                    "id": row.id,
                    "tenant_id": _serialize(row.tenant_id),
                    "timestamp": _serialize(row.timestamp),
                    "event_type": row.event_type,
                    "action": row.action,
                    "event_category": row.event_category,
                    "severity": row.severity,
                    "resource_type": row.resource_type,
                    "resource_id": row.resource_id,
                    "endpoint": row.endpoint,
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("data_export_audit_logs_unavailable", error=str(exc))

    # -------------------------------------------------------------------------
    # 8. S3 object count note (no presigned URLs)
    # -------------------------------------------------------------------------
    s3_note = (
        "S3 object count is not available inline. "
        "Contact support to request a bulk download of your uploaded files."
    )

    return {
        "schema_version": "1.0",
        "generated_at": _serialize(__import__("datetime").datetime.now(__import__("datetime").timezone.utc)),
        "account": account_data,
        "memberships": memberships,
        "sessions": {
            "data": sessions,
            "note": "Showing up to 50 most recent sessions. Refresh tokens are never included.",
        },
        "mfa": mfa_data,
        "tool_leads": tool_leads,
        "supplier_data": {
            "facilities": supplier_facilities,
            "traceability_lots": {
                "data": supplier_traceability_lots,
                "note": "Showing up to 500 lots. Contact support for the complete set.",
            },
            "cte_events": {
                "count": supplier_cte_events_count,
                "note": "CTE event payloads are available on request.",
            },
            "funnel_events": supplier_funnel_events,
        },
        "audit_log": {
            "data": audit_entries,
            "note": (
                f"Showing up to {_AUDIT_LOG_LIMIT} most recent entries where you are the actor. "
                "Full history available on request."
            ),
        },
        "s3_objects": {"note": s3_note},
    }


@router.get(
    "/export",
    summary="Export personal data (GDPR Article 15 / 20)",
    description=(
        "Returns a structured, machine-readable copy of your personal data per "
        "GDPR Art. 15 (right of access) and Art. 20 (data portability). "
        "Secrets (password hash, TOTP seed, refresh tokens) are never returned. "
        "Rate-limited to 1 request per day."
    ),
)
@limiter.limit("1/day")
async def export_personal_data(
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Return a structured export of the authenticated user's personal data."""
    user_id = current_user.get("user_id") or current_user.get("sub")
    tenant_id = current_user.get("tenant_id")
    email = current_user.get("email", "unknown")

    if not user_id:
        raise HTTPException(status_code=401, detail="Could not identify user")

    logger.info(
        "data_export_requested",
        user_id=str(user_id),
        tenant_id=str(tenant_id) if tenant_id else None,
    )

    export_data = _build_user_export(db, user_id)

    # Emit audit log entry for the export event
    try:
        if tenant_id:
            try:
                tenant_uuid = uuid.UUID(str(tenant_id))
                user_uuid = uuid.UUID(str(user_id))
            except (TypeError, ValueError):
                tenant_uuid = None
                user_uuid = None

            if tenant_uuid and user_uuid:
                AuditLogger.log_event(
                    db,
                    tenant_id=tenant_uuid,
                    event_type="user.data_export",
                    action="DATA_EXPORT",
                    event_category="privacy",
                    severity="info",
                    actor_id=user_uuid,
                    actor_email=email,
                    resource_type="user_account",
                    resource_id=str(user_id),
                    metadata={"gdpr_article": "Art. 15 / 20"},
                )
                db.commit()
    except Exception as exc:  # noqa: BLE001
        # Audit log failure must not block the export response
        logger.warning("data_export_audit_log_failed", user_id=str(user_id), error=str(exc))
        db.rollback()

    return export_data
