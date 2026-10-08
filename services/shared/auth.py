"""Shared authentication and authorization utilities for RegEngine services."""

from __future__ import annotations

import hmac
import os
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Optional, Union

import structlog
from fastapi import Header, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

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
    # Resolve cloud markers before evaluating the controls below. Deployed
    # staging keeps its environment name, but it must still use the same
    # durable authentication backends as production.
    from shared.env import (  # noqa: PLC0415
        CLOUD_ENV_VARS,
        is_production,
        requires_strict_auth_runtime,
        validate_cloud_environment,
    )

    validate_cloud_environment()
    strict_auth = requires_strict_auth_runtime()
    issues: list[str] = []

    # JWT secret must be set and non-trivial
    jwt_secret = os.getenv("AUTH_SECRET_KEY") or os.getenv("JWT_SECRET")
    if not jwt_secret:
        issues.append("AUTH_SECRET_KEY / JWT_SECRET not set — JWT auth will fail")
    elif len(jwt_secret) < 16:
        issues.append("AUTH_SECRET_KEY is too short (<16 chars) — insecure for production")
    elif jwt_secret in ("dev_secret_key_change_me", "your-secret", "changeme", "secret"):
        issues.append("AUTH_SECRET_KEY is a known default — change it before production")

    # Test bypass should not be active in any deployed/strict runtime.
    bypass_token = os.getenv("AUTH_TEST_BYPASS_TOKEN")
    if bypass_token and strict_auth:
        issues.append("AUTH_TEST_BYPASS_TOKEN is set in a strict auth environment — remove it")

    for issue in issues:
        logger.error("auth_config_validation_failed", issue=issue)

    # Only explicit local development/test may continue after a warning.
    is_ci = os.getenv("GITHUB_ACTIONS") or os.getenv("CI")
    if issues and strict_auth and not is_ci:
        raise RuntimeError(f"Auth config validation failed ({len(issues)} issues): " + "; ".join(issues))

    # #2512: defense-in-depth fail-fast for the dev-auth-fallback surface.
    # First re-run the central gate: when ANY cloud marker is present it forces
    # REGENGINE_ENV=production (broadened beyond Railway/Vercel to Render / Fly /
    # Kubernetes), which is the normal, correct path and disables the ephemeral
    # signing-key fallbacks. We call it here too so this check sees the same
    # resolved environment regardless of import order.
    # If a cloud marker is present yet the environment STILL did not resolve to
    # production (e.g. an explicit REGENGINE_ENV=staging on a non-Railway host —
    # a case the gate intentionally leaves alone), the ephemeral-secret
    # fallbacks in admin auth_utils / tool_verification_routes are live: per-
    # process JWT / TOOL_ACCESS signing keys mean non-portable, restart-forgeable
    # sessions and invisible cross-worker revocation. Refuse to boot.
    cloud_marker_present = any(os.getenv(var) for var in CLOUD_ENV_VARS)
    if cloud_marker_present and not is_production() and not is_ci:
        ephemeral_secrets: list[str] = []
        if not (os.getenv("AUTH_SECRET_KEY") or os.getenv("JWT_SECRET")):
            ephemeral_secrets.append("AUTH_SECRET_KEY")
        if not os.getenv("TOOL_ACCESS_SECRET"):
            ephemeral_secrets.append("TOOL_ACCESS_SECRET")
        if ephemeral_secrets:
            raise RuntimeError(
                "Cloud deployment detected (marker present) but the environment did "
                "not resolve to 'production' and an ephemeral signing key is active "
                f"for: {', '.join(ephemeral_secrets)}. Set REGENGINE_ENV=production "
                "and provide these secrets before deploying — ephemeral keys produce "
                "non-portable, restart-forgeable sessions."
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

        # Check if key has expired. Naive datetimes (no tzinfo) can arrive
        # from DB rows or direct construction; assume UTC so the comparison
        # never raises TypeError (which would surface as a 500 instead of
        # an auth decision).
        if api_key.expires_at:
            expires_at = api_key.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < datetime.now(timezone.utc):
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
            self._rate_limits[key_id] = [ts for ts in self._rate_limits[key_id] if ts > window_start]

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
        """Hash an API key using the shared storage digest."""
        from shared.api_key_store import hash_api_key

        return hash_api_key(raw_key)


from shared.api_key_store import APIKeyResponse, DatabaseAPIKeyStore, get_db_key_store
from shared.tenant_context import set_rls_tenant_id

# Global key store instance
_key_store = APIKeyStore()
_db_store_instance: Optional[DatabaseAPIKeyStore] = None


def _store_api_key_principal(
    request: Request,
    api_key: Union[APIKey, APIKeyResponse],
) -> Union[APIKey, APIKeyResponse]:
    """Attach the accepted API key to request state for tenant resolution."""
    request.state.api_key = api_key
    # #2461: seed the RLS contextvar from the authenticated key's tenant
    # so the Engine begin-hook covers API-key routes that never call a
    # resolve funnel (routes_scraping enqueue, compliance, nlp routes).
    # Callers (require_api_key / optional_api_key) are async dependencies,
    # so the set is visible downstream.
    tenant_id = getattr(api_key, "tenant_id", None)
    if tenant_id:
        set_rls_tenant_id(tenant_id)
    return api_key


def get_key_store() -> Union[APIKeyStore, DatabaseAPIKeyStore]:
    """Get the global API key store instance.

    Strict deployed runtimes always return ``DatabaseAPIKeyStore``. Explicit
    local development/test returns the in-memory store unless
    ``ENABLE_DB_API_KEYS=true``.
    """
    from shared.env import requires_strict_auth_runtime

    use_db = requires_strict_auth_runtime() or os.getenv("ENABLE_DB_API_KEYS", "false").lower() == "true"
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
        _test_bypass_token and _current_env in _allowed_envs and x_regengine_api_key == _test_bypass_token
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
        api_key = APIKey(
            key_id="test",
            key_hash="",
            name="Test Bypass Key",
            tenant_id=_bypass_tenant_id,
            created_at=datetime.now(timezone.utc),
            rate_limit_per_minute=1000,
            enabled=True,
            # "webhooks.ingest" is the one permission-style scope here: the
            # Inflow Lab contract job authenticates with this credential and
            # posts to /api/v1/webhooks/ingest, which is gated by
            # require_permission("webhooks.ingest"). permission_implies()
            # treats "admin" as a plain scope, not a wildcard, so without it
            # every ingest from that job is a 403 (#3064).
            scopes=["read", "write", "admin", "webhooks.ingest"],
            billing_tier="ENTERPRISE",
            allowed_jurisdictions=["US", "US-NY", "US-CA", "EU"],
        )
        return _store_api_key_principal(request, api_key)

    key_store = get_key_store()

    if isinstance(key_store, DatabaseAPIKeyStore):
        api_key = await key_store.validate_key(x_regengine_api_key)
    else:
        api_key = key_store.validate_key(x_regengine_api_key)

    if not api_key:
        logger.warning("invalid_api_key", path=request.url.path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Tenantless/internal keys are a separate workload credential class.  The
    # one allowed workload route validates them directly through
    # require_tenant_provisioner_key; they must never be reusable through the
    # generic tenant API dependency.
    scopes = set(getattr(api_key, "scopes", None) or [])
    if not getattr(api_key, "tenant_id", None) or any(scope.startswith("internal.") for scope in scopes):
        logger.warning(
            "workload_key_rejected_on_tenant_api",
            path=request.url.path,
            key_id=getattr(api_key, "key_id", None),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workload credentials are not accepted by tenant APIs",
        )

    # Check rate limit
    if isinstance(key_store, DatabaseAPIKeyStore):
        rate_info = await key_store.check_rate_limit(api_key.key_id, api_key.rate_limit_per_minute)
        if not rate_info.allowed:
            logger.warning("rate_limit_exceeded", key_id=api_key.key_id)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                # Seconds until the key's current window ends. Falls back to the
                # full 60s window if a store ever denies without computing one.
                headers={"Retry-After": str(rate_info.retry_after or 60)},
            )
    else:
        if not key_store.check_rate_limit(api_key.key_id, api_key.rate_limit_per_minute):
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
    return _store_api_key_principal(request, api_key)


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
    # ``None`` means the header was absent and is the only anonymous case.
    # An explicitly empty header is still a presented credential and must
    # reach require_api_key so it is rejected with the normal 401 contract.
    if x_regengine_api_key is None:
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
    demo_tenant_id = os.getenv("REGENGINE_DEMO_TENANT_ID", "11111111-1111-1111-1111-111111111111")

    # Create demo keys with different permission levels
    demo_key, _ = key_store.create_key(
        name="Demo Key",
        tenant_id=demo_tenant_id,
        rate_limit_per_minute=100,
        scopes=["read", "ingest"],
        billing_tier="DEVELOPER",
        allowed_jurisdictions=["US"],
    )

    admin_key, _ = key_store.create_key(
        name="Admin Key",
        tenant_id=demo_tenant_id,
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
# Canonical reconciliation helper for credential-bound tenant identity. The
# authenticated principal is authoritative; X-Tenant-ID is only an assertion
# that must match it.


def reconcile_tenant_scope(
    api_key: Optional["APIKey"],
    middleware_tenant_id: object,
    *,
    request_path: Optional[str] = None,
) -> str:
    """Reconcile the two independent tenant sources that drive one request.

    Handlers that depend on BOTH ``require_api_key`` (authenticated
    principal) and ``get_current_tenant_id`` (TenantContextMiddleware) have
    two separately-resolved tenant values. They can diverge when a caller's
    optional ``X-Tenant-ID`` assertion does not match the database-bound API
    key. This helper makes them fail closed by construction and returns the
    authenticated API-key tenant as the single source of truth for downstream
    scoping (DB selection, query predicates).

    Mirrors ``services/compliance/app/routes.py`` FDA-export tenant binding
    (#1106). See issue #2511.

    Args:
        api_key: The authenticated ``APIKey`` (from ``require_api_key``).
        middleware_tenant_id: The middleware-resolved tenant (from
            ``get_current_tenant_id`` — a ``uuid.UUID`` in practice). Any
            value with a ``str()`` representation is accepted.
        request_path: Optional request path, for log context only.

    Returns:
        The authenticated tenant id as a string.

    Raises:
        HTTPException: 403 if the API key has no tenant; 409
            (``E_TENANT_MISMATCH``) if the two tenant sources disagree.
    """
    authenticated_tenant_id = getattr(api_key, "tenant_id", None)
    if not authenticated_tenant_id:
        raise HTTPException(
            status_code=403,
            detail="API key is not associated with a tenant",
        )
    authenticated_tenant = str(authenticated_tenant_id)

    # ``middleware_tenant_id`` is non-optional at the handler (the
    # get_current_tenant_id dependency 401s when absent), but guard anyway.
    middleware_tenant = str(middleware_tenant_id) if middleware_tenant_id is not None else None
    if middleware_tenant and middleware_tenant != authenticated_tenant:
        logger.warning(
            "graph_tenant_scope_mismatch",
            authenticated_tenant=authenticated_tenant,
            middleware_tenant=middleware_tenant,
            key_id=getattr(api_key, "key_id", None),
            path=request_path,
        )
        raise HTTPException(
            status_code=409,
            detail="E_TENANT_MISMATCH",
        )
    return authenticated_tenant


def get_tenant_id(
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> str:
    """Resolve tenant_id from the X-Tenant-ID header.

    This validates syntax only. Services must derive authorization from the
    authenticated principal and treat this header as a matching assertion,
    never as an independent authentication or tenant-selection mechanism.
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
