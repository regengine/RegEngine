"""JWT signing key registry with rotation support.

Manages multiple JWT signing keys to enable zero-downtime key rotation.
Keys are stored in Redis with env-var fallback for durability.

Key lifecycle:
  1. ACTIVE + VALID   — used to sign new tokens AND verify existing ones
  2. INACTIVE + VALID  — grace period; verifies old tokens but doesn't sign new ones
  3. INACTIVE + INVALID — fully retired; tokens signed with this key are rejected

Usage:
    registry = JWTKeyRegistry(redis_client)
    await registry.initialize()              # bootstrap from AUTH_SECRET_KEY
    key = await registry.get_signing_key()   # get current active key
    keys = await registry.get_verification_keys()  # all keys valid for verify
    new_key = await registry.rotate()        # rotate to a new key
"""

from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from typing import Optional

import structlog

logger = structlog.get_logger("jwt-key-registry")

# Redis key for the key registry
REDIS_KEY = "regengine:jwt:keys"

# Grace period: old keys remain valid for verification for 7 days after rotation
DEFAULT_GRACE_PERIOD_SECONDS = 86400 * 7  # 7 days


def generate_kid() -> str:
    """Generate a unique key ID. Format: re-YYYYMMDD-XXXX."""
    date_part = time.strftime("%Y%m%d")
    random_part = secrets.token_hex(4)
    return f"re-{date_part}-{random_part}"


def generate_signing_secret() -> str:
    """Generate a cryptographically secure 512-bit signing secret."""
    return secrets.token_urlsafe(64)


@dataclass
class SigningKey:
    """A JWT signing key with metadata."""

    kid: str
    secret: str
    algorithm: str = "HS256"
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    is_active: bool = True
    is_valid: bool = True
    rotated_by: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> SigningKey:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class JWTKeyRegistry:
    """Manages JWT signing keys with rotation support.

    Primary store: Redis (fast, shared across workers).
    Fallback: AUTH_SECRET_KEY env var (single static key, no rotation).
    """

    def __init__(
        self,
        redis_client=None,
        grace_period_seconds: int = DEFAULT_GRACE_PERIOD_SECONDS,
    ):
        self._redis = redis_client
        self._grace_period = grace_period_seconds
        # In-memory cache for when Redis is unavailable
        self._fallback_keys: list[SigningKey] = []
        self._initialized = False

    async def initialize(self) -> None:
        """Bootstrap the key registry.

        If no keys exist in Redis, imports the legacy AUTH_SECRET_KEY env var
        as the first key so existing sessions continue to work.
        """
        if self._initialized:
            return

        keys = await self._load_keys()
        if not keys:
            legacy_secret = os.environ.get("AUTH_SECRET_KEY") or os.environ.get("JWT_SECRET")
            if not legacy_secret:
                raise RuntimeError(
                    "No JWT signing key configured. Set AUTH_SECRET_KEY env var."
                )

            legacy_key = SigningKey(
                kid="re-legacy-0001",
                secret=legacy_secret,
                algorithm="HS256",
                created_at=time.time(),
                expires_at=None,
                is_active=True,
                is_valid=True,
            )
            await self._save_keys([legacy_key])
            logger.info("jwt_key_registry_initialized", kid=legacy_key.kid, source="legacy_env_var")

        self._initialized = True

    async def get_signing_key(self) -> SigningKey:
        """Get the current active signing key (exactly one)."""
        keys = await self._load_keys()
        active = [k for k in keys if k.is_active and k.is_valid]

        if not active:
            # Fallback: use env var directly
            return self._env_fallback_key()

        if len(active) > 1:
            logger.warning(
                "jwt_multiple_active_keys",
                count=len(active),
                kids=[k.kid for k in active],
            )
            # Use the most recently created
            active.sort(key=lambda k: k.created_at, reverse=True)

        return active[0]

    async def get_verification_keys(self) -> list[SigningKey]:
        """Get all keys valid for token verification (active + grace period)."""
        keys = await self._load_keys()
        valid = [k for k in keys if k.is_valid]

        if not valid:
            return [self._env_fallback_key()]

        return valid

    async def rotate(self, rotated_by: str = "admin") -> SigningKey:
        """Rotate to a new signing key.

        1. Generate a new active key.
        2. Demote the old active key (grace period for verification).
        3. Expire any keys past their grace period.
        """
        keys = await self._load_keys()

        # Expire keys past grace period
        now = time.time()
        for key in keys:
            if key.expires_at and key.expires_at < now and key.is_valid:
                key.is_valid = False
                logger.info("jwt_key_expired", kid=key.kid)

        # Demote current active key(s)
        for key in keys:
            if key.is_active:
                key.is_active = False
                key.expires_at = now + self._grace_period
                logger.info(
                    "jwt_key_demoted",
                    kid=key.kid,
                    grace_period_days=self._grace_period // 86400,
                )

        # Create new active key
        new_key = SigningKey(
            kid=generate_kid(),
            secret=generate_signing_secret(),
            algorithm="HS256",
            created_at=now,
            expires_at=None,
            is_active=True,
            is_valid=True,
            rotated_by=rotated_by,
        )
        keys.append(new_key)

        await self._save_keys(keys)
        logger.info("jwt_key_rotated", new_kid=new_key.kid, rotated_by=rotated_by)

        return new_key

    async def get_all_keys(self) -> list[SigningKey]:
        """Get all keys (for admin listing). Secrets are NOT included."""
        return await self._load_keys()

    async def get_key_by_kid(self, kid: str) -> Optional[SigningKey]:
        """Look up a specific key by its kid."""
        keys = await self._load_keys()
        for key in keys:
            if key.kid == kid:
                return key
        return None

    async def revoke_key(self, kid: str, revoked_by: str = "admin") -> bool:
        """Emergency: immediately invalidate a specific key by kid.

        All tokens signed with this key will be rejected on the next
        verification attempt. Use when a key is compromised.

        Returns True if the key was found and revoked, False if not found.
        """
        keys = await self._load_keys()
        found = False

        for key in keys:
            if key.kid == kid and key.is_valid:
                key.is_valid = False
                key.is_active = False
                key.expires_at = 0  # Expired in the past
                found = True
                logger.warning(
                    "jwt_key_emergency_revoked",
                    kid=kid,
                    revoked_by=revoked_by,
                )
                break

        if found:
            await self._save_keys(keys)

            # If we revoked the only active key, auto-generate a replacement
            active = [k for k in keys if k.is_active and k.is_valid]
            if not active:
                logger.warning("jwt_no_active_keys_after_revocation_auto_rotating")
                await self.rotate(rotated_by=f"auto-after-revoke-{revoked_by}")

        return found

    async def revoke_all_keys(self, revoked_by: str = "admin") -> int:
        """Emergency: invalidate ALL keys and generate a fresh one.

        Nuclear option — every existing session/token becomes invalid.
        Returns count of keys revoked.
        """
        keys = await self._load_keys()
        count = 0

        for key in keys:
            if key.is_valid:
                key.is_valid = False
                key.is_active = False
                key.expires_at = 0
                count += 1

        await self._save_keys(keys)

        # Generate a fresh signing key
        await self.rotate(rotated_by=f"revoke-all-{revoked_by}")

        logger.warning(
            "jwt_all_keys_revoked",
            keys_revoked=count,
            revoked_by=revoked_by,
        )
        return count

    async def cleanup_expired_keys(self) -> int:
        """Invalidate keys past their grace period. Returns count of expired keys."""
        keys = await self._load_keys()
        now = time.time()
        expired_count = 0

        for key in keys:
            if key.expires_at and key.expires_at < now and key.is_valid:
                key.is_valid = False
                expired_count += 1
                logger.info("jwt_key_expired", kid=key.kid)

        if expired_count > 0:
            await self._save_keys(keys)

        return expired_count

    # -- Storage layer --

    async def _load_keys(self) -> list[SigningKey]:
        """Load keys from Redis, falling back to in-memory cache."""
        if self._redis:
            try:
                raw = await self._redis.get(REDIS_KEY)
                if raw:
                    data = json.loads(raw)
                    keys = [SigningKey.from_dict(k) for k in data]
                    self._fallback_keys = keys  # update cache
                    return keys
            except Exception as exc:
                logger.warning("jwt_key_registry_redis_read_failed", error=str(exc))
                from shared.redis_health import report_redis_fallback
                report_redis_fallback("jwt_key_registry", str(exc))

        # Redis unavailable — use in-memory cache
        if self._fallback_keys:
            return list(self._fallback_keys)

        return []

    async def _save_keys(self, keys: list[SigningKey]) -> None:
        """Save keys to Redis and update in-memory cache."""
        self._fallback_keys = list(keys)

        if self._redis:
            try:
                data = json.dumps([k.to_dict() for k in keys])
                await self._redis.set(REDIS_KEY, data)
            except Exception as exc:
                logger.warning("jwt_key_registry_redis_write_failed", error=str(exc))

    def _env_fallback_key(self) -> SigningKey:
        """Create a SigningKey from the legacy env var (fallback when Redis is empty/down)."""
        secret = os.environ.get("AUTH_SECRET_KEY") or os.environ.get("JWT_SECRET")
        if not secret:
            raise RuntimeError("No JWT signing key available — set AUTH_SECRET_KEY")

        return SigningKey(
            kid="re-legacy-0001",
            secret=secret,
            algorithm="HS256",
            created_at=0,
            expires_at=None,
            is_active=True,
            is_valid=True,
        )


# ---------------------------------------------------------------------------
# Module-level singleton (initialized lazily by auth_utils)
# ---------------------------------------------------------------------------
_registry: Optional[JWTKeyRegistry] = None


async def get_key_registry() -> JWTKeyRegistry:
    """Get the global key registry singleton.

    Call `initialize()` on first use. The registry requires an async Redis
    client; if none is available it works in env-var-only mode.
    """
    global _registry
    if _registry is None:
        _registry = JWTKeyRegistry()
    if not _registry._initialized:
        await _registry.initialize()
    return _registry


def set_key_registry(registry: JWTKeyRegistry) -> None:
    """Override the global registry (for testing)."""
    global _registry
    _registry = registry
