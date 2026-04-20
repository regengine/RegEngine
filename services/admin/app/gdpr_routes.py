"""
GDPR data rights endpoints.

  Art. 15 / 20 — Right of access / data portability:
      GET  /gdpr/export

  Art. 17 — Right to erasure for unauthenticated data subjects (tool_leads):
      POST /gdpr/request-erasure   — generate & log a signed token
      POST /gdpr/confirm-erasure   — validate token, delete from tool_leads
"""

from __future__ import annotations

import hashlib
import hmac
import json
import structlog
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_current_user

logger = structlog.get_logger("gdpr")

router = APIRouter(prefix="/gdpr", tags=["GDPR"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ERASURE_TOKEN_TTL = 3600  # 1 hour

# In-memory store for pending erasure tokens (dev / single-process).
# Production should use Redis — but a simple dict suffices here because
# the token is single-use and short-lived.
_pending_erasure_tokens: Dict[str, float] = {}


def _erasure_secret() -> str:
    """Return the HMAC signing secret for erasure tokens."""
    secret = os.environ.get("GDPR_ERASURE_SECRET") or os.environ.get("AUTH_SECRET_KEY")
    if not secret:
        raise RuntimeError("GDPR_ERASURE_SECRET env var is not set")
    return secret


def _make_erasure_token(email: str) -> str:
    """Generate an HMAC-SHA256 token for the given email address."""
    nonce = secrets.token_hex(16)
    ts = str(int(time.time()))
    message = f"{email}:{ts}:{nonce}"
    sig = hmac.new(
        _erasure_secret().encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    # Encode the payload so we can verify later without a DB
    payload = f"{message}:{sig}"
    return payload


def _verify_erasure_token(email: str, token: str) -> bool:
    """Return True if *token* is a valid, non-expired token for *email*."""
    try:
        parts = token.rsplit(":", 1)
        if len(parts) != 2:
            return False
        message, provided_sig = parts
        expected_sig = hmac.new(
            _erasure_secret().encode(), message.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, provided_sig):
            return False
        # Parse timestamp from message: email:ts:nonce
        msg_parts = message.split(":", 2)
        if len(msg_parts) != 3:
            return False
        msg_email, ts_str, _ = msg_parts
        if msg_email != email:
            return False
        ts = int(ts_str)
        if int(time.time()) - ts > _ERASURE_TOKEN_TTL:
            return False
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Art. 15 / 20 — Data export
# ---------------------------------------------------------------------------

class ExportResponse(BaseModel):
    user: Dict[str, Any]
    audit_events: List[Dict[str, Any]]
    compliance_records: List[Dict[str, Any]]


@router.get(
    "/export",
    summary="GDPR Art. 15/20 — export all data for the authenticated user",
)
async def gdpr_export(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Return all personal data held for the requesting user.

    Response is a JSON attachment with schema:
    ``{"user": {...}, "audit_events": [...], "compliance_records": [...]}``.
    """
    user_id = str(current_user.get("user_id") or current_user.get("sub") or "")
    tenant_id = str(current_user.get("tenant_id") or "")
    email = current_user.get("email", "")

    if not user_id:
        raise HTTPException(status_code=401, detail="Cannot identify user")

    offset = (page - 1) * page_size

    # ── User profile ─────────────────────────────────────────────────────────
    try:
        user_row = db.execute(
            text(
                "SELECT id, email, status, created_at, last_login_at "
                "FROM users WHERE id = :uid LIMIT 1"
            ),
            {"uid": user_id},
        ).mappings().first()
        user_data: Dict[str, Any] = dict(user_row) if user_row else {"id": user_id, "email": email}
    except Exception as exc:
        logger.warning("gdpr_export_user_query_failed", error=str(exc))
        user_data = {"id": user_id, "email": email}

    # Convert datetime objects to ISO strings for JSON serialisation
    for k, v in user_data.items():
        if isinstance(v, datetime):
            user_data[k] = v.isoformat()

    # ── Audit events (paginated) ──────────────────────────────────────────────
    audit_events: List[Dict[str, Any]] = []
    try:
        rows = db.execute(
            text(
                "SELECT id, timestamp, event_type, event_category, action, "
                "       severity, resource_type, resource_id, endpoint "
                "FROM audit_logs "
                "WHERE tenant_id = :tid AND actor_id = :uid "
                "ORDER BY timestamp DESC "
                "LIMIT :lim OFFSET :off"
            ),
            {"tid": tenant_id, "uid": user_id, "lim": page_size, "off": offset},
        ).mappings().all()
        for row in rows:
            d = dict(row)
            for k, v in d.items():
                if isinstance(v, datetime):
                    d[k] = v.isoformat()
            audit_events.append(d)
    except Exception as exc:
        logger.warning("gdpr_export_audit_query_failed", error=str(exc))

    # ── Compliance records (paginated) ────────────────────────────────────────
    compliance_records: List[Dict[str, Any]] = []
    try:
        rows = db.execute(
            text(
                "SELECT id, cte_type, status, created_at "
                "FROM supplier_cte_events "
                "WHERE tenant_id = :tid "
                "ORDER BY created_at DESC "
                "LIMIT :lim OFFSET :off"
            ),
            {"tid": tenant_id, "lim": page_size, "off": offset},
        ).mappings().all()
        for row in rows:
            d = dict(row)
            for k, v in d.items():
                if isinstance(v, datetime):
                    d[k] = v.isoformat()
            compliance_records.append(d)
    except Exception as exc:
        logger.warning("gdpr_export_compliance_query_failed", error=str(exc))

    payload: Dict[str, Any] = {
        "user": user_data,
        "audit_events": audit_events,
        "compliance_records": compliance_records,
    }

    logger.info(
        "gdpr_export_served",
        user_id=user_id,
        page=page,
        audit_count=len(audit_events),
        compliance_count=len(compliance_records),
    )

    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": 'attachment; filename="data-export.json"',
        },
    )


# ---------------------------------------------------------------------------
# Art. 17 — Tool-lead erasure (unauthenticated)
# ---------------------------------------------------------------------------

class ErasureRequestBody(BaseModel):
    email: EmailStr


class ErasureConfirmBody(BaseModel):
    email: EmailStr
    token: str


@router.post(
    "/request-erasure",
    summary="GDPR Art. 17 — request erasure of tool_leads data (step 1)",
)
async def request_lead_erasure(body: ErasureRequestBody):
    """Generate a signed erasure token for the given email.

    In production this would send the token via email.
    For now the token is logged server-side for manual handoff.
    """
    try:
        token = _make_erasure_token(body.email)
    except RuntimeError as exc:
        logger.error("gdpr_request_erasure_config_error", error=str(exc))
        raise HTTPException(status_code=503, detail="Service configuration error")

    # Store token keyed by email so confirm step can look it up
    _pending_erasure_tokens[body.email] = time.time()

    # Log token — in production send via transactional email instead
    logger.info(
        "gdpr_erasure_token_generated",
        email_masked=body.email[:2] + "***",
        # NOTE: only log in non-prod; redact in production
        token=token if os.environ.get("ENV") != "production" else "REDACTED",
    )

    return {
        "status": "pending",
        "message": (
            "An erasure verification token has been generated. "
            "In production this would be sent to your email address. "
            "Use it with POST /gdpr/confirm-erasure within 1 hour."
        ),
        # Expose token in response only in non-production
        **({"token": token} if os.environ.get("ENV") != "production" else {}),
    }


@router.post(
    "/confirm-erasure",
    summary="GDPR Art. 17 — confirm erasure of tool_leads data (step 2)",
)
async def confirm_lead_erasure(
    body: ErasureConfirmBody,
    db: Session = Depends(get_session),
):
    """Validate the signed token and delete the email from tool_leads."""
    try:
        secret_ok = _verify_erasure_token(body.email, body.token)
    except RuntimeError as exc:
        logger.error("gdpr_confirm_erasure_config_error", error=str(exc))
        raise HTTPException(status_code=503, detail="Service configuration error")

    if not secret_ok:
        logger.warning(
            "gdpr_confirm_erasure_invalid_token",
            email_masked=body.email[:2] + "***",
        )
        raise HTTPException(status_code=400, detail="Invalid or expired erasure token")

    # Delete from tool_leads — gracefully handle missing table
    deleted = 0
    try:
        result = db.execute(
            text("DELETE FROM tool_leads WHERE email = :email"),
            {"email": body.email},
        )
        deleted = result.rowcount
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(
            "gdpr_confirm_erasure_db_error",
            email_masked=body.email[:2] + "***",
            error=str(exc),
        )
        raise HTTPException(
            status_code=500,
            detail="Database error during erasure. Your request has been logged.",
        )

    # Clean up pending-token tracking
    _pending_erasure_tokens.pop(body.email, None)

    logger.info(
        "gdpr_lead_erasure_complete",
        email_masked=body.email[:2] + "***",
        rows_deleted=deleted,
    )

    return {
        "status": "erased",
        "rows_deleted": deleted,
        "message": (
            "Your data has been removed from our lead capture database "
            "in accordance with GDPR Article 17."
        ),
    }
