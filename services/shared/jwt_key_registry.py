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

import asyncio
import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Optional, TypeVar

import structlog

logger = structlog.get_logger("jwt-key-registry")

# Redis key for the key registry
REDIS_KEY = "regengine:jwt:keys"
CAS_MAX_ATTEMPTS = 16
_CAS_REPLACE_SCRIPT = """
local current = redis.call('GET', KEYS[1])
local expected_present = ARGV[1]
local expected = ARGV[2]

if expected_present == '0' then
    if current then
        return 0
    end
else
    if (not current) or current ~= expected then
        return 0
    end
end

redis.call('SET', KEYS[1], ARGV[3])
return 1
"""

# Grace period: old keys remain valid for verification for 7 days after rotation
DEFAULT_GRACE_PERIOD_SECONDS = 86400 * 7  # 7 days


class JWTKeyRegistryBackendUnavailable(RuntimeError):
    """Raised when a strict registry cannot reach durable Redis state."""


_MutationResult = TypeVar("_MutationResult")


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
        strict: bool = False,
    ):
        self._redis = redis_client
        self._grace_period = grace_period_seconds
        self._strict = strict
        # In-memory cache for when Redis is unavailable
        self._fallback_keys: list[SigningKey] = []
        self._initialized = False
        self._local_mutation_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Bootstrap the key registry.

        If no keys exist in Redis, imports the legacy AUTH_SECRET_KEY env var
        as the first key so existing sessions continue to work.
        """
        if self._initialized:
            return

        def bootstrap(keys: list[SigningKey]) -> tuple[SigningKey | None, bool]:
            if not keys:
                legacy_secret = os.environ.get("AUTH_SECRET_KEY") or os.environ.get("JWT_SECRET")
                if not legacy_secret:
                    raise RuntimeError("No JWT signing key configured. Set AUTH_SECRET_KEY env var.")

                legacy_key = SigningKey(
                    kid="re-legacy-0001",
                    secret=legacy_secret,
                    algorithm="HS256",
                    created_at=time.time(),
                    expires_at=None,
                    is_active=True,
                    is_valid=True,
                )
                keys.append(legacy_key)
                return legacy_key, True
            return None, False

        # Bootstrap is a read/modify/write operation too. The compare-and-set
        # makes concurrent replica startup safe without a crash-persistent
        # mutex: a process that dies before the atomic script leaves no lock,
        # and a stale snapshot simply loses the CAS and is recomputed.
        legacy_key = await self._mutate_keys(bootstrap)
        if legacy_key is not None:
            logger.info("jwt_key_registry_initialized", kid=legacy_key.kid, source="legacy_env_var")

        self._initialized = True

    async def get_signing_key(self) -> SigningKey:
        """Get the current active signing key (exactly one)."""
        signing_key, _verification_keys = await self.get_key_snapshot()
        return signing_key

    async def get_key_snapshot(self) -> tuple[SigningKey, list[SigningKey]]:
        """Load one consistent signing/verification snapshot from storage."""

        keys = await self._load_keys()
        active = [k for k in keys if k.is_active and k.is_valid]
        valid = [k for k in keys if k.is_valid]

        if not active:
            if self._strict:
                raise JWTKeyRegistryBackendUnavailable("JWT key registry has no active signing key")
            fallback = self._env_fallback_key()
            return fallback, valid or [fallback]

        if len(active) > 1:
            logger.warning(
                "jwt_multiple_active_keys",
                count=len(active),
                kids=[k.kid for k in active],
            )
            # Use the most recently created
            active.sort(key=lambda k: k.created_at, reverse=True)

        return active[0], valid

    async def get_verification_keys(self) -> list[SigningKey]:
        """Get all keys valid for token verification (active + grace period)."""
        _signing_key, verification_keys = await self.get_key_snapshot()
        return verification_keys

    async def rotate(self, rotated_by: str = "admin") -> SigningKey:
        """Rotate to a new signing key.

        1. Generate a new active key.
        2. Demote the old active key (grace period for verification).
        3. Expire any keys past their grace period.
        """

        def rotate_keys(keys: list[SigningKey]) -> tuple[tuple[SigningKey, list[str], list[str]], bool]:
            now = time.time()
            expired_kids = [key.kid for key in keys if key.expires_at and key.expires_at < now and key.is_valid]
            demoted_kids = [key.kid for key in keys if key.is_active]
            new_key = self._append_rotated_key(keys, rotated_by=rotated_by)
            return (new_key, expired_kids, demoted_kids), True

        new_key, expired_kids, demoted_kids = await self._mutate_keys(rotate_keys)
        for expired_kid in expired_kids:
            logger.info("jwt_key_expired", kid=expired_kid)
        for demoted_kid in demoted_kids:
            logger.info(
                "jwt_key_demoted",
                kid=demoted_kid,
                grace_period_days=self._grace_period // 86400,
            )
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

        def revoke(keys: list[SigningKey]) -> tuple[tuple[bool, SigningKey | None, bool], bool]:
            found = False
            replacement: SigningKey | None = None
            newly_revoked = False

            for key in keys:
                if key.kid != kid:
                    continue
                found = True
                if key.is_valid:
                    key.is_valid = False
                    key.is_active = False
                    key.expires_at = 0  # Expired in the past
                    newly_revoked = True
                break

            if found:
                # Persist the invalidation and any required replacement as one
                # registry value. There is never a durable no-active-key gap.
                active = [key for key in keys if key.is_active and key.is_valid]
                if not active:
                    replacement = self._append_rotated_key(
                        keys,
                        rotated_by=f"auto-after-revoke-{revoked_by}",
                    )
            return (found, replacement, newly_revoked), found

        found, replacement, newly_revoked = await self._mutate_keys(revoke)

        if newly_revoked:
            logger.warning(
                "jwt_key_emergency_revoked",
                kid=kid,
                revoked_by=revoked_by,
            )

        if replacement is not None:
            logger.warning("jwt_no_active_keys_after_revocation_auto_rotating")
            logger.info(
                "jwt_key_rotated",
                new_kid=replacement.kid,
                rotated_by=replacement.rotated_by,
            )

        return found

    async def revoke_all_keys(self, revoked_by: str = "admin") -> int:
        """Emergency: invalidate ALL keys and generate a fresh one.

        Nuclear option — every existing session/token becomes invalid.
        Returns count of keys revoked.
        """

        def revoke_all(keys: list[SigningKey]) -> tuple[tuple[int, SigningKey], bool]:
            count = 0

            for key in keys:
                if key.is_valid:
                    key.is_valid = False
                    key.is_active = False
                    key.expires_at = 0
                    count += 1

            replacement = self._append_rotated_key(
                keys,
                rotated_by=f"revoke-all-{revoked_by}",
            )
            return (count, replacement), True

        count, replacement = await self._mutate_keys(revoke_all)

        logger.warning(
            "jwt_all_keys_revoked",
            keys_revoked=count,
            revoked_by=revoked_by,
            new_kid=replacement.kid,
        )
        return count

    async def cleanup_expired_keys(self) -> int:
        """Invalidate keys past their grace period. Returns count of expired keys."""

        def cleanup(keys: list[SigningKey]) -> tuple[tuple[int, list[str]], bool]:
            now = time.time()
            expired_kids: list[str] = []

            for key in keys:
                if key.expires_at and key.expires_at < now and key.is_valid:
                    key.is_valid = False
                    expired_kids.append(key.kid)

            return (len(expired_kids), expired_kids), bool(expired_kids)

        expired_count, expired_kids = await self._mutate_keys(cleanup)
        for expired_kid in expired_kids:
            logger.info("jwt_key_expired", kid=expired_kid)
        return expired_count

    def _append_rotated_key(self, keys: list[SigningKey], *, rotated_by: str) -> SigningKey:
        """Mutate one candidate registry snapshot to add its next active key."""

        now = time.time()
        for key in keys:
            if key.expires_at and key.expires_at < now and key.is_valid:
                key.is_valid = False

        for key in keys:
            if key.is_active:
                key.is_active = False
                key.expires_at = now + self._grace_period

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
        return new_key

    async def _mutate_keys(
        self,
        mutation: Callable[[list[SigningKey]], tuple[_MutationResult, bool]],
    ) -> _MutationResult:
        """Apply one optimistic, crash-safe registry mutation.

        Redis stores the registry as one JSON value. Each writer reads that
        value, computes a replacement, and atomically swaps it only when the
        value is unchanged. A conflicting writer causes a bounded retry with a
        fresh snapshot. There is no lease to expire and no owner lock that can
        survive a crashed process, while a stale writer can never overwrite a
        newer revoke/rotate result.
        """

        if self._redis is None:
            if self._strict:
                raise JWTKeyRegistryBackendUnavailable("JWT key registry Redis is not initialized")
            async with self._local_mutation_lock:
                keys = await self._load_keys()
                result, changed = mutation(keys)
                if changed:
                    await self._save_keys(keys)
                return result

        for _attempt in range(CAS_MAX_ATTEMPTS):
            try:
                raw = await self._redis.get(REDIS_KEY)
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                keys = [SigningKey.from_dict(item) for item in json.loads(raw)] if raw else []
            except Exception as exc:
                logger.warning(
                    "jwt_key_registry_cas_read_failed",
                    error_type=type(exc).__name__,
                )
                raise JWTKeyRegistryBackendUnavailable("JWT key registry mutation read failed") from exc

            # Configuration and mutation-policy errors (for example, a missing
            # bootstrap signing secret) are not Redis failures. Preserve their
            # original type and message for callers.
            result, changed = mutation(keys)
            if not changed:
                return result

            replacement = json.dumps([key.to_dict() for key in keys])
            try:
                committed = await self._redis.eval(
                    _CAS_REPLACE_SCRIPT,
                    1,
                    REDIS_KEY,
                    "1" if raw is not None else "0",
                    raw or "",
                    replacement,
                )
            except Exception as exc:
                logger.warning(
                    "jwt_key_registry_cas_write_failed",
                    error_type=type(exc).__name__,
                )
                raise JWTKeyRegistryBackendUnavailable("JWT key registry mutation write failed") from exc

            try:
                commit_status = int(committed)
            except (TypeError, ValueError) as exc:
                raise JWTKeyRegistryBackendUnavailable("JWT key registry mutation acknowledgement was invalid") from exc

            if commit_status == 1:
                self._fallback_keys = list(keys)
                return result
            if commit_status != 0:
                raise JWTKeyRegistryBackendUnavailable("JWT key registry mutation acknowledgement was invalid")

            # Another replica committed first. Yield so it can finish, then
            # recompute this mutation from the new authoritative value.
            await asyncio.sleep(0)

        raise JWTKeyRegistryBackendUnavailable("JWT key registry mutation contention exceeded retry limit")

    # -- Storage layer --

    async def _load_keys(self) -> list[SigningKey]:
        """Load keys from Redis, falling back to in-memory cache."""
        if self._redis is not None:
            try:
                raw = await self._redis.get(REDIS_KEY)
                if raw:
                    data = json.loads(raw)
                    keys = [SigningKey.from_dict(k) for k in data]
                    self._fallback_keys = keys  # update cache
                    return keys
            except Exception as exc:
                logger.warning("jwt_key_registry_redis_read_failed", error_type=type(exc).__name__)
                if self._strict:
                    raise JWTKeyRegistryBackendUnavailable("JWT key registry read failed") from exc
                from shared.redis_health import report_redis_fallback

                report_redis_fallback("jwt_key_registry", type(exc).__name__)
        elif self._strict:
            raise JWTKeyRegistryBackendUnavailable("JWT key registry Redis is not initialized")

        # Redis unavailable — use in-memory cache
        if self._fallback_keys:
            return list(self._fallback_keys)

        return []

    async def _save_keys(self, keys: list[SigningKey]) -> None:
        """Save keys to Redis and update in-memory cache."""
        if self._redis is not None:
            try:
                data = json.dumps([k.to_dict() for k in keys])
                persisted = await self._redis.set(REDIS_KEY, data)
                if self._strict and not persisted:
                    raise RuntimeError("Redis did not acknowledge JWT key registry write")
            except Exception as exc:
                logger.warning("jwt_key_registry_redis_write_failed", error_type=type(exc).__name__)
                if self._strict:
                    raise JWTKeyRegistryBackendUnavailable("JWT key registry write failed") from exc
            else:
                self._fallback_keys = list(keys)
                return
        elif self._strict:
            raise JWTKeyRegistryBackendUnavailable("JWT key registry Redis is not initialized")

        self._fallback_keys = list(keys)

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
        from shared.env import requires_strict_auth_runtime

        _registry = JWTKeyRegistry(strict=requires_strict_auth_runtime())
    if not _registry._initialized:
        await _registry.initialize()
    return _registry


def set_key_registry(registry: Optional[JWTKeyRegistry]) -> None:
    """Override the global registry (for testing)."""
    global _registry
    _registry = registry
