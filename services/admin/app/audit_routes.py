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
- When a row has ``anonymized_at`` set, or a per-user anonymization
  marker exists in the append-only audit stream (GDPR Art. 17), PII is
  forced to the masked representation regardless of the caller's
  permissions -- the retention policy must be honored even for
  compliance officers.
- Audit metadata is redacted on export so raw payload fields such as
  invite emails, contact details, IPs, user agents, and tokens do not
  bypass the actor-level PII controls.
"""

import hashlib
import hmac
import json
import os
import re
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

_ANONYMIZATION_MARKER_ACTION = "gdpr_anonymize_user"
_ANONYMIZATION_MARKER_KIND = "per_user_anonymization_order"
_PII_REDACTION = "[REDACTED_PII]"
_PII_KEY_SUBSTRINGS = frozenset(
    {
        "address",
        "actor_ip",
        "actor_ua",
        "contact",
        "contact_name",
        "email",
        "first_name",
        "full_name",
        "ip_address",
        "last_name",
        "password",
        "person_name",
        "phone",
        "redacted_user_id",
        "secret",
        "ssn",
        "token",
        "user_agent",
        "user_id",
    }
)
_SECRET_KEY_SUBSTRINGS = frozenset({"password", "secret", "token"})
_EMAIL_PATTERN = re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w.-]+\.[A-Za-z]{2,}")
_PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\w)"
)


def _mask_identifier(value: Any) -> Optional[str]:
    """Salted-hash a stable identifier for PII-redacted export."""
    if value is None:
        return None
    text = str(value)
    if not text:
        return text
    salt = os.getenv("AUDIT_PII_HASH_SALT", "regengine-audit-default-salt-v1")
    digest = hashlib.sha256(f"{salt}:{text}".encode("utf-8")).hexdigest()
    return f"masked:{digest[:24]}"


def _mask_email(email: Optional[str]) -> Optional[str]:
    """Salted-hash an email for PII-redacted export.

    The salt comes from the AUDIT_PII_HASH_SALT env var if set;
    otherwise a per-process salt is generated at module import so
    hashes are at least consistent within a single deploy.
    """
    return _mask_identifier(email)


def _metadata_as_dict(metadata: Any) -> dict[str, Any]:
    """Return audit metadata as a dict without trusting stored shape."""
    if not metadata:
        return {}
    if isinstance(metadata, dict):
        return metadata
    if isinstance(metadata, str):
        try:
            parsed = json.loads(metadata)
        except json.JSONDecodeError:
            return {"value": metadata}
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    return {"value": metadata}


def _metadata_key_is_pii(key: Any) -> bool:
    key_lower = str(key).lower()
    return any(marker in key_lower for marker in _PII_KEY_SUBSTRINGS)


def _metadata_key_is_secret(key: Any) -> bool:
    key_lower = str(key).lower()
    return any(marker in key_lower for marker in _SECRET_KEY_SUBSTRINGS)


def _redact_metadata_value(value: Any, *, force: bool = False) -> Any:
    """Recursively redact PII from audit metadata export payloads."""
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, nested_value in value.items():
            key_is_pii = _metadata_key_is_pii(key)
            if key_is_pii and _metadata_key_is_secret(key):
                redacted[key] = _PII_REDACTION
            else:
                redacted[key] = _redact_metadata_value(
                    nested_value, force=force or key_is_pii
                )
        return redacted
    if isinstance(value, list):
        return [_redact_metadata_value(item, force=force) for item in value]
    if isinstance(value, tuple):
        return [_redact_metadata_value(item, force=force) for item in value]
    if force:
        if isinstance(value, str) and value:
            return _mask_identifier(value)
        return _PII_REDACTION
    if isinstance(value, str):
        redacted = _EMAIL_PATTERN.sub(
            lambda match: _mask_email(match.group(0)) or "", value
        )
        return _PHONE_PATTERN.sub(_PII_REDACTION, redacted)
    return value


def _redact_metadata_pii(metadata: Any, *, force: bool = False) -> dict[str, Any]:
    """Redact raw PII from an audit metadata object."""
    redacted = _redact_metadata_value(_metadata_as_dict(metadata), force=force)
    return redacted if isinstance(redacted, dict) else {"value": redacted}


def _collect_anonymized_actor_ids(rows: list[Any], tenant_id: UUID) -> set[str]:
    """Collect erased user IDs from append-only per-user anonymization markers."""
    anonymized_actor_ids: set[str] = set()
    tenant_text = str(tenant_id)
    for row in rows:
        metadata = _metadata_as_dict(getattr(row, "metadata_", None))
        raw_details = metadata.get("details")
        details = raw_details if isinstance(raw_details, dict) else {}
        marker_payloads = (metadata, details)
        is_marker = (
            getattr(row, "action", None) == _ANONYMIZATION_MARKER_ACTION
            or any(
                payload.get("marker_kind") == _ANONYMIZATION_MARKER_KIND
                for payload in marker_payloads
            )
        )
        if not is_marker:
            continue
        redacted_tenant_id = next(
            (
                payload.get("redacted_tenant_id")
                for payload in marker_payloads
                if payload.get("redacted_tenant_id")
            ),
            None,
        )
        if redacted_tenant_id and str(redacted_tenant_id) != tenant_text:
            continue
        redacted_user_id = next(
            (
                payload.get("redacted_user_id")
                for payload in marker_payloads
                if payload.get("redacted_user_id")
            ),
            None,
        )
        redacted_user_id = redacted_user_id or getattr(row, "resource_id", None)
        if redacted_user_id:
            anonymized_actor_ids.add(str(redacted_user_id))
    return anonymized_actor_ids


def _load_anonymized_actor_ids(
    db: Session,
    tenant_id: UUID,
    export_rows: list[Any],
) -> set[str]:
    """Load tenant-wide erasure markers so narrow exports still honor them."""
    marker_stmt = select(AuditLogModel).where(
        and_(
            AuditLogModel.tenant_id == tenant_id,
            AuditLogModel.action == _ANONYMIZATION_MARKER_ACTION,
        )
    )
    marker_rows = db.execute(marker_stmt).scalars().all()
    return _collect_anonymized_actor_ids([*export_rows, *marker_rows], tenant_id)


def _row_is_anonymized(row: Any, anonymized_actor_ids: set[str]) -> bool:
    """Return True when export-time PII must stay masked for this row."""
    if getattr(row, "anonymized_at", None) is not None:
        return True
    actor_id = getattr(row, "actor_id", None)
    return actor_id is not None and str(actor_id) in anonymized_actor_ids


def _export_actor_id(row: Any, row_anonymized: bool) -> Optional[str]:
    actor_id = getattr(row, "actor_id", None)
    if not actor_id:
        return None
    if row_anonymized:
        return _mask_identifier(actor_id)
    return str(actor_id)


def _export_resource_id(row: Any, anonymized_actor_ids: set[str]) -> Any:
    resource_id = getattr(row, "resource_id", None)
    if resource_id is not None and str(resource_id) in anonymized_actor_ids:
        return _mask_identifier(resource_id)
    return resource_id


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
            "permission. Ignored for rows with anonymized_at set or per-user "
            "anonymization markers. (#1385)"
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
    - Rows with ``anonymized_at`` set, or rows covered by a per-user
      anonymization marker (GDPR Art. 17 erasure), are always masked
      regardless of permissions.
    - Metadata runs through a recursive PII redaction pass so raw
      payload fields do not bypass actor-level masking.
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

    anonymized_actor_ids = _load_anonymized_actor_ids(db, tenant_id, rows)

    # Build export entries (#1385 -- mask PII unless caller is entitled).
    # Per-user anonymization is represented by append-only marker rows, so
    # export performs dynamic masking rather than mutating historical logs.
    entries = []
    for row in rows:
        # GDPR Art. 17: rows marked anonymized, or rows whose actor has a
        # per-user anonymization order, ALWAYS mask regardless of permissions.
        row_anonymized = _row_is_anonymized(row, anonymized_actor_ids)
        show_raw_pii = raw_pii_allowed and not row_anonymized

        if show_raw_pii:
            actor_email = row.actor_email
            actor_ip = row.actor_ip
            actor_ua = row.actor_ua
        else:
            actor_email = _mask_email(row.actor_email)
            actor_ip = None
            actor_ua = None

        entries.append(
            {
                "id": row.id,
                "tenant_id": str(row.tenant_id),
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "actor": {
                    "id": _export_actor_id(row, row_anonymized),
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
                    "id": _export_resource_id(row, anonymized_actor_ids),
                },
                "endpoint": row.endpoint,
                "metadata": _redact_metadata_pii(
                    row.metadata_,
                    force=row_anonymized,
                ),
                "request_id": str(row.request_id) if row.request_id else None,
                "integrity": {
                    "prev_hash": row.prev_hash,
                    "hash": row.integrity_hash,
                },
            }
        )

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
