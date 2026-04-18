from fastapi import Depends, HTTPException, Path, status, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import select, text
from uuid import UUID
from typing import List, Optional
import structlog
from jwt.exceptions import PyJWTError as JWTError
import os

from .database import get_session
from .sqlalchemy_models import UserModel, MembershipModel, RoleModel
from .models import TenantContext
from .auth_utils import decode_access_token
# Supabase Integration
from shared.supabase_client import get_supabase
from shared.permissions import has_permission
from shared.env import is_production

# Redis Session Store
from .session_store import RedisSessionStore, redact_connection_url

# Define oauth2_scheme (although we use custom login mostly, this helps Swagger UI)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

logger = structlog.get_logger("auth_dependency")

# Global session store instance (singleton)
_session_store: Optional[RedisSessionStore] = None

def get_session_store() -> RedisSessionStore:
    """Dependency injection for Redis session store.
    
    Returns singleton instance of RedisSessionStore.
    Lazily initialized on first call.
    """
    global _session_store
    if _session_store is None:
        redis_url = os.getenv("REDIS_URL", "rediss://redis:6379/0")
        _session_store = RedisSessionStore(redis_url)
        logger.info("session_store_initialized", redis_url=redact_connection_url(redis_url))
    return _session_store


async def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: Session = Depends(get_session)
) -> UserModel:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    user_id = None
    tenant_id = None

    # 1. Try Supabase Auth First (Production Path)
    sb = get_supabase()
    if sb:
        try:
            # Supabase validates the JWT signature and expiration against the project
            user_response = sb.auth.get_user(token)
            if user_response and user_response.user:
                sb_user = user_response.user
                user_id = sb_user.id
                # SECURITY (#1345): tenant_id MUST come from app_metadata
                # (service-role-only writable), NEVER from user_metadata
                # (user-writable via supabase.auth.updateUser). Reading
                # user_metadata lets a multi-tenant user silently switch
                # which tenant they act as from the browser.
                app_meta = getattr(sb_user, "app_metadata", None) or {}
                tenant_id = app_meta.get("tenant_id")

                # User existence verified at line 101 below (db.get raises if missing)
        except (OSError, TimeoutError, ConnectionError, ValueError, AttributeError) as e:
            logger.warning("supabase_auth_failed", error=str(e))
            # In production, fail closed — do not fall through to local JWT
            # unless explicitly opted out via ALLOW_LOCAL_JWT_FALLBACK=true
            if is_production() and not os.getenv("ALLOW_LOCAL_JWT_FALLBACK", "").lower() in ("true", "1"):
                logger.error("supabase_auth_failed_production_fail_closed", error=str(e))
                raise credentials_exception

    # 2. Fallback to Local JWT (Legacy / Dev Path)
    # Only reached in dev, or if Supabase is not configured, or explicit opt-in
    if not user_id:       
        try:
            payload = decode_access_token(token)
            user_id: str = payload.get("sub")
            # Try new tenant_id claim first, fallback to tid for backward compat
            tenant_id: str = payload.get("tenant_id") or payload.get("tid")
            
            if user_id is None:
                raise credentials_exception
                
        except JWTError:
            raise credentials_exception
        
    # Set user_id context for RLS so the user can see themselves (PostgreSQL only)
    if db.bind and db.bind.dialect.name != "sqlite":
        db.execute(
            text("SELECT set_config('regengine.user_id', :uid, false)"),
            {"uid": str(user_id)}
        )

    user = db.get(UserModel, UUID(user_id))
    if user is None:
        logger.warning("user_not_found_in_db", user_id=user_id)
        raise credentials_exception

    logger.info("user_authenticated", user_id=user_id)

    # SECURITY (#1345): if no trusted tenant claim is present, derive from
    # the DB — but only when there is exactly one active membership. Users
    # who belong to multiple tenants must have tenant_id written into
    # app_metadata (or the local JWT) by the server; we refuse to guess.
    if not tenant_id:
        active_memberships = db.execute(
            select(MembershipModel).where(
                MembershipModel.user_id == UUID(user_id),
                MembershipModel.is_active == True,  # noqa: E712  (SQLAlchemy needs ==)
            )
        ).scalars().all()
        if len(active_memberships) == 1:
            tenant_id = str(active_memberships[0].tenant_id)
            logger.info(
                "tenant_derived_from_sole_membership",
                user_id=user_id,
                tenant_id=tenant_id,
            )
        elif len(active_memberships) > 1 and not user.is_sysadmin:
            logger.warning(
                "ambiguous_tenant_no_trusted_claim",
                user_id=user_id,
                membership_count=len(active_memberships),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tenant selection required — no app_metadata.tenant_id set",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
    # Store tenant context in request state or handle via DB session context
    if tenant_id:
        try:
            # Enforce RLS context (PostgreSQL only — SQLite has no RLS)
            if db.bind and db.bind.dialect.name != "sqlite":
                TenantContext.set_tenant_context(db, UUID(tenant_id))
            # Verify membership exists for this tenant
            membership = db.execute(
                select(MembershipModel).where(
                    MembershipModel.user_id == UUID(user_id),
                    MembershipModel.tenant_id == UUID(tenant_id)
                )
            ).scalar_one_or_none()
            
            if not membership:
                 logger.warning("invalid_tenant_context", user_id=user_id, tenant_id=tenant_id)
                 raise credentials_exception
            
            if not membership.is_active:
                 logger.warning("deactivated_user_access_attempt", user_id=user_id, tenant_id=tenant_id)
                 raise credentials_exception

        except (RuntimeError, OSError, ValueError, KeyError, AttributeError) as e:
            logger.error("tenant_context_error", error=str(e))
            raise credentials_exception

    return user

class PermissionChecker:
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    def __call__(self, user: UserModel = Depends(get_current_user), db: Session = Depends(get_session)):
        # Inspect current tenant context from session? 
        # Since set_tenant_context was called in get_current_user, RLS is active.
        # But we need to check the Roles/Permissions for the current tenant.
        
        # We need to retrieve the tenant_id embedded in the current RLS context
        # OR we parse it from the token again (but get_current_user already did).
        # We can also get it from `db` if we trust `get_tenant_context`.
        
        current_tenant_id = TenantContext.get_tenant_context(db)
        if not current_tenant_id:
            # If no tenant context, only system-wide permissions apply (if implemented)
            # OR we fail for tenant-scoped resources
            if user.is_sysadmin:
                return True
            raise HTTPException(status_code=403, detail="No tenant context active")
            
        # Get Membership and Role
        stmt = select(RoleModel).join(MembershipModel).where(
            MembershipModel.user_id == user.id,
            MembershipModel.tenant_id == current_tenant_id,
        )
        role = db.execute(stmt).scalar_one_or_none()
        
        if not role:
             raise HTTPException(status_code=403, detail="Role not found")
             
        # Check permissions with wildcard and namespace support.
        if has_permission(role.permissions or [], self.required_permission):
            return True
            
        raise HTTPException(status_code=403, detail="Insufficient permissions")


def verify_path_tenant_matches(
    tenant_id: str = Path(...),
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> UUID:
    """Reject a request when the URL path ``tenant_id`` does not match the
    caller's authenticated tenant context.

    Without this, routes shaped as ``/v1/compliance/{tenant_id}/...`` accept
    any UUID in the path and pass it straight to the service layer, producing
    a trivial IDOR: caller in tenant A supplies tenant B's UUID and reads or
    mutates tenant B's data. See #1328.
    """
    try:
        path_tenant = UUID(tenant_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid tenant_id format")

    auth_tenant = TenantContext.get_tenant_context(db)
    if auth_tenant is None:
        if user.is_sysadmin:
            return path_tenant
        logger.warning("path_tenant_check_no_context", user_id=str(user.id))
        raise HTTPException(status_code=403, detail="No tenant context active")

    if path_tenant != auth_tenant and not user.is_sysadmin:
        logger.warning(
            "cross_tenant_path_access_denied",
            user_id=str(user.id),
            auth_tenant=str(auth_tenant),
            path_tenant=str(path_tenant),
        )
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    return path_tenant


# --- API Key Auth (Remediation Phase 1) ---
from fastapi.security import APIKeyHeader
from shared.api_key_store import get_db_key_store

api_key_header = APIKeyHeader(name="X-RegEngine-API-Key", auto_error=False)

async def get_current_tenant(
    key: str = Depends(api_key_header),
    db: Session = Depends(get_session)
) -> UUID:
    """
    Validates API Key and returns the associated Tenant ID.
    Enforces Strict Security Boundary (Constitution 4.1).
    Sets the RLS session context for the database connection.
    """
    if not key:
        raise HTTPException(status_code=401, detail="Missing API Key")

    store = await get_db_key_store()
    api_key_data = await store.validate_key(key)
    
    if not api_key_data:
        raise HTTPException(status_code=403, detail="Invalid API Key")
        
    if not api_key_data.tenant_id:
         raise HTTPException(status_code=403, detail="API Key not associated with a Tenant")
         
    tenant_id = UUID(api_key_data.tenant_id)
    # SEC-RLS: Ensure the database session is restricted to this tenant
    TenantContext.set_tenant_context(db, tenant_id)
    
    return tenant_id
