"""Shared authentication and authorization utilities for RegEngine services."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Optional, Union

import structlog
from fastapi import Header, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
import os

logger = structlog.get_logger("auth")


def validate_auth_config() -> None:
    """Validate critical auth configuration at service startup.

    Call this from each service's main.py after app creation.
    Logs warnings for missing config and raises on fatal misconfigurations.

    Note: Supabase credential checks were removed (H2 postmortem). The
    SupabaseManager.get_client() already handles missing creds gracefully
    by returning None. Duplicating that check here caused production
    outages when env var names didn't match expectations.
    """
    issues: list[str] = []

    # JWT secret must be set and non-trivial
    jwt_secret = os.getenv("AUTH_SECRET_KEY") or os.getenv("JWT_SECRET")
    if not jwt_secret:
        issues.append("AUTH_SECRET_KEY / JWT_SECRET not set — JWT auth will fail")
    elif len(jwt_secret) < 16:
        issues.append("AUTH_SECRET_KEY is too short (<16 chars) — insecure for production")
    elif jwt_secret in ("dev_secret_key_change_me", "your-secret", "changeme", "secret"):
        issues.append("AUTH_SECRET_KEY is a known default — change it before production")

    # API key should be set for proxy auth
    api_key = os.getenv("REGENGINE_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        logger.warning("validate_auth_config", msg="REGENGINE_API_KEY not set — proxy auth will fail")

    # Test bypass should not be active in production
    bypass_token = os.getenv("AUTH_TEST_BYPASS_TOKEN")
    env = os.getenv("REGENGINE_ENV", "production").lower()
    if bypass_token and env == "production":
        issues.append("AUTH_TEST_BYPASS_TOKEN is set in production — remove it")

    for issue in issues:
        logger.error("auth_config_validation_failed", issue=issue)

    # Only raise when REGENGINE_ENV is explicitly set to "production".
    # If unset, we assume local development — warn but don't crash.
    is_ci = os.getenv("GITHUB_ACTIONS") or os.getenv("CI")
    is_explicit_production = os.getenv("REGENGINE_ENV", "").lower() == "production"
    if issues and is_explicit_production and not is_ci:
        raise RuntimeError(
            f"Auth config validation failed ({len(issues)} issues): "
            + "; ".join(issues)
        )


# API Key header scheme
api_key_header = APIKeyHeader(name="X-RegEngine-API-Key", auto_error=False)


class APIKey(BaseModel):
    """API Key model for authentication."""

    key_id: str
    key_hash: str
    name: str
    tenant_id: Optional[str] = None  # UUID of tenant this key belongs to
    billing_tier: Optional[str] = None  # DEVELOPER, PROFESSIONAL, ENTERPRISE
    allowed_jurisdictions: list[str] = []  # e.g., ["US"], ["US","US-NY"]
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    rate_limit_per_minute: int = 60
    enabled: bool = True
    scopes: list[str] = []


class APIKeyStore:
    """In-memory API key store. In production, use Redis or a database.
    
    Thread-safe: All operations on _keys and _rate_limits are protected by a lock.
    """

    def __init__(self):
        self._keys: dict[str, APIKey] = {}
        self._rate_limits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def create_key(
        self,
        name: str,
        tenant_id: Optional[str] = None,
        rate_limit_per_minute: int = 60,
        expires_at: Optional[datetime] = None,
        scopes: Optional[list[str]] = None,
        billing_tier: Optional[str] = None,
        allowed_jurisdictions: Optional[list[str]] = None,
    ) -> tuple[str, APIKey]:
        """Create a new API key and return the raw key + metadata.

        Args:
            name: Human-readable key name
            tenant_id: UUID of tenant this key belongs to (for multi-tenancy)
            rate_limit_per_minute: Request rate limit
            expires_at: Optional expiration datetime
            scopes: List of permission scopes
            billing_tier: Billing tier for entitlement gating
            allowed_jurisdictions: Jurisdiction codes the tenant is entitled to

        Returns:
            Tuple of (raw_key, APIKey metadata)
        """
        key_id = f"rge_{secrets.token_urlsafe(16)}"
        raw_secret = secrets.token_urlsafe(32)
        raw_key = f"{key_id}.{raw_secret}"
        key_hash = self._hash_key(raw_key)

        api_key = APIKey(
            key_id=key_id,
            key_hash=key_hash,
            name=name,
            tenant_id=tenant_id,
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            rate_limit_per_minute=rate_limit_per_minute,
            enabled=True,
            scopes=scopes or [],
            billing_tier=billing_tier,
            allowed_jurisdictions=allowed_jurisdictions or ["US"],
        )

        with self._lock:
            self._keys[key_id] = api_key
        logger.info("api_key_created", key_id=key_id, name=name, tenant_id=tenant_id)
        return raw_key, api_key

    def validate_key(self, raw_key: str) -> Optional[APIKey]:
        """Validate an API key and return the associated metadata."""
        if not raw_key or not raw_key.startswith("rge_"):
            return None

        # Extract key_id from the raw key (first part before hash)
        try:
            key_id, _ = raw_key.split(".", 1)
        except ValueError:
            return None

        with self._lock:
            api_key = self._keys.get(key_id)
        if not api_key:
            return None

        # Verify hash using constant-time comparison
        key_hash = self._hash_key(raw_key)
        if not hmac.compare_digest(key_hash, api_key.key_hash):
            logger.warning("api_key_hash_mismatch", key_id=key_id)
            return None

        # Check if key is enabled
        if not api_key.enabled:
            logger.warning("api_key_disabled", key_id=key_id)
            return None

        # Check if key has expired
        if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
            logger.warning("api_key_expired", key_id=key_id)
            return None

        # Track last usage timestamp
        api_key.last_used_at = datetime.now(timezone.utc)

        return api_key

    def check_rate_limit(self, key_id: str, limit_per_minute: int) -> bool:
        """Check if the key has exceeded its rate limit."""
        now = time.time()
        window_start = now - 60  # 1-minute window

        with self._lock:
            # Initialize rate limit tracking for this key
            if key_id not in self._rate_limits:
                self._rate_limits[key_id] = []

            # Clean up old timestamps outside the window
            self._rate_limits[key_id] = [
                ts for ts in self._rate_limits[key_id] if ts > window_start
            ]

            # Check if we've exceeded the limit
            if len(self._rate_limits[key_id]) >= limit_per_minute:
                return False

            # Add current timestamp
            self._rate_limits[key_id].append(now)
            return True

    def revoke_key(self, key_id: str) -> bool:
        """Revoke an API key."""
        with self._lock:
            if key_id in self._keys:
                self._keys[key_id].enabled = False
                logger.info("api_key_revoked", key_id=key_id)
                return True
            return False

    def list_keys(self) -> list[APIKey]:
        """List all API keys (for admin use)."""
        with self._lock:
            return list(self._keys.values())

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        """Hash an API key using SHA256."""
        return hashlib.sha256(raw_key.encode()).hexdigest()


from shared.api_key_store import DatabaseAPIKeyStore, get_db_key_store, APIKeyResponse

# Global key store instance
_key_store = APIKeyStore()
_db_store_instance: Optional[DatabaseAPIKeyStore] = None

def get_key_store() -> Union[APIKeyStore, DatabaseAPIKeyStore]:
    """Get the global API key store instance.

    In production, always returns DatabaseAPIKeyStore.
    In development/test, returns in-memory APIKeyStore unless ENABLE_DB_API_KEYS=true.
    """
    env = os.getenv("REGENGINE_ENV", "production").lower()
    use_db = (
        env == "production"
        or os.getenv("ENABLE_DB_API_KEYS", "false").lower() == "true"
    )
    if use_db:
        global _db_store_instance
        if _db_store_instance is None:
            _db_store_instance = DatabaseAPIKeyStore()
        return _db_store_instance
    return _key_store


async def require_api_key(
    request: Request,
    x_regengine_api_key: Optional[str] = Header(None, alias="X-RegEngine-API-Key"),
) -> Union[APIKey, APIKeyResponse]:
    """FastAPI dependency for requiring API key authentication."""
    if not x_regengine_api_key:
        logger.warning("missing_api_key", path=request.url.path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Testing bypass: requires AUTH_TEST_BYPASS_TOKEN to be a non-empty env var
    # AND REGENGINE_ENV to be explicitly set to "development" or "test".
    # Fail closed: if either is missing or env is production, bypass is disabled.
    _test_bypass_token = os.getenv("AUTH_TEST_BYPASS_TOKEN")
    _bypass_tenant_id = os.getenv("AUTH_TEST_BYPASS_TENANT_ID", "11111111-1111-1111-1111-111111111111")
    _allowed_envs = {"development", "test"}
    _current_env = os.getenv("REGENGINE_ENV", "production").lower()
    _is_env_bypass = bool(
        _test_bypass_token
        and _current_env in _allowed_envs
        and x_regengine_api_key == _test_bypass_token
    )

    # Log a warning if bypass token is configured but we're in production
    if _test_bypass_token and _current_env not in _allowed_envs:
        logger.warning(
            "auth_bypass_blocked_in_production",
            path=request.url.path,
            env=_current_env,
            msg="AUTH_TEST_BYPASS_TOKEN is set but blocked — remove it from production config",
        )

    if _is_env_bypass:
        logger.info("test_bypass_auth_used", path=request.url.path, env=_current_env)
        return APIKey(
            key_id="test",
            key_hash="",
            name="Test Bypass Key",
            tenant_id=_bypass_tenant_id,
            created_at=datetime.now(timezone.utc),
            rate_limit_per_minute=1000,
            enabled=True,
            scopes=["read", "write", "admin"],
            billing_tier="ENTERPRISE",
            allowed_jurisdictions=["US", "US-NY", "US-CA", "EU"],
        )

    # Check preshared/master key first — same pattern as get_ingestion_principal.
    # This ensures server-side proxy injection (which uses the configured API_KEY
    # env var) works for ALL endpoints, not just those using require_permission.
    _configured_key = os.getenv("API_KEY") or os.getenv("REGENGINE_API_KEY")
    if _configured_key and x_regengine_api_key:
        import hmac as _hmac
        if _hmac.compare_digest(
            x_regengine_api_key.encode("utf-8"),
            _configured_key.encode("utf-8"),
        ):
            # Derive tenant from X-Tenant-ID header so RLS is still enforced.
            # Without this, tenant_id=None would bypass row-level security.
            # Require a non-empty, valid-UUID X-Tenant-ID — fail closed to
            # prevent the master-key path from silently disabling RLS (#1068).
            _master_tenant_raw = request.headers.get("x-tenant-id") or ""
            _master_tenant = _master_tenant_raw.strip()
            if not _master_tenant:
                logger.warning(
                    "master_key_without_tenant_id", path=request.url.path
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="E_TENANT_HEADER_REQUIRED: preshared master-key auth requires X-Tenant-ID",
                )
            try:
                uuid.UUID(_master_tenant)
            except (ValueError, AttributeError, TypeError):
                logger.warning(
                    "master_key_invalid_tenant_id",
                    path=request.url.path,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="E_TENANT_HEADER_INVALID: X-Tenant-ID must be a valid UUID",
                )
            return APIKey(
                key_id="preshared-master",
                key_hash="",
                name="Preshared Master Key",
                tenant_id=_master_tenant,
                created_at=datetime.now(timezone.utc),
                rate_limit_per_minute=1000,
                enabled=True,
                scopes=["read", "write", "admin"],
                billing_tier="ENTERPRISE",
                allowed_jurisdictions=["US", "US-NY", "US-CA", "EU"],
            )

    key_store = get_key_store()

    if isinstance(key_store, DatabaseAPIKeyStore):
        api_key = await key_store.validate_key(x_regengine_api_key)
    else:
        api_key = key_store.validate_key(x_regengine_api_key)

    if not api_key:
        logger.warning(
            "invalid_api_key", path=request.url.path, key_prefix=x_regengine_api_key[:10]
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Check rate limit
    if isinstance(key_store, DatabaseAPIKeyStore):
        rate_info = await key_store.check_rate_limit(
            api_key.key_id, api_key.rate_limit_per_minute
        )
        if not rate_info.allowed:
            logger.warning("rate_limit_exceeded", key_id=api_key.key_id)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": "60"},
            )
    else:
        if not key_store.check_rate_limit(
            api_key.key_id, api_key.rate_limit_per_minute
        ):
            logger.warning("rate_limit_exceeded", key_id=api_key.key_id)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": "60"},
            )

    logger.info(
        "api_key_used",
        key_id=api_key.key_id,
        tenant_id=getattr(api_key, "tenant_id", None),
        endpoint=request.url.path,
        method=request.method,
    )
    return api_key


async def optional_api_key(
    request: Request,
    x_regengine_api_key: Optional[str] = Header(None, alias="X-RegEngine-API-Key"),
) -> Optional[Union[APIKey, APIKeyResponse]]:
    """FastAPI dependency for optional API key authentication.

    When no key is provided, returns None (unauthenticated path).
    When a key IS provided but fails validation (expired, revoked,
    rate-limited), the HTTPException is re-raised so the caller
    receives a proper 401/429 instead of being silently downgraded
    to the unauthenticated path.
    """
    if not x_regengine_api_key:
        return None

    return await require_api_key(request, x_regengine_api_key)


def verify_jurisdiction_access(api_key: Union[APIKey, APIKeyResponse], requested_jurisdiction: str) -> None:
    """
    Enforce entitlement rules for jurisdiction access.
    - Federal (e.g., "US", "EU", "UK") allowed for all tiers.
    - State/Municipal (e.g., "US-CA", "US-TX-AUS") require entitlement in `allowed_jurisdictions`.
    Raises HTTPException(403) if not permitted.
    """
    federal_roots = {"US", "EU", "UK"}
    # Allow if root is federal
    root = requested_jurisdiction.split("-")[0] if requested_jurisdiction else ""
    allowed = api_key.allowed_jurisdictions or []
    if root in federal_roots and requested_jurisdiction == root:
        return
    # State/municipal require explicit entitlement (prefix match allowed)
    for ent in allowed:
        if requested_jurisdiction == ent:
            return
        if "-" in ent and requested_jurisdiction.startswith(ent + "-"):
            return
    raise HTTPException(status_code=403, detail="Upgrade to Professional + State Add-on")

def init_demo_keys():
    """Initialize demo API keys for development."""
    key_store = get_key_store()

    # Create demo keys with different permission levels
    demo_key, _ = key_store.create_key(
        name="Demo Key",
        rate_limit_per_minute=100,
        scopes=["read", "ingest"],
        billing_tier="DEVELOPER",
        allowed_jurisdictions=["US"],
    )

    admin_key, _ = key_store.create_key(
        name="Admin Key",
        rate_limit_per_minute=1000,
        scopes=["read", "ingest", "admin"],
        billing_tier="ENTERPRISE",
        allowed_jurisdictions=["US", "US-CA", "US-NY", "US-TX", "US-FL"],
    )

    logger.info("demo_keys_initialized", demo_key=demo_key[:8] + "...", admin_key=admin_key[:8] + "...")

    return {
        "demo_key": demo_key,
        "admin_key": admin_key,
    }


# ---------------------------------------------------------------------------
# Standardized Tenant Resolution
# ---------------------------------------------------------------------------
# Canonical dependency for deriving tenant_id. Precedence:
#   1. X-Tenant-ID header (explicit override)
#   2. Authenticated principal's tenant (from API key)
# Rejects requests where neither is present.

def get_tenant_id(
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> str:
    """Resolve tenant_id from the X-Tenant-ID header.

    Services should prefer deriving tenant from the authenticated principal
    (e.g., IngestionPrincipal.tenant_id) and fall back to this header only
    for admin/service-to-service calls.
    """
    if not x_tenant_id:
        raise HTTPException(
            status_code=400,
            detail="Missing X-Tenant-ID header. Tenant context is required.",
        )
    # Validate UUID format to prevent runtime cast errors in RLS policies
    import uuid as _uuid
    try:
        _uuid.UUID(x_tenant_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=400,
            detail="Invalid X-Tenant-ID: must be a valid UUID.",
        )
    return x_tenant_id
