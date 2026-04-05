"""Password change route for authenticated users."""

from fastapi import APIRouter, Depends, HTTPException, Request
import structlog
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.sqlalchemy_models import UserModel, MembershipModel
from app.auth_utils import get_password_hash, verify_password
from app.audit import AuditLogger
from app.password_policy import validate_password, PasswordPolicyError
from app.dependencies import get_current_user, get_session_store
from app.session_store import RedisSessionStore
from shared.rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger("password_change")


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


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
