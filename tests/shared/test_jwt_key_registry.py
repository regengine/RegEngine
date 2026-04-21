"""Tests for JWT key registry with rotation support.

Covers:
- Key generation utilities (kid format, secret strength)
- Registry initialization from legacy env var
- Signing key retrieval (exactly one active)
- Verification key retrieval (active + grace period)
- Key rotation lifecycle (new active, old demoted, expired cleaned)
- Legacy token fallback (no kid header)
- Token creation with kid, verification with kid
- Backward compatibility: tokens created before rotation still verify
- Grace period expiry
- Redis-down fallback to in-memory cache
"""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

from shared.jwt_key_registry import (
    DEFAULT_GRACE_PERIOD_SECONDS,
    REDIS_KEY,
    JWTKeyRegistry,
    SigningKey,
    generate_kid,
    generate_signing_secret,
)


# ── Utilities ────────────────────────────────────────────────────────


class TestGenerateKid:
    def test_format(self):
        kid = generate_kid()
        assert kid.startswith("re-")
        parts = kid.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 8  # YYYYMMDD
        assert len(parts[2]) == 8  # hex(4) = 8 chars

    def test_unique(self):
        kids = {generate_kid() for _ in range(50)}
        assert len(kids) == 50


class TestGenerateSigningSecret:
    def test_length(self):
        secret = generate_signing_secret()
        assert len(secret) >= 64

    def test_unique(self):
        secrets = {generate_signing_secret() for _ in range(20)}
        assert len(secrets) == 20


class TestSigningKey:
    def test_round_trip(self):
        key = SigningKey(kid="re-test-0001", secret="s3cret", algorithm="HS256")  # nosemgrep: python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret
        d = key.to_dict()
        restored = SigningKey.from_dict(d)
        assert restored.kid == key.kid
        assert restored.secret == key.secret
        assert restored.algorithm == key.algorithm
        assert restored.is_active == key.is_active
        assert restored.is_valid == key.is_valid


# ── FakeRedis for async tests ───────────────────────────────────────


class FakeAsyncRedis:
    """Minimal async Redis stub for testing."""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str):
        self.store[key] = value


# ── Registry Tests ───────────────────────────────────────────────────


class TestRegistryInitialize:
    @pytest.mark.asyncio
    async def test_bootstrap_from_legacy_env(self, monkeypatch):
        """First run imports AUTH_SECRET_KEY as legacy key."""
        monkeypatch.setenv("AUTH_SECRET_KEY", "test-legacy-secret-key-1234")
        redis = FakeAsyncRedis()
        registry = JWTKeyRegistry(redis_client=redis)

        await registry.initialize()

        keys = await registry.get_all_keys()
        assert len(keys) == 1
        assert keys[0].kid == "re-legacy-0001"
        assert keys[0].secret == "test-legacy-secret-key-1234"  # nosemgrep: python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret
        assert keys[0].is_active is True
        assert keys[0].is_valid is True

    @pytest.mark.asyncio
    async def test_no_secret_raises(self, monkeypatch):
        """Raises if no AUTH_SECRET_KEY or JWT_SECRET."""
        monkeypatch.delenv("AUTH_SECRET_KEY", raising=False)
        monkeypatch.delenv("JWT_SECRET", raising=False)
        redis = FakeAsyncRedis()
        registry = JWTKeyRegistry(redis_client=redis)

        with pytest.raises(RuntimeError, match="No JWT signing key"):
            await registry.initialize()

    @pytest.mark.asyncio
    async def test_idempotent(self, monkeypatch):
        """Calling initialize() twice doesn't duplicate keys."""
        monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret")
        redis = FakeAsyncRedis()
        registry = JWTKeyRegistry(redis_client=redis)

        await registry.initialize()
        await registry.initialize()

        keys = await registry.get_all_keys()
        assert len(keys) == 1

    @pytest.mark.asyncio
    async def test_existing_keys_preserved(self, monkeypatch):
        """If keys already exist in Redis, don't re-bootstrap."""
        monkeypatch.setenv("AUTH_SECRET_KEY", "should-not-be-used")
        redis = FakeAsyncRedis()

        existing = SigningKey(kid="re-existing-0001", secret="pre-existing")  # nosemgrep: python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret
        redis.store[REDIS_KEY] = json.dumps([existing.to_dict()])

        registry = JWTKeyRegistry(redis_client=redis)
        await registry.initialize()

        keys = await registry.get_all_keys()
        assert len(keys) == 1
        assert keys[0].kid == "re-existing-0001"


class TestGetSigningKey:
    @pytest.mark.asyncio
    async def test_returns_active_key(self, monkeypatch):
        monkeypatch.setenv("AUTH_SECRET_KEY", "fallback")
        redis = FakeAsyncRedis()
        registry = JWTKeyRegistry(redis_client=redis)
        await registry.initialize()

        key = await registry.get_signing_key()
        assert key.is_active is True
        assert key.is_valid is True

    @pytest.mark.asyncio
    async def test_env_fallback_when_redis_empty(self, monkeypatch):
        """Falls back to env var when Redis has no keys."""
        monkeypatch.setenv("AUTH_SECRET_KEY", "env-fallback-secret")
        registry = JWTKeyRegistry(redis_client=None)

        key = registry._env_fallback_key()
        assert key.kid == "re-legacy-0001"
        assert key.secret == "env-fallback-secret"  # nosemgrep: python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret


class TestGetVerificationKeys:
    @pytest.mark.asyncio
    async def test_includes_active_and_grace_period(self, monkeypatch):
        monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret")
        redis = FakeAsyncRedis()
        registry = JWTKeyRegistry(redis_client=redis)
        await registry.initialize()

        # Rotate — old key enters grace period
        await registry.rotate()

        keys = await registry.get_verification_keys()
        assert len(keys) == 2
        active = [k for k in keys if k.is_active]
        grace = [k for k in keys if not k.is_active and k.is_valid]
        assert len(active) == 1
        assert len(grace) == 1


class TestRotation:
    @pytest.mark.asyncio
    async def test_rotate_creates_new_active(self, monkeypatch):
        monkeypatch.setenv("AUTH_SECRET_KEY", "old-secret")
        redis = FakeAsyncRedis()
        registry = JWTKeyRegistry(redis_client=redis)
        await registry.initialize()

        new_key = await registry.rotate(rotated_by="test-admin")

        assert new_key.is_active is True
        assert new_key.is_valid is True
        assert new_key.kid != "re-legacy-0001"
        assert new_key.rotated_by == "test-admin"

    @pytest.mark.asyncio
    async def test_rotate_demotes_old_key(self, monkeypatch):
        monkeypatch.setenv("AUTH_SECRET_KEY", "old-secret")
        redis = FakeAsyncRedis()
        registry = JWTKeyRegistry(redis_client=redis)
        await registry.initialize()

        await registry.rotate()

        keys = await registry.get_all_keys()
        old = next(k for k in keys if k.kid == "re-legacy-0001")
        assert old.is_active is False
        assert old.is_valid is True
        assert old.expires_at is not None

    @pytest.mark.asyncio
    async def test_exactly_one_active_after_rotation(self, monkeypatch):
        monkeypatch.setenv("AUTH_SECRET_KEY", "secret")
        redis = FakeAsyncRedis()
        registry = JWTKeyRegistry(redis_client=redis)
        await registry.initialize()

        await registry.rotate()
        await registry.rotate()

        keys = await registry.get_all_keys()
        active = [k for k in keys if k.is_active]
        assert len(active) == 1

    @pytest.mark.asyncio
    async def test_grace_period_expiry(self, monkeypatch):
        monkeypatch.setenv("AUTH_SECRET_KEY", "secret")
        redis = FakeAsyncRedis()
        # Short grace period for testing
        registry = JWTKeyRegistry(redis_client=redis, grace_period_seconds=1)
        await registry.initialize()

        await registry.rotate()

        # Manually expire the old key
        keys = await registry.get_all_keys()
        old = next(k for k in keys if k.kid == "re-legacy-0001")
        old.expires_at = time.time() - 10  # expired 10s ago
        await registry._save_keys(keys)

        expired_count = await registry.cleanup_expired_keys()
        assert expired_count == 1

        verification_keys = await registry.get_verification_keys()
        valid_kids = [k.kid for k in verification_keys]
        assert "re-legacy-0001" not in valid_kids

    @pytest.mark.asyncio
    async def test_get_key_by_kid(self, monkeypatch):
        monkeypatch.setenv("AUTH_SECRET_KEY", "secret")
        redis = FakeAsyncRedis()
        registry = JWTKeyRegistry(redis_client=redis)
        await registry.initialize()

        key = await registry.get_key_by_kid("re-legacy-0001")
        assert key is not None
        assert key.kid == "re-legacy-0001"

        missing = await registry.get_key_by_kid("re-nonexistent-0001")
        assert missing is None


# ── Token Integration Tests ──────────────────────────────────────────


class TestTokenIntegration:
    """End-to-end: create token with kid → verify → rotate → verify old → expire."""

    @pytest.mark.asyncio
    async def test_token_with_kid_verifies(self, monkeypatch):
        """Token created with kid header verifies against matching key."""
        monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret-for-tokens")
        redis = FakeAsyncRedis()
        registry = JWTKeyRegistry(redis_client=redis)
        await registry.initialize()

        signing_key = await registry.get_signing_key()

        # Create token with kid
        token = jwt.encode(
            {"sub": "user-1", "tenant_id": "t-1"},
            signing_key.secret,
            algorithm=signing_key.algorithm,
            headers={"kid": signing_key.kid},
        )

        # Verify using kid lookup
        header = jwt.get_unverified_header(token)
        assert header["kid"] == signing_key.kid

        verification_keys = await registry.get_verification_keys()
        matching = next(k for k in verification_keys if k.kid == header["kid"])
        payload = jwt.decode(token, matching.secret, algorithms=[matching.algorithm])
        assert payload["sub"] == "user-1"

    @pytest.mark.asyncio
    async def test_old_token_survives_rotation(self, monkeypatch):
        """Token signed with old key still verifies during grace period."""
        monkeypatch.setenv("AUTH_SECRET_KEY", "pre-rotation-secret")
        redis = FakeAsyncRedis()
        registry = JWTKeyRegistry(redis_client=redis)
        await registry.initialize()

        old_key = await registry.get_signing_key()
        old_token = jwt.encode(
            {"sub": "user-1"},
            old_key.secret,
            algorithm="HS256",
            headers={"kid": old_key.kid},
        )

        # Rotate
        await registry.rotate()

        # Old token should still verify
        verification_keys = await registry.get_verification_keys()
        kid = jwt.get_unverified_header(old_token).get("kid")
        matching = next((k for k in verification_keys if k.kid == kid), None)
        assert matching is not None
        payload = jwt.decode(old_token, matching.secret, algorithms=["HS256"])
        assert payload["sub"] == "user-1"

    @pytest.mark.asyncio
    async def test_token_rejected_after_grace_period(self, monkeypatch):
        """Token signed with expired key is rejected."""
        monkeypatch.setenv("AUTH_SECRET_KEY", "will-expire-secret")
        redis = FakeAsyncRedis()
        registry = JWTKeyRegistry(redis_client=redis, grace_period_seconds=1)
        await registry.initialize()

        old_key = await registry.get_signing_key()
        old_token = jwt.encode(
            {"sub": "user-1"},
            old_key.secret,
            algorithm="HS256",
            headers={"kid": old_key.kid},
        )

        await registry.rotate()

        # Force-expire the old key
        keys = await registry.get_all_keys()
        for k in keys:
            if k.kid == old_key.kid:
                k.expires_at = time.time() - 10
        await registry._save_keys(keys)
        await registry.cleanup_expired_keys()

        # Old kid should no longer be in verification keys
        verification_keys = await registry.get_verification_keys()
        kid = jwt.get_unverified_header(old_token).get("kid")
        matching = next((k for k in verification_keys if k.kid == kid), None)
        assert matching is None

    @pytest.mark.asyncio
    async def test_legacy_token_no_kid_still_verifies(self, monkeypatch):
        """Token without kid (pre-rotation era) verifies via key iteration."""
        secret = "legacy-static-secret"  # nosemgrep: python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret
        monkeypatch.setenv("AUTH_SECRET_KEY", secret)
        redis = FakeAsyncRedis()
        registry = JWTKeyRegistry(redis_client=redis)
        await registry.initialize()

        # Create token WITHOUT kid (legacy style)
        legacy_token = jwt.encode(  # nosemgrep: python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret
            {"sub": "legacy-user"},
            secret,
            algorithm="HS256",
        )

        # Verify by trying all keys
        header = jwt.get_unverified_header(legacy_token)
        assert "kid" not in header

        verification_keys = await registry.get_verification_keys()
        decoded = None
        for k in verification_keys:
            try:
                decoded = jwt.decode(legacy_token, k.secret, algorithms=["HS256"])
                break
            except jwt.exceptions.InvalidSignatureError:
                continue

        assert decoded is not None
        assert decoded["sub"] == "legacy-user"

    @pytest.mark.asyncio
    async def test_unknown_kid_rejected(self, monkeypatch):
        """Token with unknown kid has no matching verification key."""
        monkeypatch.setenv("AUTH_SECRET_KEY", "known-secret")
        redis = FakeAsyncRedis()
        registry = JWTKeyRegistry(redis_client=redis)
        await registry.initialize()

        # Create token with a kid that doesn't exist in registry
        forged_token = jwt.encode(  # nosemgrep: python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret
            {"sub": "attacker"},
            "some-other-secret",
            algorithm="HS256",
            headers={"kid": "re-forged-9999"},
        )

        verification_keys = await registry.get_verification_keys()
        kid = jwt.get_unverified_header(forged_token).get("kid")
        matching = next((k for k in verification_keys if k.kid == kid), None)
        assert matching is None


# ── Redis Failure Resilience ─────────────────────────────────────────


class TestRedisFailure:
    @pytest.mark.asyncio
    async def test_falls_back_to_memory_cache(self, monkeypatch):
        """If Redis fails after initialization, uses in-memory cache."""
        monkeypatch.setenv("AUTH_SECRET_KEY", "cached-secret")
        redis = FakeAsyncRedis()
        registry = JWTKeyRegistry(redis_client=redis)
        await registry.initialize()

        # Verify keys are cached
        assert len(registry._fallback_keys) == 1

        # Simulate Redis failure
        registry._redis = None

        # Should still return from cache
        key = await registry.get_signing_key()
        assert key.kid == "re-legacy-0001"
