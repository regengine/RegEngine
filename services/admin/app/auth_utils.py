from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid
import jwt
from cachetools import TTLCache
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

# ──────────────────────────────────────────────────────────────
# JWT audience/issuer claims — separate token domains (#1060).
#
# Session tokens (admin API auth) and tool-access tokens (free
# compliance-tool gate) share neither their signing key nor their
# audience. Even if a key ever leaked, a tool-access token cannot
# be swapped in as a session token — decode_access_token verifies
# aud=SESSION_AUDIENCE and decode_tool_access_token verifies
# aud=TOOL_ACCESS_AUDIENCE.
# ──────────────────────────────────────────────────────────────
SESSION_AUDIENCE = "regengine-api"
SESSION_ISSUER = "regengine-admin"
TOOL_ACCESS_AUDIENCE = "regengine-tool-access"

# Session timeout configuration (configurable via env vars)
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
SESSION_IDLE_TIMEOUT_MINUTES = int(os.getenv("SESSION_IDLE_TIMEOUT_MINUTES", "60"))

# #1069 — reject JWTs without a ``jti`` claim. ``revoke_token()`` can only
# flag tokens by jti, so a pre-jti (legacy) token is un-revocable for its
# full natural TTL. Forcing re-auth on these tokens closes the gap. Set
# AUTH_ALLOW_LEGACY_JTI_FREE=true ONLY as a short-term rollback lever if
# production traffic still contains pre-jti tokens (all tokens minted by
# create_access_token now carry a jti, so the natural access-token TTL
# bounds the rollback window).
def _require_jti_default() -> bool:
    return os.getenv("AUTH_ALLOW_LEGACY_JTI_FREE", "").lower() not in ("true", "1", "yes")

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# ──────────────────────────────────────────────────────────────
# #1082 — constant-time login to close user-enumeration oracle.
#
# The /login handler used to short-circuit verify_password when
# the email was unknown, so an attacker could measure response
# latency to enumerate which emails are RegEngine customers.
# Argon2 verify is ~80-200 ms — trivially detectable as a gap.
#
# _DUMMY_ARGON2_HASH is a valid hash of a random string computed
# once at import time. verify_login() uses it when the user is
# absent so both branches do exactly one argon2 verify.
# ──────────────────────────────────────────────────────────────
_DUMMY_ARGON2_HASH = pwd_context.hash(secrets.token_urlsafe(32))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def verify_login(plain_password: str, user) -> bool:
    """Timing-safe login verification.

    Always performs one argon2 verify, even when ``user`` is None, so
    response latency does not depend on whether the email exists.
    Returns True iff ``user`` exists AND the password hash matches.

    Callers must still perform their own existence check for the
    authorization decision — this helper is only for the
    credential-verification timing envelope.
    """
    if user is None:
        # Run argon2 against the module-level dummy hash so this
        # branch takes the same wall time as the real one. Ignore
        # the result — the caller will see False because user is None.
        pwd_context.verify(plain_password, _DUMMY_ARGON2_HASH)
        return False
    password_hash = getattr(user, "password_hash", None)
    if not password_hash:
        # User row exists but has no hash (shouldn't happen; be
        # defensive and still pay the argon2 cost so this edge case
        # isn't its own oracle).
        pwd_context.verify(plain_password, _DUMMY_ARGON2_HASH)
        return False
    return pwd_context.verify(plain_password, password_hash)


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
# #1039 — bound the in-memory revocation set so long-running workers
# cannot leak memory when Redis is unavailable. TTL matches the token
# lifetime + 5-minute slack (same slack Redis key uses), so a revoked
# jti ages out exactly when the underlying JWT would no longer be
# accepted anyway. 50k entries caps peak memory at ~5MB per worker.
_revoked_jtis: TTLCache[str, bool] = TTLCache(
    maxsize=50_000,
    ttl=ACCESS_TOKEN_EXPIRE_MINUTES * 60 + 300,
)
_revocation_redis = None  # set by lifespan init


def _remember_revoked_jti(jti: str) -> None:
    """Cache a revoked JTI in whichever local container tests have installed."""
    if hasattr(_revoked_jtis, "__setitem__"):
        _revoked_jtis[jti] = True
        return
    add = getattr(_revoked_jtis, "add", None)
    if callable(add):
        add(jti)
        return
    raise TypeError("_revoked_jtis must support item assignment or add()")


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
    # Stamp the session domain so tool-access tokens (signed with a separate
    # secret and audience) cannot be accepted in place of a session — see #1060.
    to_encode.setdefault("aud", SESSION_AUDIENCE)
    to_encode.setdefault("iss", SESSION_ISSUER)

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


def _decode_session_strict(token: str, secret: str) -> dict:
    """Verify signature + aud/iss for a session token.

    During the transitional rollout, legacy tokens minted before #1060
    have no ``aud``/``iss`` claims. PyJWT raises ``MissingRequiredClaimError``
    when ``audience``/``issuer`` are requested on a token that lacks them.
    We retry without aud/iss verification in that case so existing sessions
    survive — signature is still checked either way. Once all legacy
    tokens expire (≤ ACCESS_TOKEN_EXPIRE_MINUTES), this fallback is dead
    code and can be removed.

    Tokens that carry the *wrong* aud (e.g. a tool-access token) raise
    ``InvalidAudienceError`` and are rejected — that is the bug fix.
    """
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            audience=SESSION_AUDIENCE,
            issuer=SESSION_ISSUER,
        )
    except jwt.exceptions.MissingRequiredClaimError:
        return jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            options={"verify_aud": False, "verify_iss": False},
        )


def decode_access_token(token: str) -> dict:
    # Read the unverified header to get kid (if present)
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.exceptions.DecodeError:
        # Malformed token — let jwt.decode raise the proper error
        return _decode_session_strict(token, SECRET_KEY)

    kid = unverified_header.get("kid")

    if kid and _verification_keys:
        # New-style token: look up the specific key by kid
        key_secret = _verification_keys.get(kid)
        if key_secret:
            payload = _decode_session_strict(token, key_secret)
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
                payload = _decode_session_strict(token, vk_secret)
                return _check_revoked(payload)
            except jwt.exceptions.InvalidSignatureError:
                continue

    # Final fallback — static env var key
    payload = _decode_session_strict(token, SECRET_KEY)
    return _check_revoked(payload)


def _check_revoked(payload: dict) -> dict:
    """Raise if the token's jti has been revoked. Returns payload if ok.

    NOTE (#1071): this function consults ONLY the in-process
    ``_revoked_jtis`` set — it does NOT contact Redis. The original
    implementation tried to call ``loop.run_until_complete`` on the
    async Redis client, which silently no-ops whenever an event loop
    is already running — i.e. every FastAPI request. The net effect
    was that a token revoked on worker A (written to Redis) was still
    accepted by worker B until B's in-memory set happened to pick it
    up, which only happens if B itself processed the revocation. That
    produced an exploitable window of up to the token's natural TTL on
    any worker that did not serve the logout.

    Cross-worker revocation is now the responsibility of
    :func:`check_revoked_async`, which every async token-validating
    dependency MUST call after decoding. See
    ``services.admin.app.dependencies.get_current_user`` for the
    required wiring. Removing the broken Redis branch here makes the
    contract explicit: sync callers get best-effort local-only
    revocation; any caller that needs cross-worker revocation must use
    the async path.
    """
    jti = payload.get("jti")
    if not jti:
        if _require_jti_default():
            raise jwt.exceptions.InvalidTokenError(
                "Token missing jti claim — please re-authenticate"
            )
        return payload  # rollback path — legacy tokens still pass through

    # In-process fast path. Populated by revoke_token() on this worker
    # and cached by check_revoked_async() whenever it observes a Redis
    # hit. Cross-worker revocations reach other workers via the async
    # path, not this sync call.
    if jti in _revoked_jtis:
        raise jwt.exceptions.InvalidTokenError("Token has been revoked")

    return payload


async def check_revoked_async(jti: str) -> bool:
    """Async revocation check — async token-validating dependencies MUST
    call this after :func:`decode_access_token` succeeds.

    Checks the in-memory set first (fast path, bypasses Redis on an
    already-known revocation) then falls through to Redis so a
    revocation written by any worker becomes visible to every other
    worker within the Redis round-trip — not capped by the token's
    natural TTL like the old sync implementation (#1071).
    """
    if not jti:
        return False
    if jti in _revoked_jtis:
        return True
    if _revocation_redis:
        try:
            if await _revocation_redis.sismember("regengine:jwt:revoked", jti):
                _remember_revoked_jti(jti)
                return True
        except Exception as exc:  # pragma: no cover — Redis best-effort
            # If Redis is transiently unreachable, fall back to
            # in-memory. The worker that issued the revocation still
            # blocks the token, and the logout audit event is still in
            # the DB. Better to be permissive on read than to fail
            # every request when Redis hiccups.
            _logger.warning("check_revoked_async_redis_error: %s", exc)
    return False


async def revoke_token(jti: str, ttl_seconds: Optional[int] = None) -> None:
    """Revoke a token by its jti. TTL defaults to ACCESS_TOKEN_EXPIRE_MINUTES."""
    if ttl_seconds is None:
        ttl_seconds = ACCESS_TOKEN_EXPIRE_MINUTES * 60

    _remember_revoked_jti(jti)
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
