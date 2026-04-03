from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import timedelta, datetime, timezone
import structlog
from pydantic import BaseModel
from typing import List, Dict, Optional
from uuid import UUID
import uuid
import re

from app.database import get_session
from app.sqlalchemy_models import UserModel, MembershipModel, TenantModel, RoleModel
from app.auth_utils import verify_password, get_password_hash, create_access_token, create_refresh_token, decode_access_token, hash_token, REFRESH_TOKEN_EXPIRE_DAYS
from app.dependencies import get_current_user, PermissionChecker, get_session_store
from app.audit import AuditLogger
from app.password_policy import validate_password, PasswordPolicyError
from app.session_store import RedisSessionStore, SessionData
from shared.supabase_client import get_supabase
from shared.funnel_events import emit_funnel_event
from shared.rate_limit import limiter

import asyncio

router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger("auth")


async def _persist_session(
    session_store: RedisSessionStore,
    session_data: SessionData,
    *,
    context: str,
    user_id: UUID,
) -> None:
    """Persist session to Redis with one retry. Raises 503 on failure.

    A missing session record means the refresh token can never be validated,
    creating a zombie session that silently expires and kicks the user out.
    Failing fast with 503 is better than a half-working login.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(2):
        try:
            await session_store.create_session(session_data)
            return
        except Exception as exc:
            last_exc = exc
            if attempt == 0:
                logger.warning(
                    "session_store_retry",
                    context=context,
                    user_id=str(user_id),
                    error=str(exc),
                )
                await asyncio.sleep(0.25)  # brief back-off before retry

    # Both attempts failed
    logger.error(
        "session_store_unavailable",
        context=context,
        user_id=str(user_id),
        error=str(last_exc),
    )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Session service temporarily unavailable. Please try again.",
    )

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


def _slugify_tenant_name(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return base or "tenant"


def _ensure_unique_tenant_slug(db: Session, tenant_name: str) -> str:
    base_slug = _slugify_tenant_name(tenant_name)
    slug = base_slug
    suffix = 2
    while db.execute(select(TenantModel).where(TenantModel.slug == slug)).scalar_one_or_none():
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug

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
@limiter.limit("10/minute")
async def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_session),
    session_store: RedisSessionStore = Depends(get_session_store)
):
    # 1. Verify User (normalize email to lowercase for case-insensitive match)
    normalized_login_email = payload.email.strip().lower()
    stmt = select(UserModel).where(UserModel.email == normalized_login_email)
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
    active_tenant_status = None

    for mem, tenant in results:
        available_tenants.append({"id": tenant.id, "name": tenant.name, "slug": tenant.slug})
        if not active_tenant_id:
            active_tenant_id = tenant.id
            active_tenant_status = tenant.status
    
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
    
    # Persist session — retries once, then fails with 503 so the user
    # gets a clean error instead of a zombie session that can't refresh.
    await _persist_session(
        session_store, session_data,
        context="login",
        user_id=user.id,
    )

    # 4. Create Access Token
    access_token_data = {
        "sub": str(user.id),
        "email": user.email,
        "tenant_id": str(active_tenant_id) if active_tenant_id else None,  # For RLS
        "tid": str(active_tenant_id) if active_tenant_id else None,  # Backward compat
        "tenant_status": active_tenant_status,  # Middleware checks this to reject suspended tenants
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
        )

    db.commit()

    logger.info(
        "login_success",
        user_id=str(user.id),
        session_id=str(session_data.id),
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        tenant_id=active_tenant_id,
        user={"id": str(user.id), "email": user.email, "is_sysadmin": user.is_sysadmin},
        available_tenants=available_tenants
    )


@router.post("/signup", response_model=TokenResponse)
async def signup(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_session),
    session_store: RedisSessionStore = Depends(get_session_store),
):
    """Self-serve signup that creates tenant + owner membership and returns session tokens."""
    normalized_email = payload.email.strip().lower()
    tenant_name = payload.tenant_name.strip()
    if not tenant_name:
        raise HTTPException(status_code=400, detail="Tenant name is required")

    existing_user = db.execute(
        select(UserModel).where(UserModel.email == normalized_email)
    ).scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=409, detail="User already exists")

    try:
        validate_password(payload.password, user_context={"email": normalized_email})
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=400, detail=exc.message)

    supabase_user_id: Optional[UUID] = None
    sb = get_supabase()
    if sb:
        try:
            supabase_response = sb.auth.admin.create_user(
                {
                    "email": normalized_email,
                    "password": payload.password,
                    "email_confirm": True,
                    "user_metadata": {"tenant_name": tenant_name},
                }
            )
            supabase_user = getattr(supabase_response, "user", None)
            if supabase_user and getattr(supabase_user, "id", None):
                supabase_user_id = UUID(str(supabase_user.id))
        except (OSError, TimeoutError, ConnectionError, ValueError, RuntimeError, AttributeError) as exc:  # pragma: no cover - external dependency behavior
            logger.warning("supabase_signup_provisioning_failed", email=normalized_email, error=str(exc))

    new_user = UserModel(
        id=supabase_user_id or uuid.uuid4(),
        email=normalized_email,
        password_hash=get_password_hash(payload.password),
        is_sysadmin=False,
        status="active",
    )
    db.add(new_user)
    db.flush()

    new_tenant = TenantModel(
        name=tenant_name,
        slug=_ensure_unique_tenant_slug(db, tenant_name),
        status="active",
        settings={
            "onboarding": {
                "workspace_setup_completed": False,
                "facility_created": False,
                "ftl_check_completed": False,
                "first_document_imported": False,
                "team_member_invited": False,
                "mock_drill_run": False,
            }
        },
    )
    db.add(new_tenant)
    db.flush()

    owner_role = RoleModel(
        tenant_id=new_tenant.id,
        name="Owner",
        permissions=["*"],
    )
    db.add(owner_role)
    db.flush()

    membership = MembershipModel(
        user_id=new_user.id,
        tenant_id=new_tenant.id,
        role_id=owner_role.id,
    )
    db.add(membership)

    raw_refresh_token = create_refresh_token()
    token_hash = hash_token(raw_refresh_token)
    family_id = uuid.uuid4()
    session_data = SessionData(
        id=uuid.uuid4(),
        user_id=new_user.id,
        refresh_token_hash=token_hash,
        family_id=family_id,
        created_at=datetime.now(timezone.utc),
        last_used_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=request.headers.get("User-Agent", "Unknown"),
        ip_address=request.client.host if request.client else "0.0.0.0",
    )

    # Commit the user + tenant + membership rows BEFORE attempting Redis.
    # If Redis fails (503), the user still exists in the DB and can retry login.
    db.commit()

    # Persist session — retries once, then fails with 503.
    await _persist_session(
        session_store, session_data,
        context="signup",
        user_id=new_user.id,
    )

    access_token_data = {
        "sub": str(new_user.id),
        "email": new_user.email,
        "tenant_id": str(new_tenant.id),
        "tid": str(new_tenant.id),
    }
    access_token = create_access_token(access_token_data)

    AuditLogger.log_event(
        db,
        tenant_id=new_tenant.id,
        event_type="tenant.create",
        action="tenant.create",
        event_category="tenant_management",
        actor_id=new_user.id,
        resource_type="tenant",
        resource_id=str(new_tenant.id),
        metadata={"tenant_name": new_tenant.name, "signup": True},
    )

    emit_funnel_event(
        tenant_id=str(new_tenant.id),
        event_name="signup_completed",
        metadata={
            "source": "auth.signup",
            "user_id": str(new_user.id),
        },
        db_session=db,
    )

    db.commit()

    logger.info(
        "signup_success",
        user_id=str(new_user.id),
        tenant_id=str(new_tenant.id),
        supabase_user_linked=bool(supabase_user_id),
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        tenant_id=new_tenant.id,
        user={"id": str(new_user.id), "email": new_user.email, "is_sysadmin": new_user.is_sysadmin},
        available_tenants=[{"id": new_tenant.id, "name": new_tenant.name, "slug": new_tenant.slug}],
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

    # Atomically claim the token — GETDEL ensures only one concurrent
    # refresh request succeeds. The second request finds the mapping gone
    # and gets 401, preventing the "last write wins" race condition where
    # two tabs refresh simultaneously and one gets an invalidated token.
    session = await session_store.claim_session_by_token(input_hash)

    if not session:
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
    
    # Update session with new token hash and timestamps.
    # old_token_hash already deleted by claim_session_by_token (GETDEL).
    await session_store.update_session(
        session.id,
        {
            "refresh_token_hash": new_hash,
            "last_used_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).isoformat()
        },
        new_token_hash=new_hash,
    )
    
    # Re-issue Access Token
    user = db.get(UserModel, session.user_id)
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    # Get first active tenant — must join TenantModel to filter out
    # suspended/archived tenants so they cannot receive fresh access tokens.
    stmt_mem = (
        select(MembershipModel)
        .join(TenantModel, MembershipModel.tenant_id == TenantModel.id)
        .where(
            MembershipModel.user_id == user.id,
            MembershipModel.is_active == True,  # noqa: E712
            TenantModel.status == "active",
        )
    )
    memberships = db.execute(stmt_mem).scalars().all()
    active_tenant_id = memberships[0].tenant_id if memberships else None

    if not active_tenant_id:
        logger.warning("refresh_no_active_tenant", user_id=str(user.id))
        raise HTTPException(status_code=403, detail="No active tenant available")
    
    access_token_data = {
        "sub": str(user.id),
        "email": user.email,
        "tenant_id": str(active_tenant_id) if active_tenant_id else None,  # For RLS
        "tid": str(active_tenant_id) if active_tenant_id else None,  # Backward compat
        "tenant_status": "active",  # Only active tenants reach this point (query filters above)
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
@limiter.limit("3/minute")
def register_initial_admin(payload: RegisterRequest, request: Request, db: Session = Depends(get_session)):
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
