import hashlib
import html
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from shared.pagination import PaginationParams
from shared.permissions import can_invite_role
from shared.pii import mask_email
from shared.rate_limit import limiter
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .audit import AuditLogger
from .auth.identity_helpers import EmailOwnershipConflictError, ensure_passwordless_identity
from .database import get_session
from .dependencies import PermissionChecker, get_current_user
from .e2e_safety import assert_e2e_mode_allowed, e2e_mode_enabled
from .models import TenantContext
from .sqlalchemy_models import InviteModel, MembershipModel, RoleModel, UserModel
from .supplier_graph_sync import supplier_graph_sync

router = APIRouter()
logger = structlog.get_logger("invite_routes")
assert_e2e_mode_allowed()


def _get_invite_base_url() -> str:
    """Return frontend base URL for invite acceptance links."""
    return os.getenv("INVITE_BASE_URL", "https://regengine.co").rstrip("/")


def _build_invite_link(token: str) -> tuple[str, str]:
    """Build relative and absolute invite links from a token."""
    # Put the one-time secret in the fragment so it is not sent to servers,
    # proxies, or gateway logs. The client scrubs it from browser history.
    relative_link = f"/accept-invite#token={token}"
    absolute_link = f"{_get_invite_base_url()}{relative_link}"
    return relative_link, absolute_link


def _record_e2e_invite_email(recipient_email: str, invite_link: str) -> bool:
    """Record an invite email in the Playwright-only outbox fixture."""
    outbox_path = os.getenv("REGENGINE_E2E_EMAIL_OUTBOX")
    environment = os.getenv("REGENGINE_ENV", "").strip().lower()
    # #2512: reuse the single shared cloud-marker tuple from shared.env.
    from shared.env import CLOUD_ENV_VARS  # noqa: PLC0415

    cloud_deployment = any(os.getenv(marker) for marker in CLOUD_ENV_VARS)
    if (
        not outbox_path
        or not e2e_mode_enabled()
        or environment not in {"development", "dev", "test", "local"}
        or cloud_deployment
    ):
        return False

    record = {
        "type": "invite_email",
        "to": recipient_email,
        "invite_link": invite_link,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    path = Path(outbox_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as outbox:
        outbox.write(json.dumps(record, sort_keys=True) + "\n")
    return True


def _send_invite_email(recipient_email: str, invite_link: str) -> None:
    """Send invite email via Resend if configured."""
    recorded_e2e_outbox = _record_e2e_invite_email(recipient_email, invite_link)
    resend_api_key = os.getenv("RESEND_API_KEY")
    if not resend_api_key:
        if recorded_e2e_outbox:
            logger.info("invite_email_recorded_e2e_outbox", email=mask_email(recipient_email))
        else:
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

        response_id = getattr(response, "id", None) or (response.get("id") if isinstance(response, dict) else None)
        logger.info("invite_email_sent", email=mask_email(recipient_email), resend_id=response_id)
    except Exception as exc:  # pragma: no cover - external SDK/network behavior
        logger.warning("invite_email_send_failed", email=mask_email(recipient_email), error=str(exc))


# DTOs
class InviteCreate(BaseModel):
    email: str
    role_id: UUID

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", v):
            raise ValueError("Invalid email format")
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
    name: str  # Assuming we might want name, though User model doesn't explicitly show it in sqlalchemy_models check.
    # Note: UserModel has no 'name' col in the viewed file, only email/status/sysadmin metadata.
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
    invite_data: InviteCreate, current_user: UserModel = Depends(get_current_user), db: Session = Depends(get_session)
):
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    # Check if user already exists in this tenant
    existing_member = db.execute(
        select(MembershipModel)
        .join(UserModel)
        .where(MembershipModel.tenant_id == tenant_id, UserModel.email == invite_data.email)
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
            InviteModel.expires_at > datetime.now(timezone.utc),
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
        created_by=current_user.id,
    )
    db.add(new_invite)
    db.flush()  # Ensure ID is generated

    # Audit Log
    audit_entry_id = AuditLogger.log_event(
        db,
        tenant_id=tenant_id,
        event_type="invite.create",
        action="invite.create",
        event_category="identity_access",
        resource_type="invite",
        resource_id=str(new_invite.id),
        actor_id=current_user.id,
        metadata={"email": invite_data.email, "role_id": str(invite_data.role_id)},
    )
    if audit_entry_id is None:
        logger.error(
            "invite_create_audit_chain_write_failed_aborting",
            tenant_id=str(tenant_id),
            invite_id=str(new_invite.id),
        )
        # ``log_event`` may have left the session in an aborted transaction;
        # roll back before raising so no partial work is committed.
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail={
                "error": "audit_write_failed",
                "message": (
                    "Could not write the required audit-chain entry. "
                    "Invite creation was aborted — no change was committed."
                ),
            },
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
        invite_link=invite_link,
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
    total = db.execute(select(func.count()).select_from(InviteModel).where(*base_filter)).scalar()

    stmt = (
        select(InviteModel)
        .where(*base_filter)
        .order_by(InviteModel.created_at.desc())
        .offset(pagination.skip)
        .limit(pagination.limit)
    )

    invites = db.execute(stmt).scalars().all()

    # Simple serialization
    results = []
    for inv in invites:
        results.append(
            {
                "id": inv.id,
                "email": inv.email,
                "role_id": inv.role_id,
                "status": "pending",
                "created_at": inv.created_at,
                "expires_at": inv.expires_at,
            }
        )
    return {"items": results, "total": total, "skip": pagination.skip, "limit": pagination.limit}


@router.post(
    "/admin/invites/{invite_id}/revoke",
    response_model=RevokeInviteResponse,
    dependencies=[Depends(PermissionChecker("users.invite"))],
)
async def revoke_invite(
    invite_id: UUID, current_user: UserModel = Depends(get_current_user), db: Session = Depends(get_session)
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

    audit_entry_id = AuditLogger.log_event(
        db,
        tenant_id=tenant_id,
        event_type="invite.revoke",
        action="invite.revoke",
        event_category="identity_access",
        resource_type="invite",
        resource_id=str(invite.id),
        actor_id=current_user.id,
        metadata={"revoked_by": str(current_user.id)},
    )
    if audit_entry_id is None:
        logger.error(
            "invite_revoke_audit_chain_write_failed_aborting",
            tenant_id=str(tenant_id),
            invite_id=str(invite.id),
        )
        # ``log_event`` may have left the session in an aborted transaction;
        # roll back before raising so no partial work is committed.
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail={
                "error": "audit_write_failed",
                "message": (
                    "Could not write the required audit-chain entry. "
                    "Invite revocation was aborted — no change was committed."
                ),
            },
        )


    db.commit()
    return {"status": "revoked"}


def _uses_postgres(db: Session) -> bool:
    """True only for a real PostgreSQL bind.

    Opt-IN rather than opt-out: RLS and the v113 function exist on PostgreSQL
    and nowhere else, so the SQLite fixture (and any test double) keeps the
    direct read it has always had.
    """
    bind = getattr(db, "bind", None)
    return bool(bind) and getattr(getattr(bind, "dialect", None), "name", None) == "postgresql"


def _resolve_invite_tenant(db: Session, token_hash: str) -> UUID | None:
    """Resolve an invite's tenant from its token hash, before tenant context.

    Returns ``None`` when the token matches no still-usable invite, and on any
    non-PostgreSQL bind, which has neither RLS nor the v113 function — there
    the caller reads ``invites`` directly, as before.
    """
    if not _uses_postgres(db):
        return None

    row = db.execute(
        text("SELECT get_invite_tenant_by_token_hash(:token_hash)"),
        {"token_hash": token_hash},
    ).scalar()
    if row is None:
        return None
    return row if isinstance(row, UUID) else UUID(str(row))


# --- Public Endpoint ---


@router.post("/auth/accept-invite", response_model=AcceptInviteResponse, status_code=201)
@limiter.limit("10/minute")
async def accept_invite(
    payload: AcceptInviteRequest,
    request: Request,
    db: Session = Depends(get_session),
):
    """Accept an invite.

    The invite token is delivered to the invited mailbox and acts as
    proof-of-email for account creation or membership attachment.
      * Deleted/erased users are not reinstated via invite.
      * All failure cases return a uniform 400 so an attacker cannot distinguish
        expired / revoked / already-accepted from other unusable invite states.
    """
    generic_400 = HTTPException(status_code=400, detail="Invite is not usable")

    # Verify Token (hashed lookup; tokens stay opaque at rest).
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()

    # #2899: this route is unauthenticated, so no tenant context exists yet —
    # and public.invites is FORCE RLS under tenant_isolation_invites, whose
    # get_tenant_context() RAISES when app.tenant_id is unset (v097). Reading
    # the table directly therefore 500'd for every invitee. v113 adds a
    # SELECT-only policy arm keyed on the token hash; the function below arms
    # it for one statement and returns nothing but the invite's tenant_id.
    # Binding that tenant is what makes every statement after this point
    # authorised by the ordinary tenant policies.
    invite_tenant_id = _resolve_invite_tenant(db, token_hash)
    if invite_tenant_id is not None:
        TenantContext.set_tenant_context(db, invite_tenant_id)
    elif _uses_postgres(db):
        # Fail closed: unknown, revoked, accepted or expired token. Proceeding
        # would read invites with no tenant context and 500 instead of
        # returning the uniform 400 (#1337).
        raise generic_400

    invite = db.execute(select(InviteModel).where(InviteModel.token_hash == token_hash)).scalar_one_or_none()

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

    # Check if user exists (Global). The comparison is case-insensitive so
    # an invite addressed to a case variant of an existing user's email
    # attaches to that user instead of creating a duplicate account that
    # would then claim their verified email row.
    user = db.execute(
        select(UserModel).where(func.lower(UserModel.email) == invite.email.strip().lower())
    ).scalar_one_or_none()

    if user is not None:
        if user.status != "active":
            # Do not reinstate erased / suspended users via invite (#1337).
            logger.warning(
                "accept_invite_inactive_user_blocked",
                email=mask_email(invite.email),
                status=user.status,
            )
            raise generic_400

    else:
        # Path A — create a passwordless user from an invite token.
        user = UserModel(
            email=invite.email,
            status="active",
            is_sysadmin=False,
        )
        db.add(user)
        db.flush()  # get ID

    # Check membership (idempotency + defense-in-depth).
    existing_membership = db.execute(
        select(MembershipModel).where(MembershipModel.user_id == user.id, MembershipModel.tenant_id == invite.tenant_id)
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
        created_by=None,  # Self-accepted via system
    )
    db.add(membership)

    # Provision the passwordless identity rows (verified user_emails +
    # organization_memberships) or sign-in code emails for this user are
    # silently suppressed. The invite token is proof of mailbox control.
    invite_role = db.get(RoleModel, invite.role_id)
    try:
        ensure_passwordless_identity(
            db,
            user=user,
            email=invite.email,
            organization_id=invite.tenant_id,
            role_name=invite_role.name if invite_role is not None else None,
        )
    except EmailOwnershipConflictError:
        # The invited address (up to case) is verified for a different user.
        # Refuse without revealing which account holds it (uniform 400).
        logger.warning(
            "accept_invite_email_ownership_conflict",
            email=mask_email(invite.email),
        )
        db.rollback()
        raise generic_400

    # Update Invite (single-use).
    accepted_at = datetime.now(timezone.utc)
    invite.accepted_at = accepted_at

    audit_entry_id = AuditLogger.log_event(
        db,
        tenant_id=invite.tenant_id,
        event_type="invite.accept",
        action="invite.accept",
        event_category="identity_access",
        resource_type="membership",
        resource_id=str(user.id),
        actor_id=user.id,
        metadata={"role_id": str(invite.role_id)},
    )
    if audit_entry_id is None:
        logger.error(
            "invite_accept_audit_chain_write_failed_aborting",
            tenant_id=str(invite.tenant_id),
            invite_id=str(invite.id),
        )
        # ``log_event`` may have left the session in an aborted transaction;
        # roll back before raising so no partial work is committed.
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail={
                "error": "audit_write_failed",
                "message": (
                    "Could not write the required audit-chain entry. "
                    "Invite acceptance was aborted — no change was committed."
                ),
            },
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
