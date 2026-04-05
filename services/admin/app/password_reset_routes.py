"""Password reset routes — forgot-password and reset-password endpoints."""

import hashlib
import html
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
import structlog
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database import get_session
from app.sqlalchemy_models import UserModel, PasswordResetTokenModel, MembershipModel
from app.auth_utils import get_password_hash, verify_password
from app.audit import AuditLogger
from app.password_policy import validate_password, PasswordPolicyError
from app.dependencies import get_current_user, get_session_store
from app.session_store import RedisSessionStore
from shared.rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger("password_reset")

PASSWORD_RESET_TOKEN_EXPIRE_HOURS = 1

GENERIC_SUCCESS_MESSAGE = (
    "If an account with that email exists, a password reset link has been sent."
)


def _get_reset_base_url() -> str:
    return os.getenv("INVITE_BASE_URL", "https://regengine.co").rstrip("/")


def _send_password_reset_email(recipient_email: str, reset_link: str) -> None:
    """Send password reset email via Resend if configured."""
    resend_api_key = os.getenv("RESEND_API_KEY")
    if not resend_api_key:
        logger.warning("password_reset_email_skipped_missing_resend_api_key", email=recipient_email)
        return

    try:
        import resend
    except ImportError:
        logger.warning("password_reset_email_skipped_resend_not_installed", email=recipient_email)
        return

    resend.api_key = resend_api_key
    from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@regengine.co")
    safe_link = html.escape(reset_link, quote=True)

    try:
        response = resend.Emails.send(
            {
                "from": from_email,
                "to": recipient_email,
                "subject": "Reset your RegEngine password",
                "html": (
                    "<div style='font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;'>"
                    "<h2 style='color: #111827;'>Reset Your Password</h2>"
                    "<p style='color: #374151; line-height: 1.6;'>"
                    "Someone requested a password reset for your RegEngine account. "
                    "If you did not make this request, you can safely ignore this email."
                    "</p>"
                    "<p style='margin: 24px 0;'>"
                    f"<a href='{safe_link}' "
                    "style='background: #10b981; color: #ffffff; text-decoration: none; "
                    "padding: 12px 20px; border-radius: 8px; display: inline-block; font-weight: 600;'>"
                    "Reset Password"
                    "</a>"
                    "</p>"
                    "<p style='color: #6b7280; font-size: 13px;'>"
                    "If the button does not work, copy and paste this URL into your browser:<br/>"
                    f"{safe_link}"
                    "</p>"
                    "<p style='color: #9ca3af; font-size: 12px; margin-top: 24px;'>"
                    "This link expires in 1 hour."
                    "</p>"
                    "</div>"
                ),
            }
        )

        response_id = response.get("id") if isinstance(response, dict) else None
        logger.info("password_reset_email_sent", email=recipient_email, resend_id=response_id)
    except Exception as exc:  # pragma: no cover - external SDK/network behavior
        logger.warning("password_reset_email_send_failed", email=recipient_email, error=str(exc))


# ── Request / Response DTOs ─────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# ── Routes ───────────────────────────────────────────────────────────

@router.post("/forgot-password")
@limiter.limit("3/minute")
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_session),
):
    """Request a password reset link. Always returns 200 to prevent email enumeration."""
    normalized_email = payload.email.strip().lower()

    user = db.execute(
        select(UserModel).where(UserModel.email == normalized_email)
    ).scalar_one_or_none()

    if not user or user.status != "active":
        # Return the same response to prevent email enumeration
        db.commit()
        return {"message": GENERIC_SUCCESS_MESSAGE}

    # Invalidate any existing unused reset tokens for this user
    db.execute(
        update(PasswordResetTokenModel)
        .where(
            PasswordResetTokenModel.user_id == user.id,
            PasswordResetTokenModel.used_at.is_(None),
        )
        .values(used_at=datetime.now(timezone.utc))
    )

    # Generate new token
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    reset_token = PasswordResetTokenModel(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=PASSWORD_RESET_TOKEN_EXPIRE_HOURS),
    )
    db.add(reset_token)

    # Audit log — use first membership's tenant_id if available
    membership = db.execute(
        select(MembershipModel).where(MembershipModel.user_id == user.id)
    ).scalar_one_or_none()

    if membership:
        AuditLogger.log_event(
            db,
            tenant_id=membership.tenant_id,
            event_type="password_reset.request",
            action="password_reset.request",
            event_category="authentication",
            actor_id=user.id,
            resource_type="password_reset_token",
            resource_id=str(reset_token.id),
        )

    db.commit()

    # Send email (after commit so the token is persisted)
    reset_link = f"{_get_reset_base_url()}/reset-password?token={raw_token}"
    _send_password_reset_email(user.email, reset_link)

    logger.info("password_reset_requested", user_id=str(user.id))

    return {"message": GENERIC_SUCCESS_MESSAGE}


@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_session),
    session_store: RedisSessionStore = Depends(get_session_store),
):
    """Reset password using a valid token."""
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()

    reset_token = db.execute(
        select(PasswordResetTokenModel).where(
            PasswordResetTokenModel.token_hash == token_hash
        )
    ).scalar_one_or_none()

    if not reset_token:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if reset_token.used_at is not None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if reset_token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    # Load user
    user = db.get(UserModel, reset_token.user_id)
    if not user or user.status != "active":
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    # Validate new password against policy
    try:
        validate_password(payload.password, user_context={"email": user.email})
    except PasswordPolicyError as e:
        raise HTTPException(status_code=400, detail=e.message)

    # Update password
    user.password_hash = get_password_hash(payload.password)

    # Mark token as used
    reset_token.used_at = datetime.now(timezone.utc)

    # Revoke all sessions for security
    await session_store.revoke_all_user_sessions(user.id)

    # Audit log
    membership = db.execute(
        select(MembershipModel).where(MembershipModel.user_id == user.id)
    ).scalar_one_or_none()

    if membership:
        AuditLogger.log_event(
            db,
            tenant_id=membership.tenant_id,
            event_type="password_reset.complete",
            action="password_reset.complete",
            event_category="authentication",
            actor_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
        )

    db.commit()

    logger.info("password_reset_completed", user_id=str(user.id))

    return {"message": "Password has been reset successfully."}


@router.post("/change-password")
@limiter.limit("3/minute")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
    session_store: RedisSessionStore = Depends(get_session_store),
):
    """Change password for the currently authenticated user."""
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    try:
        validate_password(payload.new_password, user_context={"email": current_user.email})
    except PasswordPolicyError as e:
        raise HTTPException(status_code=400, detail=e.message)

    current_user.password_hash = get_password_hash(payload.new_password)

    # Revoke all other sessions (keep current session alive by revoking all
    # and letting the caller's token remain valid until expiry)
    await session_store.revoke_all_user_sessions(current_user.id)

    # Audit log
    membership = db.execute(
        select(MembershipModel).where(MembershipModel.user_id == current_user.id)
    ).scalar_one_or_none()

    if membership:
        AuditLogger.log_event(
            db,
            tenant_id=membership.tenant_id,
            event_type="password.change",
            action="password.change",
            event_category="authentication",
            actor_id=current_user.id,
            resource_type="user",
            resource_id=str(current_user.id),
        )

    db.commit()

    logger.info("password_changed", user_id=str(current_user.id))

    return {"message": "Password changed successfully."}
