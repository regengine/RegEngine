
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from typing import List
from uuid import UUID
import secrets
from datetime import datetime, timedelta, timezone
import structlog
from pydantic import BaseModel, field_validator

from app.database import get_session
from app.sqlalchemy_models import InviteModel, RoleModel, UserModel, MembershipModel
from app.dependencies import get_current_user, PermissionChecker
from app.audit import AuditLogger
from app.auth_utils import get_password_hash
from app.models import TenantContext
from app.password_policy import validate_password, PasswordPolicyError
from app.supplier_graph_sync import supplier_graph_sync

router = APIRouter()
logger = structlog.get_logger("invite_routes")

# DTOs
class InviteCreate(BaseModel):
    email: str
    role_id: UUID

    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        import re
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

    # Create Invite
    token = secrets.token_urlsafe(32)
    # in real prod, store hash of token. For simplicity here: storing raw token or hash? 
    # Plan said "token_hash". So let's hash it.
    # But wait, User Plan said "store hash, not raw token".
    # Implementation: I'll use a simple SHA256 of the token.
    import hashlib
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

    # In a real app, send email here.
    # For now, return the link.
    # Assuming frontend URL from env or header, but hardcoding for dev.
    invite_link = f"/accept-invite?token={token}"

    return InviteResponse(
        id=new_invite.id,
        email=new_invite.email,
        role_id=new_invite.role_id,
        status="pending",
        created_at=new_invite.created_at,
        expires_at=new_invite.expires_at,
        invite_link=invite_link
    )

@router.get("/admin/invites", dependencies=[Depends(PermissionChecker("users.read"))])
async def list_invites(
    db: Session = Depends(get_session)
):
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")
    
    stmt = select(InviteModel).where(
        InviteModel.tenant_id == tenant_id,
        InviteModel.accepted_at.is_(None),
        InviteModel.revoked_at.is_(None),
        InviteModel.expires_at > datetime.now(timezone.utc)
    ).order_by(InviteModel.created_at.desc())
    
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
    return results

@router.post("/admin/invites/{invite_id}/revoke", dependencies=[Depends(PermissionChecker("users.invite"))])
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

@router.post("/auth/accept-invite")
async def accept_invite(
    request: AcceptInviteRequest,
    db: Session = Depends(get_session)
):
    # Verify Token
    import hashlib
    token_hash = hashlib.sha256(request.token.encode()).hexdigest()
    
    invite = db.execute(
        select(InviteModel).where(InviteModel.token_hash == token_hash)
    ).scalar_one_or_none()
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invalid token")
        
    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invite expired")
        
    if invite.revoked_at or invite.accepted_at:
        raise HTTPException(status_code=400, detail="Invite invalid")

    # Check if user exists (Global)
    user = db.execute(select(UserModel).where(UserModel.email == invite.email)).scalar_one_or_none()
    
    if not user:
        # Validate password against policy
        try:
            validate_password(request.password, user_context={'email': invite.email})
        except PasswordPolicyError as e:
            raise HTTPException(status_code=400, detail=e.message)

        # Create User
        user = UserModel(
            email=invite.email,
            password_hash=get_password_hash(request.password),
            status="active",
            is_sysadmin=False
        )
        db.add(user)
        db.flush() # get ID
        
        # We assume creating a user via invite is safe. 
        # But we need to ensure we don't overwrite if check above failed race condition.
        # Unique constraint on email should catch it.
    
    # Check membership
    existing_membership = db.execute(
        select(MembershipModel).where(
            MembershipModel.user_id == user.id,
            MembershipModel.tenant_id == invite.tenant_id
        )
    ).scalar_one_or_none()
    
    if existing_membership:
         raise HTTPException(status_code=409, detail="Already a member")
         
    # Create Membership
    membership = MembershipModel(
        user_id=user.id,
        tenant_id=invite.tenant_id,
        role_id=invite.role_id,
        created_by=None # Self-accepted via system
    )
    db.add(membership)
    
    # Update Invite
    accepted_at = datetime.now(timezone.utc)
    invite.accepted_at = accepted_at
    
    # Audit Log (System context? Or User context?)
    # Since user is just created, we can use their ID? Or leave actor null (System).
    # Plan says "accepted_by (user_id)". 
    
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
