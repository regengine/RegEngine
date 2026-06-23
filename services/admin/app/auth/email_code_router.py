"""Passwordless email-code login route.

Existing active users can request a short-lived confirmation code by email,
then exchange that code for RegEngine access/refresh tokens.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from shared.env import is_production
from shared.pii import mask_email
from shared.rate_limit import limiter
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import AuditLogger
from ..auth_utils import (
    REFRESH_TOKEN_EXPIRE_DAYS,
    SECRET_KEY,
    create_access_token,
    create_refresh_token,
    hash_token,
)
from ..database import get_session
from ..dependencies import get_session_store
from ..session_store import RedisSessionStore, SessionData
from ..sqlalchemy_models import MembershipModel, RoleModel, TenantModel, UserModel
from .schemas import EmailCodeConfirmRequest, EmailCodeRequest, EmailCodeRequestResponse, TokenResponse
from .session_helpers import _persist_session

router = APIRouter()
logger = structlog.get_logger("auth.email_code")

EMAIL_CODE_TTL_SECONDS = int(os.getenv("AUTH_EMAIL_CODE_TTL_SECONDS", "600"))
EMAIL_CODE_ATTEMPTS = int(os.getenv("AUTH_EMAIL_CODE_ATTEMPTS", "3"))
EMAIL_CODE_REQUEST_DETAIL = "If an account exists, we sent a confirmation code."
EMAIL_CODE_INVALID_DETAIL = "Invalid or expired confirmation code"


def _email_code_key(email: str) -> str:
    digest = hashlib.sha256(email.encode("utf-8")).hexdigest()
    return f"auth:email_code:{digest}"


def _hash_email_code(email: str, code: str) -> str:
    return hmac.new(
        SECRET_KEY.encode("utf-8"),
        f"{email}:{code}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _make_email_code() -> str:
    return f"{secrets.randbelow(900000) + 100000}"


async def _store_email_code(
    session_store: RedisSessionStore,
    email: str,
    code: str,
    *,
    metadata: dict | None = None,
) -> None:
    client = await session_store._get_client()
    payload = {
        "code_hash": _hash_email_code(email, code),
        "attempts": EMAIL_CODE_ATTEMPTS,
        **(metadata or {}),
    }
    await client.setex(_email_code_key(email), EMAIL_CODE_TTL_SECONDS, json.dumps(payload))


async def _delete_email_code(session_store: RedisSessionStore, email: str) -> None:
    client = await session_store._get_client()
    await client.delete(_email_code_key(email))


async def _check_email_code(
    session_store: RedisSessionStore,
    email: str,
    code: str,
) -> bool:
    return await _consume_email_code(session_store, email, code) is not None


async def _consume_email_code(
    session_store: RedisSessionStore,
    email: str,
    code: str,
) -> dict | None:
    client = await session_store._get_client()
    key = _email_code_key(email)
    raw = await client.get(key)
    if not raw:
        return None

    try:
        payload = json.loads(raw)
        attempts = int(payload.get("attempts", 0))
        code_hash = str(payload["code_hash"])
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        await client.delete(key)
        return None

    if attempts <= 0:
        await client.delete(key)
        return None

    candidate_hash = _hash_email_code(email, code)
    if not hmac.compare_digest(code_hash, candidate_hash):
        attempts -= 1
        if attempts <= 0:
            await client.delete(key)
        else:
            payload["attempts"] = attempts
            await client.setex(key, EMAIL_CODE_TTL_SECONDS, json.dumps(payload))
        return None

    await client.delete(key)
    return payload


def _send_email_login_code(recipient_email: str, code: str) -> bool:
    resend_api_key = os.getenv("RESEND_API_KEY")
    if not resend_api_key:
        if is_production():
            logger.error("email_login_code_skipped_missing_resend_api_key", email=mask_email(recipient_email))
            return False
        logger.warning("email_login_code_dev", email=mask_email(recipient_email), code=code)
        return True

    try:
        import resend
    except ImportError:
        logger.error("email_login_code_skipped_resend_not_installed", email=mask_email(recipient_email))
        return False

    resend.api_key = resend_api_key
    from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@regengine.co")
    safe_code = html.escape(code, quote=True)

    try:
        response = resend.Emails.send(
            {
                "from": from_email,
                "to": recipient_email,
                "subject": f"Your RegEngine login code: {code}",
                "html": (
                    "<div style='font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;'>"
                    "<h2 style='color: #111827;'>Your RegEngine login code</h2>"
                    "<p style='color: #374151; line-height: 1.6;'>"
                    "Enter this confirmation code to finish signing in:"
                    "</p>"
                    "<p style='font-size: 32px; letter-spacing: 6px; font-weight: 700; color: #111827;'>"
                    f"{safe_code}"
                    "</p>"
                    "<p style='color: #6b7280; font-size: 13px;'>"
                    "This code expires in 10 minutes. If you did not request it, you can ignore this email."
                    "</p>"
                    "</div>"
                ),
            }
        )
        response_id = getattr(response, "id", None) or (response.get("id") if isinstance(response, dict) else None)
        logger.info("email_login_code_sent", email=mask_email(recipient_email), resend_id=response_id)
        return True
    except Exception as exc:  # pragma: no cover - external SDK/network behavior
        logger.warning("email_login_code_send_failed", email=mask_email(recipient_email), error=str(exc))
        return False


def _load_user_by_email(db: Session, normalized_email: str) -> UserModel | None:
    return db.execute(select(UserModel).where(UserModel.email == normalized_email)).scalar_one_or_none()


def _load_membership_context(
    db: Session, user: UserModel
) -> tuple[
    list[dict],
    uuid.UUID | None,
    str | None,
    uuid.UUID | None,
    str | None,
    list[str],
]:
    stmt_mem = (
        select(MembershipModel, TenantModel, RoleModel)
        .join(TenantModel, MembershipModel.tenant_id == TenantModel.id)
        .join(RoleModel, MembershipModel.role_id == RoleModel.id)
        .where(MembershipModel.user_id == user.id)
    )
    results = db.execute(stmt_mem).all()

    available_tenants = []
    active_tenant_id = None
    active_tenant_status = None
    active_role_id = None
    active_role_name = None
    active_permissions: list[str] = []

    for mem, tenant, role in results:
        available_tenants.append({"id": tenant.id, "name": tenant.name, "slug": tenant.slug})
        if not active_tenant_id:
            active_tenant_id = tenant.id
            active_tenant_status = tenant.status
            active_role_id = role.id
            active_role_name = role.name
            active_permissions = list(role.permissions or []) if isinstance(role.permissions, list) else []

    return (
        available_tenants,
        active_tenant_id,
        active_tenant_status,
        active_role_id,
        active_role_name,
        active_permissions,
    )


async def _issue_token_response_for_user(
    *,
    user: UserModel,
    request: Request,
    db: Session,
    session_store: RedisSessionStore,
) -> TokenResponse:
    (
        available_tenants,
        active_tenant_id,
        active_tenant_status,
        active_role_id,
        active_role_name,
        active_permissions,
    ) = _load_membership_context(db, user)

    raw_refresh_token = create_refresh_token()
    token_hash = hash_token(raw_refresh_token)
    session_data = SessionData(
        id=uuid.uuid4(),
        user_id=user.id,
        refresh_token_hash=token_hash,
        family_id=uuid.uuid4(),
        token_version=int(getattr(user, "token_version", 0) or 0),
        created_at=datetime.now(timezone.utc),
        last_used_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=request.headers.get("User-Agent", "Unknown"),
        ip_address=request.client.host if request.client else "0.0.0.0",
    )

    await _persist_session(
        session_store,
        session_data,
        context="email_code_login",
        user_id=user.id,
    )

    access_token = create_access_token(
        {
            "sub": str(user.id),
            "email": user.email,
            "tenant_id": str(active_tenant_id) if active_tenant_id else None,
            "tid": str(active_tenant_id) if active_tenant_id else None,
            "tenant_status": active_tenant_status,
            "is_sysadmin": bool(user.is_sysadmin),
            "tv": int(getattr(user, "token_version", 0) or 0),
            "sid": str(session_data.id),
            "session_id": str(session_data.id),
            "auth_method": "email_code",
        }
    )

    response = TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        tenant_id=active_tenant_id,
        user={
            "id": str(user.id),
            "email": user.email,
            "is_sysadmin": user.is_sysadmin,
            "status": user.status,
            "role_id": str(active_role_id) if active_role_id else None,
            "role_name": active_role_name,
            "permissions": active_permissions,
        },
        available_tenants=available_tenants,
    )

    try:
        if active_tenant_id:
            audit_entry_id = AuditLogger.log_event(
                db,
                tenant_id=active_tenant_id,
                event_type="user.login",
                action="session.create",
                event_category="authentication",
                actor_id=user.id,
                resource_type="session",
                resource_id=str(session_data.id),
            )
            if audit_entry_id is None:
                db.rollback()
        user.last_login_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        logger.warning("email_code_login_side_effects_failed", user_id=str(user.id), error=str(exc))
        db.rollback()

    return response


@router.post("/email-code/request", response_model=EmailCodeRequestResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3/minute")
async def request_email_login_code(
    payload: EmailCodeRequest,
    request: Request,
    db: Session = Depends(get_session),
    session_store: RedisSessionStore = Depends(get_session_store),
):
    normalized_email = str(payload.email).strip().lower()
    user = _load_user_by_email(db, normalized_email)

    if user and user.status == "active":
        code = _make_email_code()
        await _store_email_code(
            session_store,
            normalized_email,
            code,
            metadata={"flow": "login"},
        )
        if not _send_email_login_code(normalized_email, code):
            await _delete_email_code(session_store, normalized_email)

    return EmailCodeRequestResponse(status="code_sent", detail=EMAIL_CODE_REQUEST_DETAIL)


@router.post("/email-code/confirm", response_model=TokenResponse)
@limiter.limit("10/minute")
async def confirm_email_login_code(
    payload: EmailCodeConfirmRequest,
    request: Request,
    db: Session = Depends(get_session),
    session_store: RedisSessionStore = Depends(get_session_store),
):
    normalized_email = str(payload.email).strip().lower()
    code_payload = await _consume_email_code(session_store, normalized_email, payload.code.strip())
    if code_payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=EMAIL_CODE_INVALID_DETAIL,
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = _load_user_by_email(db, normalized_email)
    if user and user.status == "active":
        logger.info("email_code_login_success", user_id=str(user.id))
        return await _issue_token_response_for_user(
            user=user,
            request=request,
            db=db,
            session_store=session_store,
        )

    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=EMAIL_CODE_INVALID_DETAIL,
            headers={"WWW-Authenticate": "Bearer"},
        )
