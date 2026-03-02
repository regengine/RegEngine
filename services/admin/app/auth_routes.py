from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import timedelta, datetime, timezone
import structlog
from pydantic import BaseModel
from typing import List, Dict, Optional
from uuid import UUID
import uuid

from app.database import get_session
from app.sqlalchemy_models import UserModel, MembershipModel, TenantModel
from app.auth_utils import verify_password, get_password_hash, create_access_token, create_refresh_token, decode_access_token, hash_token, REFRESH_TOKEN_EXPIRE_DAYS
from app.dependencies import get_current_user, PermissionChecker, get_session_store
from app.audit import AuditLogger
from app.password_policy import validate_password, PasswordPolicyError
from app.session_store import RedisSessionStore, SessionData


router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger("auth")

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str
    tenant_id: Optional[UUID] = None
    user: Dict
    available_tenants: List[Dict]

class RegisterRequest(BaseModel):
    email: str
    password: str
    tenant_name: str

class UserResponse(BaseModel):
    id: UUID
    email: str
    is_sysadmin: bool
    status: str

@router.get("/me", response_model=UserResponse)
def get_me(user: UserModel = Depends(get_current_user)):
    """Get current user context (verifies token and tenant context)."""
    return user

@router.get("/check-permission")
def check_perm(
    user: UserModel = Depends(get_current_user), 
    authorized: bool = Depends(PermissionChecker("admin.read"))
):
    """Test RBAC."""
    return {"message": "Permission granted", "user": user.email}

@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_session),
    session_store: RedisSessionStore = Depends(get_session_store)
):
    # 1. Verify User
    stmt = select(UserModel).where(UserModel.email == payload.email)
    user = db.execute(stmt).scalar_one_or_none()
    
    if not user or not verify_password(payload.password, user.password_hash):
        logger.warning("login_failed", reason="invalid_credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account disabled")

    # 2. Get Memberships
    stmt_mem = select(MembershipModel, TenantModel)\
        .join(TenantModel, MembershipModel.tenant_id == TenantModel.id)\
        .where(MembershipModel.user_id == user.id)
    results = db.execute(stmt_mem).all()
    
    available_tenants = []
    active_tenant_id = None
    
    for mem, tenant in results:
        available_tenants.append({"id": tenant.id, "name": tenant.name, "slug": tenant.slug})
        if not active_tenant_id:
            active_tenant_id = tenant.id
    
    # 3. Create Session in Redis (replaces PostgreSQL session)
    raw_refresh_token = create_refresh_token()
    token_hash = hash_token(raw_refresh_token)
    family_id = uuid.uuid4()
    
    session_data = SessionData(
        id=uuid.uuid4(),
        user_id=user.id,
        refresh_token_hash=token_hash,
        family_id=family_id,
        created_at=datetime.now(timezone.utc),
        last_used_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=request.headers.get("User-Agent", "Unknown"),
        ip_address=request.client.host if request.client else "0.0.0.0"
    )
    
    session_persisted = True
    try:
        await session_store.create_session(session_data)
    except Exception as exc:
        session_persisted = False
        logger.warning(
            "session_store_unavailable",
            user_id=str(user.id),
            error=str(exc),
            fallback="stateless_session",
        )

    # 4. Create Access Token
    access_token_data = {
        "sub": str(user.id),
        "email": user.email,
        "tenant_id": str(active_tenant_id) if active_tenant_id else None,  # For RLS
        "tid": str(active_tenant_id) if active_tenant_id else None  # Backward compat
    }
    
    access_token = create_access_token(access_token_data)
    
    # Audit Log
    if active_tenant_id:
        AuditLogger.log_event(
            db,
            tenant_id=active_tenant_id,
            event_type="user.login",
            action="session.create",
            event_category="authentication",
            actor_id=user.id,
            resource_type="session",
            resource_id=str(session_data.id),
            metadata={"session_persisted": session_persisted},
        )

    db.commit()
    
    logger.info(
        "login_success",
        user_id=str(user.id),
        session_id=str(session_data.id),
        session_persisted=session_persisted,
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh_token if session_persisted else "",
        tenant_id=active_tenant_id,
        user={"id": str(user.id), "email": user.email, "is_sysadmin": user.is_sysadmin},
        available_tenants=available_tenants
    )



class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/refresh", response_model=TokenResponse)
async def refresh_session(
    payload: RefreshRequest,
    db: Session = Depends(get_session),
    session_store: RedisSessionStore = Depends(get_session_store)
):
    input_hash = hash_token(payload.refresh_token)
    
    # Find session by hash in Redis
    session = await session_store.get_session_by_token(input_hash)
    
    if not session:
        # Invalid refresh token
        logger.warning("refresh_invalid_token", token_hash=input_hash[:8])
        raise HTTPException(status_code=401, detail="Invalid refresh token")
        
    if session.is_revoked:
        # Session revoked - potential theft
        logger.warning("refresh_attempt_revoked_session", session_id=str(session.id))
        raise HTTPException(status_code=401, detail="Session revoked")

    if session.expires_at < datetime.now(timezone.utc):
        logger.warning("refresh_expired_session", session_id=str(session.id))
        raise HTTPException(status_code=401, detail="Session expired")
        
    # ROTATION: Generate new refresh token
    new_raw_refresh_token = create_refresh_token()
    new_hash = hash_token(new_raw_refresh_token)
    
    # Update session with new token hash and timestamps
    await session_store.update_session(
        session.id,
        {
            "refresh_token_hash": new_hash,
            "last_used_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).isoformat()
        },
        new_token_hash=new_hash,
        old_token_hash=input_hash
    )
    
    # Re-issue Access Token
    user = db.get(UserModel, session.user_id)
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    # Get active tenant (default to first available)
    stmt_mem = select(MembershipModel).where(MembershipModel.user_id == user.id)
    memberships = db.execute(stmt_mem).scalars().all()
    active_tenant_id = memberships[0].tenant_id if memberships else None
    
    access_token_data = {
        "sub": str(user.id),
        "email": user.email,
        "tenant_id": str(active_tenant_id) if active_tenant_id else None,  # For RLS
        "tid": str(active_tenant_id) if active_tenant_id else None  # Backward compat
    }
    access_token = create_access_token(access_token_data)
    
    db.commit()
    
    logger.info("token_refreshed", user_id=str(user.id), session_id=str(session.id))
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_raw_refresh_token,
        tenant_id=active_tenant_id,
        user={"id": str(user.id), "email": user.email, "is_sysadmin": user.is_sysadmin},
        available_tenants=[] # Don't need full list on refresh
    )


@router.get("/sessions", dependencies=[Depends(get_current_user)])
async def list_sessions(
    current_user: UserModel = Depends(get_current_user),
    session_store: RedisSessionStore = Depends(get_session_store)
):
    # Get all active sessions for user from Redis
    sessions = await session_store.list_user_sessions(current_user.id, active_only=True)
    
    return [
        {
            "id": str(s.id),
            "created_at": s.created_at.isoformat(),
            "last_used_at": s.last_used_at.isoformat(),
            "user_agent": s.user_agent,
            "ip_address": s.ip_address
        }
        for s in sessions
    ]

@router.post("/sessions/{session_id}/revoke", dependencies=[Depends(get_current_user)])
async def revoke_session(
    session_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    session_store: RedisSessionStore = Depends(get_session_store)
):
    # Get session from Redis
    session = await session_store.get_session(session_id)
    
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Revoke in Redis
    await session_store.revoke_session(session_id)
    
    logger.info("session_revoked", session_id=str(session_id), user_id=str(current_user.id))
    
    return {"status": "revoked"}

@router.post("/logout-all", dependencies=[Depends(get_current_user)])
async def revoke_all_sessions(
    current_user: UserModel = Depends(get_current_user),
    session_store: RedisSessionStore = Depends(get_session_store)
):
    # Revoke all active sessions for this user in Redis
    count = await session_store.revoke_all_user_sessions(current_user.id)
    
    logger.info("all_sessions_revoked", user_id=str(current_user.id), count=count)
    
    return {"status": "success", "revoked_count": count}



@router.post("/register")
def register_initial_admin(payload: RegisterRequest, db: Session = Depends(get_session)):
    """Bootstrapping endpoint to create the first admin and tenant."""
    # Check if any users exist to prevent abuse
    if db.execute(select(UserModel)).first():
        raise HTTPException(status_code=403, detail="Registration disabled. Use invites.")

    # Validate password against policy
    try:
        validate_password(payload.password, user_context={'email': payload.email})
    except PasswordPolicyError as e:
        raise HTTPException(status_code=400, detail=e.message)

    # Create User
    new_user = UserModel(
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        is_sysadmin=True,
        status="active"
    )
    db.add(new_user)
    db.flush()
    
    # Create Tenant
    new_tenant = TenantModel(
        name=payload.tenant_name,
        slug=payload.tenant_name.lower().replace(" ", "-"),
        status="active"
    )
    db.add(new_tenant)
    db.flush()
    
    # Create Admin Role
    from app.sqlalchemy_models import RoleModel
    owner_role = RoleModel(
        tenant_id=new_tenant.id,
        name="Owner",
        permissions=["*"]
    )
    db.add(owner_role)
    db.flush()
    
    # Create Membership
    membership = MembershipModel(
        user_id=new_user.id,
        tenant_id=new_tenant.id,
        role_id=owner_role.id
    )
    db.add(membership)
    
    # Audit Log
    AuditLogger.log_event(
        db,
        tenant_id=new_tenant.id,
        event_type="tenant.create",
        action="tenant.create",
        event_category="tenant_management",
        actor_id=new_user.id,
        resource_type="tenant",
        resource_id=str(new_tenant.id),
        metadata={"tenant_name": new_tenant.name},
    )
    db.commit()
    
    return {"message": "Admin created", "user_id": str(new_user.id), "tenant_id": str(new_tenant.id)}
