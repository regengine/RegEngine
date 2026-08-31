"""Fail-closed runtime wiring for JWT signing and revocation state.

The consolidated and legacy admin entrypoints share this module so Redis
revocation checks cannot be accidentally omitted from one deployment shape.
Explicit local development/test may run without Redis; deployed staging and
production may not.
"""

from __future__ import annotations

import inspect
import os
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Optional

import structlog
from shared.env import is_production, requires_strict_auth_runtime

logger = structlog.get_logger("auth_runtime")

_TRUE_VALUES = {"1", "true", "yes", "on"}
_IN_MEMORY_BACKENDS = {"memory", "inmemory", "local"}
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 5
MIN_PRODUCTION_ACCESS_TOKEN_EXPIRE_MINUTES = 1
MAX_PRODUCTION_ACCESS_TOKEN_EXPIRE_MINUTES = 15


class AuthRuntimeConfigurationError(RuntimeError):
    """Raised when authentication settings violate a boot-time invariant."""


class AuthRuntimeInitializationError(RuntimeError):
    """Raised when a required production auth backend cannot be initialized."""


@dataclass(frozen=True)
class AuthRuntimeConfig:
    access_token_expire_minutes: int
    production: bool
    strict: bool
    redis_url: Optional[str]


@dataclass
class AuthRuntime:
    """Resources owned by one application lifespan."""

    redis_client: Any = None


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def _parse_access_token_expiry() -> int:
    raw = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES)).strip()
    try:
        minutes = int(raw)
    except (TypeError, ValueError) as exc:
        raise AuthRuntimeConfigurationError("ACCESS_TOKEN_EXPIRE_MINUTES must be an integer") from exc

    if minutes <= 0:
        raise AuthRuntimeConfigurationError("ACCESS_TOKEN_EXPIRE_MINUTES must be greater than zero")
    return minutes


def load_auth_runtime_config() -> AuthRuntimeConfig:
    """Load and validate auth settings without opening network connections."""

    production = is_production()
    strict = requires_strict_auth_runtime()
    access_token_expire_minutes = _parse_access_token_expiry()

    if strict and not (
        MIN_PRODUCTION_ACCESS_TOKEN_EXPIRE_MINUTES
        <= access_token_expire_minutes
        <= MAX_PRODUCTION_ACCESS_TOKEN_EXPIRE_MINUTES
    ):
        raise AuthRuntimeConfigurationError("Strict ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 15")

    if strict and _enabled("AUTH_ALLOW_LEGACY_JTI_FREE"):
        raise AuthRuntimeConfigurationError("AUTH_ALLOW_LEGACY_JTI_FREE is forbidden in strict auth environments")

    session_backend = os.getenv("SESSION_STORE_BACKEND", "").strip().lower()
    if strict and (session_backend in _IN_MEMORY_BACKENDS or _enabled("ALLOW_INMEMORY_SESSION_STORE")):
        raise AuthRuntimeConfigurationError("In-memory session storage is forbidden in strict auth environments")

    redis_url = os.getenv("REDIS_URL", "").strip() or None
    if strict and redis_url is None:
        raise AuthRuntimeConfigurationError("REDIS_URL is required for strict authentication")

    return AuthRuntimeConfig(
        access_token_expire_minutes=access_token_expire_minutes,
        production=production,
        strict=strict,
        redis_url=redis_url,
    )


def get_access_token_expire_minutes() -> int:
    """Return the centrally validated access-token lifetime."""

    return load_auth_runtime_config().access_token_expire_minutes


def validate_access_token_expiry_delta(expires_delta: timedelta) -> None:
    """Validate a caller-supplied access-token lifetime.

    Custom lifetimes must not bypass the same production bounds enforced for
    ``ACCESS_TOKEN_EXPIRE_MINUTES``.
    """

    lifetime_seconds = expires_delta.total_seconds()
    if lifetime_seconds <= 0:
        raise AuthRuntimeConfigurationError("Access-token expiry must be greater than zero")
    if requires_strict_auth_runtime() and not (60 <= lifetime_seconds <= 15 * 60):
        raise AuthRuntimeConfigurationError("Strict access-token expiry must be between 1 and 15 minutes")


async def _close_client(client: Any) -> None:
    close = getattr(client, "aclose", None) or getattr(client, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


async def initialize_auth_runtime() -> AuthRuntime:
    """Initialize shared JWT key and revocation state for an app lifespan.

    Strict runtimes require a reachable Redis backend. Explicit local
    development/test keeps the static-key/local-revocation fallback when
    Redis is absent or unavailable.
    """

    config = load_auth_runtime_config()
    redis_client = None

    if config.redis_url:
        try:
            import redis.asyncio as aioredis

            redis_client = aioredis.from_url(config.redis_url, decode_responses=True)
            await redis_client.ping()
        except Exception as exc:
            if redis_client is not None:
                await _close_client(redis_client)
            redis_client = None
            if config.strict:
                raise AuthRuntimeInitializationError("Strict authentication Redis is unavailable") from exc
            logger.warning("auth_runtime_redis_unavailable", error_type=type(exc).__name__)

    try:
        # Shared-key selection is part of the strict boot contract too. This
        # constructs the database-backed store without issuing or logging any
        # credential and prevents deployed staging from silently using the
        # process-local API-key store.
        if config.strict:
            from shared.api_key_store import DatabaseAPIKeyStore
            from shared.auth import get_key_store

            if not isinstance(get_key_store(), DatabaseAPIKeyStore):
                raise AuthRuntimeInitializationError("Strict authentication requires the database API-key store")

        from shared.jwt_key_registry import JWTKeyRegistry, set_key_registry

        from .auth_utils import _sync_keys_from_registry, set_revocation_redis

        registry = JWTKeyRegistry(redis_client=redis_client, strict=config.strict)
        await registry.initialize()
        signing_key, verification_keys = await registry.get_key_snapshot()
        await registry.cleanup_expired_keys()

        set_key_registry(registry)
        _sync_keys_from_registry(signing_key, verification_keys)
        set_revocation_redis(redis_client)
    except Exception as exc:
        if redis_client is not None:
            await _close_client(redis_client)
        from shared.jwt_key_registry import set_key_registry

        from .auth_utils import set_revocation_redis

        set_revocation_redis(None)
        set_key_registry(None)
        if config.strict:
            raise AuthRuntimeInitializationError("Strict JWT key registry initialization failed") from exc
        logger.warning("jwt_key_registry_init_failed", error_type=type(exc).__name__)
        return AuthRuntime()

    logger.info(
        "auth_runtime_ready",
        redis_backed=redis_client is not None,
        active_kid=signing_key.kid,
    )
    return AuthRuntime(redis_client=redis_client)


async def shutdown_auth_runtime(runtime: Optional[AuthRuntime]) -> None:
    """Detach and close resources created by :func:`initialize_auth_runtime`."""

    from shared.jwt_key_registry import set_key_registry

    from .auth_utils import set_revocation_redis

    set_revocation_redis(None)
    set_key_registry(None)
    if runtime is not None and runtime.redis_client is not None:
        await _close_client(runtime.redis_client)
