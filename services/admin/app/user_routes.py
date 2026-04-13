
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import structlog
from pydantic import BaseModel

from .database import get_session
from .sqlalchemy_models import UserModel, MembershipModel, RoleModel
from .dependencies import get_current_user, PermissionChecker
from .audit import AuditLogger
from .models import TenantContext
from shared.pagination import PaginationParams, PaginatedResponse

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

class UserActionResponse(BaseModel):
    """Response for user action operations."""
    status: str


# --- Endpoints ---

@router.get("/admin/users", response_model=PaginatedResponse[UserResponse], dependencies=[Depends(PermissionChecker("users.read"))])
async def list_users(
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_session),
):
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    # Count total
    count_stmt = (
        select(func.count())
        .select_from(UserModel)
        .join(MembershipModel, UserModel.id == MembershipModel.user_id)
        .where(MembershipModel.tenant_id == tenant_id)
    )
    total = db.execute(count_stmt).scalar()

    # helper for explicit join
    stmt = (
        select(UserModel, MembershipModel, RoleModel)
        .join(MembershipModel, UserModel.id == MembershipModel.user_id)
        .join(RoleModel, MembershipModel.role_id == RoleModel.id)
        .where(MembershipModel.tenant_id == tenant_id)
        .offset(pagination.skip)
        .limit(pagination.limit)
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

    return PaginatedResponse(items=results, total=total, skip=pagination.skip, limit=pagination.limit)

@router.patch("/admin/users/{user_id}/role", response_model=UserActionResponse, dependencies=[Depends(PermissionChecker("users.manage_roles"))])
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

@router.post("/admin/users/{user_id}/deactivate", response_model=UserActionResponse, dependencies=[Depends(PermissionChecker("users.disable"))])
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
        
    # Deactivate = delete membership (tenant-scoped, not global user disable).
    # Check "Last Owner" invariant before removing.
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

@router.post("/admin/users/{user_id}/reactivate", response_model=UserActionResponse, dependencies=[Depends(PermissionChecker("users.manage_roles"))])
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

@router.get("/admin/roles", response_model=PaginatedResponse[RoleResponse], dependencies=[Depends(PermissionChecker("users.read"))])
async def list_roles(
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_session),
):
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    # Count total
    count_stmt = select(func.count()).select_from(RoleModel).where(
        (RoleModel.tenant_id == tenant_id) | (RoleModel.tenant_id.is_(None))
    )
    total = db.execute(count_stmt).scalar()

    # Return System roles (tenant_id is NULL) AND Custom roles (tenant_id matches)
    stmt = select(RoleModel).where(
        (RoleModel.tenant_id == tenant_id) | (RoleModel.tenant_id.is_(None))
    ).offset(pagination.skip).limit(pagination.limit)
    roles = db.execute(stmt).scalars().all()

    results = []
    for r in roles:
        results.append(RoleResponse(id=r.id, name=r.name, is_system=r.tenant_id is None))
    return PaginatedResponse(items=results, total=total, skip=pagination.skip, limit=pagination.limit)
