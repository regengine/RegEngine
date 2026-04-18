from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid
import jwt
from passlib.context import CryptContext
import os
import secrets
import logging

_logger = logging.getLogger("auth_utils")

# ──────────────────────────────────────────────────────────────
# JWT Secret Key — MUST be set in production.
# In development, falls back to a random key (sessions won't
# survive restarts, which is acceptable for local dev).
# ──────────────────────────────────────────────────────────────
_env_secret = os.getenv("AUTH_SECRET_KEY")
if not _env_secret:
    _is_production = os.getenv("REGENGINE_ENV", "").lower() == "production"
    if _is_production:
        raise RuntimeError(
            "AUTH_SECRET_KEY must be set in production. "
            "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
        )
    _env_secret = secrets.token_urlsafe(32)
    _logger.warning(
        "AUTH_SECRET_KEY not set — using ephemeral key. "
        "Sessions will NOT survive restarts. Set AUTH_SECRET_KEY for persistence."
    )

SECRET_KEY = _env_secret
ALGORITHM = "HS256"

# Session timeout configuration (configurable via env vars)
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
SESSION_IDLE_TIMEOUT_MINUTES = int(os.getenv("SESSION_IDLE_TIMEOUT_MINUTES", "60"))

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


# ──────────────────────────────────────────────────────────────
# JWT Token Creation & Verification (with kid-based key rotation)
# ──────────────────────────────────────────────────────────────
# _active_kid / _active_secret are set by initialize_key_registry()
# when the async registry bootstraps. Until then, the module-level
# SECRET_KEY is used (backward-compatible, zero-downtime).
# ──────────────────────────────────────────────────────────────

_active_kid: Optional[str] = None
_active_secret: Optional[str] = None
_verification_keys: dict[str, str] = {}  # kid -> secret
_revoked_jtis: set[str] = set()  # in-memory fallback when Redis unavailable
_revocation_redis = None  # set by lifespan init


def _sync_keys_from_registry(signing_key, verification_keys) -> None:
    """Cache registry keys into module-level state for sync access.

    Called from the async initialization path so that the sync
    create_access_token / decode_access_token functions have
    up-to-date keys without awaiting Redis on every call.
    """
    global _active_kid, _active_secret, _verification_keys
    _active_kid = signing_key.kid
    _active_secret = signing_key.secret
    _verification_keys = {k.kid: k.secret for k in verification_keys}


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    # Ensure every token carries a jti we can revoke individually. Callers may
    # still pass a pre-allocated jti (e.g. elevation tokens that must be stored
    # in Redis at mint-time); we only generate one if the caller did not.
    if "jti" not in to_encode:
        to_encode["jti"] = str(uuid.uuid4())
    to_encode["exp"] = expire

    # Use registry key if available, otherwise fall back to static SECRET_KEY
    signing_secret = _active_secret or SECRET_KEY
    kid = _active_kid  # None until registry initializes (legacy tokens have no kid)

    headers = {}
    if kid:
        headers["kid"] = kid

    encoded_jwt = jwt.encode(
        to_encode,
        signing_secret,
        algorithm=ALGORITHM,
        headers=headers if headers else None,
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    # Read the unverified header to get kid (if present)
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.exceptions.DecodeError:
        # Malformed token — let jwt.decode raise the proper error
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

    kid = unverified_header.get("kid")

    if kid and _verification_keys:
        # New-style token: look up the specific key by kid
        key_secret = _verification_keys.get(kid)
        if key_secret:
            payload = jwt.decode(token, key_secret, algorithms=[ALGORITHM])
            return _check_revoked(payload)

        # kid present but not in our registry — key may have expired
        _logger.warning("jwt_unknown_kid: %s", kid)
        raise jwt.exceptions.InvalidSignatureError(
            f"Token signed with unknown or expired key: {kid}"
        )

    # Legacy token (no kid) or registry not yet initialized:
    # Try all verification keys, then fall back to static SECRET_KEY
    if _verification_keys:
        for vk_secret in _verification_keys.values():
            try:
                payload = jwt.decode(token, vk_secret, algorithms=[ALGORITHM])
                return _check_revoked(payload)
            except jwt.exceptions.InvalidSignatureError:
                continue

    # Final fallback — static env var key
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return _check_revoked(payload)


def _check_revoked(payload: dict) -> dict:
    """Raise if the token's jti has been revoked. Returns payload if ok."""
    jti = payload.get("jti")
    if not jti:
        return payload  # legacy token without jti — cannot be individually revoked

    # Check in-memory set first (fast path)
    if jti in _revoked_jtis:
        raise jwt.exceptions.InvalidTokenError("Token has been revoked")

    # Check Redis if available (shared across workers)
    if _revocation_redis:
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context but this is a sync function.
                # The Redis check will be handled by the async revocation
                # path in dependencies.py. The in-memory set is the sync guard.
                pass
            else:
                if loop.run_until_complete(_revocation_redis.sismember("regengine:jwt:revoked", jti)):
                    _revoked_jtis.add(jti)  # cache locally
                    raise jwt.exceptions.InvalidTokenError("Token has been revoked")
        except RuntimeError:
            pass  # no event loop — rely on in-memory set
    return payload


async def check_revoked_async(jti: str) -> bool:
    """Async revocation check — called from auth dependencies."""
    if jti in _revoked_jtis:
        return True
    if _revocation_redis:
        try:
            if await _revocation_redis.sismember("regengine:jwt:revoked", jti):
                _revoked_jtis.add(jti)
                return True
        except Exception:
            pass
    return False


async def revoke_token(jti: str, ttl_seconds: Optional[int] = None) -> None:
    """Revoke a token by its jti. TTL defaults to ACCESS_TOKEN_EXPIRE_MINUTES."""
    if ttl_seconds is None:
        ttl_seconds = ACCESS_TOKEN_EXPIRE_MINUTES * 60

    _revoked_jtis.add(jti)
    _logger.warning("jwt_token_revoked: jti=%s", jti)

    if _revocation_redis:
        try:
            await _revocation_redis.sadd("regengine:jwt:revoked", jti)
            await _revocation_redis.expire("regengine:jwt:revoked", ttl_seconds + 300)
        except Exception as exc:
            _logger.warning("jwt_revoke_redis_failed: %s", exc)


async def revoke_all_for_kid(kid: str) -> None:
    """Revoke an entire signing key — all tokens signed with it become invalid.

    This works by marking the key as invalid in the key registry, which
    causes decode_access_token to reject any token with that kid.
    If the revoked key was the only active key, a new one is auto-generated.
    """
    from shared.jwt_key_registry import get_key_registry
    registry = await get_key_registry()
    revoked = await registry.revoke_key(kid, revoked_by="admin-api")
    if revoked:
        # Refresh sync cache so this process picks up the change immediately
        signing = await registry.get_signing_key()
        verifying = await registry.get_verification_keys()
        _sync_keys_from_registry(signing, verifying)
        _logger.warning("jwt_kid_revoked: kid=%s", kid)
    else:
        _logger.warning("jwt_kid_revoke_not_found: kid=%s", kid)


async def revoke_all_jwt_keys() -> int:
    """Emergency: revoke ALL JWT keys and force re-authentication.

    Nuclear option — every existing session becomes invalid.
    A fresh signing key is auto-generated after revocation.
    Returns count of keys revoked.
    """
    from shared.jwt_key_registry import get_key_registry
    registry = await get_key_registry()
    count = await registry.revoke_all_keys(revoked_by="admin-api-emergency")
    # Refresh sync cache
    signing = await registry.get_signing_key()
    verifying = await registry.get_verification_keys()
    _sync_keys_from_registry(signing, verifying)
    _logger.warning("jwt_all_keys_revoked: count=%d", count)
    return count


def set_revocation_redis(redis_client) -> None:
    """Set the Redis client for revocation checks (called from lifespan)."""
    global _revocation_redis
    _revocation_redis = redis_client


def create_refresh_token() -> str:
    # Opaque token for database storage
    return secrets.token_urlsafe(64)

def hash_token(token: str) -> str:
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()
