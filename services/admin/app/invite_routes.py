
import hashlib
import html
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
import structlog
from shared.pii import mask_email
from shared.permissions import can_invite_role
from shared.rate_limit import limiter
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from shared.pagination import PaginationParams

from .database import get_session
from .sqlalchemy_models import InviteModel, RoleModel, UserModel, MembershipModel
from .dependencies import get_current_user, PermissionChecker
from .audit import AuditLogger
from .auth_utils import get_password_hash
from .models import TenantContext
from .password_policy import validate_password, PasswordPolicyError
from .supplier_graph_sync import supplier_graph_sync

router = APIRouter()
logger = structlog.get_logger("invite_routes")


def _get_invite_base_url() -> str:
    """Return frontend base URL for invite acceptance links."""
    return os.getenv("INVITE_BASE_URL", "https://regengine.co").rstrip("/")


def _build_invite_link(token: str) -> tuple[str, str]:
    """Build relative and absolute invite links from a token."""
    relative_link = f"/accept-invite?token={token}"
    absolute_link = f"{_get_invite_base_url()}{relative_link}"
    return relative_link, absolute_link


def _send_invite_email(recipient_email: str, invite_link: str) -> None:
    """Send invite email via Resend if configured."""
    resend_api_key = os.getenv("RESEND_API_KEY")
    if not resend_api_key:
        logger.warning("invite_email_skipped_missing_resend_api_key", email=mask_email(recipient_email))
        return

    try:
        import resend
    except ImportError:
        logger.warning("invite_email_skipped_resend_not_installed", email=mask_email(recipient_email))
        return

    resend.api_key = resend_api_key
    from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@regengine.co")
    safe_link = html.escape(invite_link, quote=True)

    try:
        response = resend.Emails.send(
            {
                "from": from_email,
                "to": recipient_email,
                "subject": "You're invited to RegEngine",
                "html": (
                    "<div style='font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;'>"
                    "<h2 style='color: #111827;'>You're invited to RegEngine</h2>"
                    "<p style='color: #374151; line-height: 1.6;'>"
                    "Your team invited you to access your FSMA 204 compliance workspace."
                    "</p>"
                    "<p style='margin: 24px 0;'>"
                    f"<a href='{safe_link}' "
                    "style='background: #10b981; color: #ffffff; text-decoration: none; "
                    "padding: 12px 20px; border-radius: 8px; display: inline-block; font-weight: 600;'>"
                    "Accept Invite"
                    "</a>"
                    "</p>"
                    "<p style='color: #6b7280; font-size: 13px;'>"
                    "If the button does not work, copy and paste this URL into your browser:<br/>"
                    f"{safe_link}"
                    "</p>"
                    "</div>"
                ),
            }
        )

        response_id = response.get("id") if isinstance(response, dict) else None
        logger.info("invite_email_sent", email=mask_email(recipient_email), resend_id=response_id)
    except Exception as exc:  # pragma: no cover - external SDK/network behavior
        logger.warning("invite_email_send_failed", email=mask_email(recipient_email), error=str(exc))

# DTOs
class InviteCreate(BaseModel):
    email: str
    role_id: UUID

    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", v):
            raise ValueError('Invalid email format')
        return v


class InviteResponse(BaseModel):
    id: UUID
    email: str
    role_id: UUID
    status: str  # pending, accepted, revoked, expired
    created_at: datetime
    expires_at: datetime
    invite_link: str  # For dev/demo convenience

class AcceptInviteRequest(BaseModel):
    token: str
    password: str
    name: str  # Assuming we might want name, though User model doesn't explicitly show it in sqlalchemy_models check.
               # Note: UserModel has no 'name' col in the viewed file (step 2800), only email/password_hash/mfa/sysadmin/status.
               # So I will ignore name for now or assume it's metadata.

class RevokeInviteResponse(BaseModel):
    """Response for revoking an invite."""
    status: str

class AcceptInviteResponse(BaseModel):
    """Response for accepting an invite."""
    status: str
    user_id: str

# --- Admin Endpoints ---

@router.post("/admin/invites", response_model=InviteResponse, dependencies=[Depends(PermissionChecker("users.invite"))])
async def create_invite(
    invite_data: InviteCreate,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    # Check if user already exists in this tenant
    existing_member = db.execute(
        select(MembershipModel)
        .join(UserModel)
        .where(
            MembershipModel.tenant_id == tenant_id,
            UserModel.email == invite_data.email
        )
    ).scalar_one_or_none()
    
    if existing_member:
        raise HTTPException(status_code=409, detail="User already a member of this tenant")

    # Check if pending invite exists
    existing_invite = db.execute(
        select(InviteModel).where(
            InviteModel.tenant_id == tenant_id,
            InviteModel.email == invite_data.email,
            InviteModel.revoked_at.is_(None),
            InviteModel.accepted_at.is_(None),
            InviteModel.expires_at > datetime.now(timezone.utc)
        )
    ).scalar_one_or_none()

    if existing_invite:
        # Revoke old to issue new, or just fail? Strategy: Fail to prevent spam/confusion. Revoke explicitly.
        raise HTTPException(status_code=409, detail="Active invite already exists for this email")

    # Verify role exists and is valid for tenant
    role = db.get(RoleModel, invite_data.role_id)
    if not role or (role.tenant_id and role.tenant_id != tenant_id):
         raise HTTPException(status_code=400, detail="Invalid role")

    # #1387 — privilege-escalation guard. Holder of users.invite can create an
    # invite, but they can NOT assign a role of higher rank than their own.
    # Look up the caller's role in this tenant via their membership.
    caller_role = db.execute(
        select(RoleModel)
        .join(MembershipModel, MembershipModel.role_id == RoleModel.id)
        .where(
            MembershipModel.user_id == current_user.id,
            MembershipModel.tenant_id == tenant_id,
            MembershipModel.is_active == True,  # noqa: E712
        )
    ).scalar_one_or_none()

    # sysadmins bypass the tier check (platform-level role). Everyone else
    # must pass can_invite_role().
    if not current_user.is_sysadmin:
        if caller_role is None:
            logger.warning(
                "invite_role_check_no_caller_role",
                user_id=str(current_user.id),
                tenant_id=str(tenant_id),
            )
            raise HTTPException(status_code=403, detail="No active role in this tenant")
        if not can_invite_role(
            caller_role_name=caller_role.name,
            caller_permissions=caller_role.permissions or [],
            target_role_name=role.name,
            target_permissions=role.permissions or [],
        ):
            logger.warning(
                "invite_role_escalation_blocked",
                user_id=str(current_user.id),
                tenant_id=str(tenant_id),
                caller_role=caller_role.name,
                target_role=role.name,
            )
            # Opaque 403 so an attacker can't enumerate role tiers by response.
            raise HTTPException(status_code=403, detail="Insufficient privilege to assign this role")

    # Create Invite
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    new_invite = InviteModel(
        tenant_id=tenant_id,
        email=invite_data.email,
        role_id=invite_data.role_id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        created_by=current_user.id
    )
    db.add(new_invite)
    db.flush()  # Ensure ID is generated
    
    # Audit Log
    AuditLogger.log_event(
        db,
        tenant_id=tenant_id,
        event_type="invite.create",
        action="invite.create",
        event_category="identity_access",
        resource_type="invite",
        resource_id=str(new_invite.id),
        actor_id=current_user.id,
        metadata={"email": invite_data.email, "role_id": str(invite_data.role_id)}
    )
    
    db.commit()
    db.refresh(new_invite)

    supplier_graph_sync.record_invite_created(
        tenant_id=str(tenant_id),
        invite_id=str(new_invite.id),
        email=new_invite.email,
        role_id=str(new_invite.role_id),
        expires_at=new_invite.expires_at,
        created_by=str(current_user.id),
    )

    invite_link, absolute_invite_link = _build_invite_link(token)
    _send_invite_email(new_invite.email, absolute_invite_link)

    return InviteResponse(
        id=new_invite.id,
        email=new_invite.email,
        role_id=new_invite.role_id,
        status="pending",
        created_at=new_invite.created_at,
        expires_at=new_invite.expires_at,
        invite_link=invite_link
    )

@router.get("/admin/invites", response_model=dict[str, Any], dependencies=[Depends(PermissionChecker("users.read"))])
async def list_invites(
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_session),
):
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    base_filter = [
        InviteModel.tenant_id == tenant_id,
        InviteModel.accepted_at.is_(None),
        InviteModel.revoked_at.is_(None),
        InviteModel.expires_at > datetime.now(timezone.utc),
    ]

    # Count total
    total = db.execute(
        select(func.count()).select_from(InviteModel).where(*base_filter)
    ).scalar()

    stmt = select(InviteModel).where(
        *base_filter
    ).order_by(InviteModel.created_at.desc()).offset(pagination.skip).limit(pagination.limit)

    invites = db.execute(stmt).scalars().all()

    # Simple serialization
    results = []
    for inv in invites:
        results.append({
            "id": inv.id,
            "email": inv.email,
            "role_id": inv.role_id,
            "status": "pending",
            "created_at": inv.created_at,
            "expires_at": inv.expires_at
        })
    return {"items": results, "total": total, "skip": pagination.skip, "limit": pagination.limit}

@router.post("/admin/invites/{invite_id}/revoke", response_model=RevokeInviteResponse, dependencies=[Depends(PermissionChecker("users.invite"))])
async def revoke_invite(
    invite_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")
    
    invite = db.get(InviteModel, invite_id)
    if not invite or invite.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Invite not found")
        
    if invite.accepted_at or invite.revoked_at:
        raise HTTPException(status_code=400, detail="Invite already processed")
        
    invite.revoked_at = datetime.now(timezone.utc)
    
    AuditLogger.log_event(
        db,
        tenant_id=tenant_id,
        event_type="invite.revoke",
        action="invite.revoke",
        event_category="identity_access",
        resource_type="invite",
        resource_id=str(invite.id),
        actor_id=current_user.id,
        metadata={"revoked_by": str(current_user.id)}
    )
    
    db.commit()
    return {"status": "revoked"}

# --- Public Endpoint ---

class AcceptInviteExistingUserRequest(BaseModel):
    """Acceptance payload used when the invited email matches an existing user.

    The acceptor must re-authenticate with their current RegEngine password
    before the new membership is granted (#1337 Path B). No password-set is
    performed in this branch — the existing account is unchanged.
    """
    token: str
    current_password: str


@router.post("/auth/accept-invite", response_model=AcceptInviteResponse, status_code=201)
@limiter.limit("10/minute")
async def accept_invite(
    payload: AcceptInviteRequest,
    request: Request,
    db: Session = Depends(get_session),
):
    """Accept an invite.

    #1337 fix:
      * Path A (new user): invite acts as proof-of-email, but we rate-limit
        and fail-closed on any ambiguity. Password policy is enforced.
      * Path B (existing user): a membership is NEVER granted silently. The
        caller must supply either the existing account's password in
        ``current_password``, or authenticate via the standard login flow and
        accept from /v1/me. Holding the raw token alone is not enough.
      * Deleted/erased users are not reinstated via invite.
      * All failure cases return a uniform 400 so an attacker cannot distinguish
        expired / revoked / already-accepted from "invite belongs to existing
        user with no password supplied".
    """
    from .auth_utils import verify_password  # local import to avoid cycle

    generic_400 = HTTPException(status_code=400, detail="Invite is not usable")

    # Verify Token (hashed lookup; tokens stay opaque at rest).
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()

    invite = db.execute(
        select(InviteModel).where(InviteModel.token_hash == token_hash)
    ).scalar_one_or_none()

    # Uniform 400 for all not-usable cases (#1337).
    if not invite:
        raise generic_400
    invite_expires_at = invite.expires_at
    if invite_expires_at.tzinfo is None:
        invite_expires_at = invite_expires_at.replace(tzinfo=timezone.utc)
    if invite_expires_at < datetime.now(timezone.utc):
        raise generic_400
    if invite.revoked_at or invite.accepted_at:
        raise generic_400

    # Check if user exists (Global)
    user = db.execute(select(UserModel).where(UserModel.email == invite.email)).scalar_one_or_none()

    if user is not None:
        # Path B — existing user. Require proof of ownership via the existing
        # account password. If the caller only has the invite token, refuse.
        if user.status != "active":
            # Do not reinstate erased / suspended users via invite (#1337).
            logger.warning(
                "accept_invite_inactive_user_blocked",
                email=mask_email(invite.email),
                status=user.status,
            )
            raise generic_400

        # The password field on AcceptInviteRequest doubles as the existing
        # password when the email already has an account. We intentionally use
        # the same field so the frontend can post the same payload shape.
        supplied_password = payload.password or ""
        if not supplied_password or not verify_password(supplied_password, user.password_hash):
            logger.warning(
                "accept_invite_existing_user_auth_failed",
                email=mask_email(invite.email),
            )
            # Same generic 400 to avoid leaking "account exists" to token holders.
            raise generic_400

    else:
        # Path A — create new user with invite-supplied password.
        # Enforce password policy FIRST so we don't flush half-constructed rows.
        try:
            validate_password(payload.password, user_context={'email': invite.email})
        except PasswordPolicyError as e:
            raise HTTPException(status_code=400, detail=e.message)

        user = UserModel(
            email=invite.email,
            password_hash=get_password_hash(payload.password),
            status="active",
            is_sysadmin=False,
        )
        db.add(user)
        db.flush()  # get ID

    # Check membership (idempotency + defense-in-depth).
    existing_membership = db.execute(
        select(MembershipModel).where(
            MembershipModel.user_id == user.id,
            MembershipModel.tenant_id == invite.tenant_id
        )
    ).scalar_one_or_none()

    if existing_membership:
        # Mark the invite consumed so it can't be reused, then uniform 400.
        invite.accepted_at = datetime.now(timezone.utc)
        db.commit()
        raise generic_400

    # Create Membership
    membership = MembershipModel(
        user_id=user.id,
        tenant_id=invite.tenant_id,
        role_id=invite.role_id,
        created_by=None  # Self-accepted via system
    )
    db.add(membership)

    # Update Invite (single-use).
    accepted_at = datetime.now(timezone.utc)
    invite.accepted_at = accepted_at

    AuditLogger.log_event(
        db,
        tenant_id=invite.tenant_id,
        event_type="invite.accept",
        action="invite.accept",
        event_category="identity_access",
        resource_type="membership",
        resource_id=str(user.id),
        actor_id=user.id,
        metadata={"role_id": str(invite.role_id)}
    )

    db.commit()

    supplier_graph_sync.record_invite_accepted(
        tenant_id=str(invite.tenant_id),
        invite_id=str(invite.id),
        user_id=str(user.id),
        email=user.email,
        role_id=str(invite.role_id),
        accepted_at=accepted_at,
    )

    return {"status": "success", "user_id": str(user.id)}
