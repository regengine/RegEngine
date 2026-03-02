
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import structlog
from pydantic import BaseModel

from app.database import get_session
from app.sqlalchemy_models import UserModel, MembershipModel, RoleModel
from app.dependencies import get_current_user, PermissionChecker
from app.audit import AuditLogger
from app.models import TenantContext

router = APIRouter()
logger = structlog.get_logger("user_routes")

# DTOs
class UserResponse(BaseModel):
    id: UUID
    email: str
    status: str
    is_sysadmin: bool
    role_id: UUID
    role_name: str
    created_at: datetime

class RoleUpdate(BaseModel):
    role_id: UUID

class RoleResponse(BaseModel):
    id: UUID
    name: str
    is_system: bool


# --- Endpoints ---

@router.get("/admin/users", response_model=List[UserResponse], dependencies=[Depends(PermissionChecker("users.read"))])
async def list_users(
    db: Session = Depends(get_session)
):
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")
    
    # helper for explicit join
    stmt = (
        select(UserModel, MembershipModel, RoleModel)
        .join(MembershipModel, UserModel.id == MembershipModel.user_id)
        .join(RoleModel, MembershipModel.role_id == RoleModel.id)
        .where(MembershipModel.tenant_id == tenant_id)
    )
    
    rows = db.execute(stmt).all()
    
    results = []
    for user, membership, role in rows:
        results.append(UserResponse(
            id=user.id,
            email=user.email,
            status="inactive" if not membership.is_active else user.status,
            is_sysadmin=user.is_sysadmin,
            role_id=role.id,
            role_name=role.name,
            created_at=user.created_at
        ))
        
    return results

@router.patch("/admin/users/{user_id}/role", dependencies=[Depends(PermissionChecker("users.manage_roles"))])
async def update_user_role(
    user_id: UUID,
    update: RoleUpdate,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")
    
    # Invariant: Cannot remove last Owner
    # Check if target user has Owner role currently
    # Note: We need to know which role is "Owner". For now assuming by Name or specific ID property?
    # User plan said: "ensure at least one Owner per tenant".
    # Implementation: If target user is Owner, check if there are other Owners.
    
    membership = db.execute(
        select(MembershipModel).where(
            MembershipModel.user_id == user_id,
            MembershipModel.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    
    if not membership:
        raise HTTPException(status_code=404, detail="User not found in this tenant")
        
    target_role = db.get(RoleModel, update.role_id)
    if not target_role:
        raise HTTPException(status_code=400, detail="Role not found")
        
    # Check "Last Owner" invariant
    # 1. Get current role of user
    current_role = db.get(RoleModel, membership.role_id)
    if current_role.name == "Owner" and target_role.name != "Owner":
        # Check count of OTHER owners
        owner_subquery = (
            select(MembershipModel.user_id)
            .join(RoleModel)
            .where(
                MembershipModel.tenant_id == tenant_id,
                RoleModel.name == "Owner",
                MembershipModel.user_id != user_id
            )
        )
        other_owners = db.execute(owner_subquery).all()
        if not other_owners:
             raise HTTPException(status_code=400, detail="Cannot remove the last Owner")

    # Update
    old_role_id = membership.role_id
    membership.role_id = target_role.id
    
    AuditLogger.log_event(
        db,
        tenant_id=tenant_id,
        event_type="membership.role_change",
        event_category="identity_access",
        actor_id=current_user.id,
        action="membership.role_change",
        resource_type="membership",
        resource_id=str(user_id),
        metadata={
            "old_role": str(old_role_id), 
            "new_role": str(target_role.id)
        }
    )
    
    db.commit()
    return {"status": "updated"}

@router.post("/admin/users/{user_id}/deactivate", dependencies=[Depends(PermissionChecker("users.disable"))])
async def deactivate_user(
    user_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")
    
    membership = db.execute(
        select(MembershipModel).where(
            MembershipModel.user_id == user_id,
            MembershipModel.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    
    if not membership:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Do we deactivate the USER (global) or the Membership?
    # Context implies removing from tenant. 
    # Plan says: "Remove user from tenant (deactivate membership)"
    # But `membership` model doesn't have `status` col. `users` table has `status`.
    # If we change `users.status`, it locks them globally.
    # If we want tenant-specific deactivation, we should probably delete the membership OR add status to membership.
    # Plan Section 1B: "Remove user from tenant (deactivate membership)".
    # Plan Section 2: Membership invariants "valid membership".
    # Implementation: Delete membership? Or is there a status pending?
    # Re-reading Plan Data Model Additions: No status on membership.
    # Re-reading Plan Section 3: `POST .../deactivate` `perm: users.disable`
    
    # Decide: I will DELETE the membership for now, effectively removing them.
    # Wait, check "Last Owner" invariant again.
    
    current_role = db.get(RoleModel, membership.role_id)
    if current_role.name == "Owner":
         owner_subquery = (
            select(MembershipModel.user_id)
            .join(RoleModel)
            .where(
                MembershipModel.tenant_id == tenant_id,
                RoleModel.name == "Owner",
                MembershipModel.user_id != user_id
            )
        )
         other_owners = db.execute(owner_subquery).all()
         if not other_owners:
             raise HTTPException(status_code=400, detail="Cannot remove the last Owner")
             
    # Perform Removal (Deactivate)
    # Changed to Soft Delete (Deactivate)
    membership.is_active = False
    
    AuditLogger.log_event(
        db,
        tenant_id=tenant_id,
        event_type="membership.deactivate",
        event_category="identity_access",
        actor_id=current_user.id,
        action="membership.deactivate",
        resource_type="membership",
        resource_id=str(user_id),
        metadata={"is_active": False}
    )
    
    db.commit()
    return {"status": "deactivated"}

@router.post("/admin/users/{user_id}/reactivate", dependencies=[Depends(PermissionChecker("users.manage_roles"))])
async def reactivate_user(
    user_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")
    
    membership = db.execute(
        select(MembershipModel).where(
            MembershipModel.user_id == user_id,
            MembershipModel.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    
    if not membership:
        raise HTTPException(status_code=404, detail="User not found")
        
    membership.is_active = True
    
    AuditLogger.log_event(
        db,
        tenant_id=tenant_id,
        event_type="membership.reactivate",
        event_category="identity_access",
        actor_id=current_user.id,
        action="membership.reactivate",
        resource_type="membership",
        resource_id=str(user_id),
        metadata={"is_active": True}
    )
    
    db.commit()
    return {"status": "reactivated"}

@router.get("/admin/roles", response_model=List[RoleResponse], dependencies=[Depends(PermissionChecker("users.read"))])
async def list_roles(
    db: Session = Depends(get_session)
):
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")
    
    # Return System roles (tenant_id is NULL) AND Custom roles (tenant_id matches)
    # Actually, simplistic RBAC: just show all roles visible to tenant?
    stmt = select(RoleModel).where(
        (RoleModel.tenant_id == tenant_id) | (RoleModel.tenant_id.is_(None))
    )
    roles = db.execute(stmt).scalars().all()
    
    results = []
    for r in roles:
        results.append(RoleResponse(id=r.id, name=r.name, is_system=r.tenant_id is None))
    return results
