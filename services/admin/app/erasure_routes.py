"""
GDPR Right-to-Erasure API.

Provides a user-facing endpoint for data deletion requests per
GDPR Article 17. Soft-deletes user account data immediately and
schedules hard-delete after the configured retention period.

FSMA 204 compliance note: Audit logs that contain actor_email are
anonymized (email masked) rather than deleted, because 21 CFR 1.1310
requires maintaining the traceability audit trail. The anonymization
preserves the audit trail's integrity while removing PII.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shared.auth import get_current_user
from shared.database import get_db

logger = logging.getLogger("erasure")

router = APIRouter(prefix="/v1/account", tags=["Account"])


class ErasureRequest(BaseModel):
    """Request body for GDPR right-to-erasure."""
    reason: Optional[str] = Field(
        default=None,
        description="Optional reason for the deletion request",
    )
    confirm: bool = Field(
        ...,
        description="Must be true to confirm deletion. This action is irreversible.",
    )


class ErasureResponse(BaseModel):
    """Response from erasure request."""
    status: str
    message: str
    soft_deleted: bool = False
    audit_logs_anonymized: bool = False
    hard_delete_scheduled: bool = False
    hard_delete_date: Optional[str] = None


@router.post(
    "/erasure",
    response_model=ErasureResponse,
    summary="Request account data erasure (GDPR Article 17)",
    description=(
        "Soft-deletes your account data and schedules permanent deletion. "
        "Audit logs are anonymized (email masked) to preserve FSMA 204 "
        "traceability requirements while removing PII."
    ),
)
async def request_erasure(
    body: ErasureRequest,
    current_user=Depends(get_current_user),
):
    """Process a GDPR right-to-erasure request for the authenticated user."""
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="You must set confirm=true to proceed with account erasure.",
        )

    user_id = current_user.get("user_id") or current_user.get("sub")
    tenant_id = current_user.get("tenant_id")
    email = current_user.get("email", "unknown")

    if not user_id:
        raise HTTPException(status_code=401, detail="Could not identify user")

    logger.info(
        "erasure_requested",
        user_id=user_id,
        tenant_id=tenant_id,
        reason=body.reason,
    )

    try:
        from shared.data_retention import (
            DataRetentionManager,
            DeletionRequest,
            RetentionPolicy,
        )
        from shared.audit_logging import AuditActor
        from shared.pii import mask_email

        with get_db() as db:
            manager = DataRetentionManager()

            # 1. Soft-delete the user account record
            result = await manager.process_deletion_request(
                db=db,
                resource_type="user_account",
                record_id=user_id,
                policy=RetentionPolicy.USER_ACCOUNT,
                deletion_request=DeletionRequest.USER_REQUEST,
                actor=AuditActor(
                    actor_type="user",
                    actor_id=user_id,
                    actor_email=mask_email(email),
                ),
                reason=body.reason or "GDPR Article 17 right-to-erasure request",
            )

            # 2. Anonymize audit logs (mask email, preserve trail)
            anonymized = await manager.anonymize_audit_logs(
                db=db,
                resource_type="user_account",
                record_id=user_id,
            )

            db.commit()

        return ErasureResponse(
            status="accepted",
            message=(
                "Your account data has been marked for deletion. "
                "Audit logs have been anonymized to comply with both GDPR and FSMA 204. "
                "Permanent deletion will occur after the retention period."
            ),
            soft_deleted=result.get("soft_deleted", False),
            audit_logs_anonymized=anonymized > 0 if isinstance(anonymized, int) else bool(anonymized),
            hard_delete_scheduled=result.get("hard_delete_scheduled", False),
            hard_delete_date=result.get("hard_delete_date"),
        )

    except ImportError as e:
        logger.error("erasure_import_error", error=str(e))
        raise HTTPException(
            status_code=503,
            detail="Data retention module not available. Contact support.",
        )
    except Exception as e:
        logger.error("erasure_failed", user_id=user_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Erasure request failed. Your request has been logged and will be processed manually.",
        )
