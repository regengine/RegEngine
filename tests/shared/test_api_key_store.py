"""
SEC-005: Tests for database-backed API key store.

These tests use SQLite in-memory for fast testing.
Production uses PostgreSQL.
"""

import asyncio
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)

# Test with SQLite for simplicity (aiosqlite driver)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


class TestAPIKeyModels:
    """Test Pydantic models for API keys."""

    def test_api_key_response_model(self):
        """APIKeyResponse should have all required fields."""
        from shared.api_key_store import APIKeyResponse

        response = APIKeyResponse(
            key_id="rge_test123",
            key_prefix="rge_test123",
            name="Test Key",
            tenant_id="00000000-0000-0000-0000-000000000000",
            billing_tier="DEVELOPER",
            allowed_jurisdictions=["US"],
            scopes=["read:regulations"],
            rate_limit_per_minute=60,
            rate_limit_per_hour=1000,
            rate_limit_per_day=10000,
            enabled=True,
            created_at=datetime.now(timezone.utc),
            expires_at=None,
            last_used_at=None,
            total_requests=0,
        )

        assert response.key_id == "rge_test123"
        assert response.tenant_id == "00000000-0000-0000-0000-000000000000"
        assert response.billing_tier == "DEVELOPER"
        assert "US" in response.allowed_jurisdictions
        assert response.enabled is True

    def test_api_key_create_response_includes_raw_key(self):
        """APIKeyCreateResponse should include raw_key field."""
        from shared.api_key_store import APIKeyCreateResponse

        response = APIKeyCreateResponse(
            key_id="rge_test123",
            key_prefix="rge_test123",
            name="Test Key",
            raw_key="rge_test123.abcdef123456",
            created_at=datetime.now(timezone.utc),
        )

        assert response.raw_key == "rge_test123.abcdef123456"

    def test_rate_limit_info_model(self):
        """RateLimitInfo should represent rate limit status."""
        from shared.api_key_store import RateLimitInfo

        info = RateLimitInfo(
            allowed=False,
            limit=60,
            remaining=0,
            reset_at=datetime.now(timezone.utc),
            retry_after=30,
        )

        assert info.allowed is False
        assert info.remaining == 0
        assert info.retry_after == 30


class TestKeyGeneration:
    """Test key generation utilities."""

    def test_generate_key_id_format(self):
        """Key IDs should have rge_ prefix."""
        from shared.api_key_store import DatabaseAPIKeyStore

        key_id = DatabaseAPIKeyStore._generate_key_id()
        assert key_id.startswith("rge_")
        assert len(key_id) > 10

    def test_generate_key_id_uniqueness(self):
        """Key IDs should be unique."""
        from shared.api_key_store import DatabaseAPIKeyStore

        key_ids = {DatabaseAPIKeyStore._generate_key_id() for _ in range(100)}
        assert len(key_ids) == 100  # All unique

    def test_generate_secret_length(self):
        """Secrets should be sufficiently long."""
        from shared.api_key_store import DatabaseAPIKeyStore

        secret = DatabaseAPIKeyStore._generate_secret()
        # Base64-encoded 32 bytes = 43 characters
        assert len(secret) >= 40

    def test_hash_key_deterministic(self):
        """Same key should produce same hash."""
        from shared.api_key_store import DatabaseAPIKeyStore

        raw_key = "rge_test123.abcdef"
        hash1 = DatabaseAPIKeyStore._hash_key(raw_key)
        hash2 = DatabaseAPIKeyStore._hash_key(raw_key)
        assert hash1 == hash2

    def test_hash_key_different_for_different_keys(self):
        """Different keys should produce different hashes."""
        from shared.api_key_store import DatabaseAPIKeyStore

        hash1 = DatabaseAPIKeyStore._hash_key("rge_key1.secret1")
        hash2 = DatabaseAPIKeyStore._hash_key("rge_key2.secret2")
        assert hash1 != hash2

    def test_hash_key_is_sha256(self):
        """Hash should be SHA-256 (64 hex chars)."""
        from shared.api_key_store import DatabaseAPIKeyStore

        key_hash = DatabaseAPIKeyStore._hash_key("rge_test.secret")
        assert len(key_hash) == 64
        assert all(c in "0123456789abcdef" for c in key_hash)

    def test_hash_key_uses_hmac_sha256_when_pepper_configured(self, monkeypatch):
        """Server-side pepper switches storage to HMAC-SHA256."""
        from shared.api_key_store import DatabaseAPIKeyStore

        raw_key = "rge_test.secret"
        monkeypatch.setenv("REGENGINE_API_KEY_HASH_PEPPER", "pepper-value")

        expected = hmac.new(
            b"pepper-value",
            raw_key.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        assert DatabaseAPIKeyStore._hash_key(raw_key) == expected
        assert DatabaseAPIKeyStore._hash_key(raw_key) != hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def test_hash_candidates_include_legacy_when_peppered(self, monkeypatch):
        """Validation can accept legacy rows long enough to migrate them."""
        from shared.api_key_store import api_key_hash_candidates, legacy_hash_api_key

        raw_key = "rge_test.secret"
        monkeypatch.setenv("REGENGINE_API_KEY_HASH_PEPPER", "pepper-value")

        candidates = api_key_hash_candidates(raw_key)

        assert len(candidates) == 2
        assert candidates[1] == legacy_hash_api_key(raw_key)
        assert candidates[0] != candidates[1]


class TestDatabaseAPIKeyStoreInit:
    """Test store initialization."""

    def test_init_with_custom_url(self):
        """Should accept custom database URL."""
        from shared.api_key_store import DatabaseAPIKeyStore

        store = DatabaseAPIKeyStore(database_url="postgresql+asyncpg://test:test@localhost/test")
        assert store._database_url == "postgresql+asyncpg://test:test@localhost/test"

    def test_init_with_env_var(self):
        """Should use DATABASE_URL env var if not provided."""
        import os

        from shared.api_key_store import DatabaseAPIKeyStore

        old_val = os.environ.get("DATABASE_URL")
        try:
            os.environ["DATABASE_URL"] = "postgresql+asyncpg://env:env@envhost/envdb"
            store = DatabaseAPIKeyStore()
            assert "envhost" in store._database_url
        finally:
            if old_val:
                os.environ["DATABASE_URL"] = old_val
            else:
                os.environ.pop("DATABASE_URL", None)


class TestDatabaseAPIKeyStoreCRUD:
    """Test CRUD operations with mocked database."""

    @pytest.fixture
    def mock_store(self):
        """Create a store with mocked database."""
        from shared.api_key_store import DatabaseAPIKeyStore

        store = DatabaseAPIKeyStore(database_url=TEST_DATABASE_URL)
        return store

    @pytest.mark.asyncio
    async def test_create_key_returns_raw_key(self, mock_store):
        """create_key should return a response with raw_key."""
        # Mock the session
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()

        with patch.object(mock_store, "_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            response = await mock_store.create_key(
                name="Test Production Key",
                tenant_id="00000000-0000-0000-0000-000000000000",
                billing_tier="ENTERPRISE",
            )

        assert response.raw_key is not None
        assert response.raw_key.startswith("rge_")
        assert "." in response.raw_key
        assert response.name == "Test Production Key"
        assert response.tenant_id == "00000000-0000-0000-0000-000000000000"
        assert response.billing_tier == "ENTERPRISE"

    @pytest.mark.asyncio
    async def test_create_key_default_jurisdictions(self, mock_store):
        """create_key should default to US jurisdiction."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()

        with patch.object(mock_store, "_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            response = await mock_store.create_key(name="Test Key")

        assert "US" in response.allowed_jurisdictions


class TestValidation:
    """Test API key validation."""

    @pytest.mark.asyncio
    async def test_validate_rejects_empty_key(self):
        """validate_key should reject empty strings."""
        from shared.api_key_store import DatabaseAPIKeyStore

        store = DatabaseAPIKeyStore(database_url=TEST_DATABASE_URL)
        result = await store.validate_key("")
        assert result is None

    @pytest.mark.asyncio
    async def test_validate_rejects_wrong_prefix(self):
        """validate_key should reject keys without rge_ prefix."""
        from shared.api_key_store import DatabaseAPIKeyStore

        store = DatabaseAPIKeyStore(database_url=TEST_DATABASE_URL)
        result = await store.validate_key("abc_wrongprefix.secret")
        assert result is None

    @pytest.mark.asyncio
    async def test_validate_rejects_no_separator(self):
        """validate_key should reject keys without . separator."""
        from shared.api_key_store import DatabaseAPIKeyStore

        store = DatabaseAPIKeyStore(database_url=TEST_DATABASE_URL)
        result = await store.validate_key("rge_noseparator")
        assert result is None

    @pytest.mark.asyncio
    async def test_runtime_validate_accepts_legacy_hash_without_rewriting_credential(self, monkeypatch):
        """Runtime validation accepts legacy SHA-256 without mutating key material."""
        from shared.api_key_store import (
            APIKeyModel,
            DatabaseAPIKeyStore,
            hash_api_key,
            legacy_hash_api_key,
        )

        raw_key = "rge_live_legacy.secret"
        key_id = raw_key.split(".", 1)[0]
        monkeypatch.setenv("REGENGINE_API_KEY_HASH_PEPPER", "pepper-value")

        model = APIKeyModel(
            key_id=key_id,
            key_hash=legacy_hash_api_key(raw_key),
            key_prefix=raw_key[:12],
            name="Legacy Key",
            tenant_id="00000000-0000-0000-0000-000000000000",
            allowed_jurisdictions=["US"],
            scopes=["read"],
            rate_limit_per_minute=60,
            rate_limit_per_hour=1000,
            rate_limit_per_day=10000,
            enabled=True,
            created_at=datetime.now(timezone.utc),
            total_requests=0,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=model)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()

        store = DatabaseAPIKeyStore(database_url=TEST_DATABASE_URL)
        with patch.object(store, "_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await store.validate_key(raw_key)

        assert result is not None
        assert result.key_id == key_id
        assert model.key_hash == legacy_hash_api_key(raw_key)
        assert model.key_hash != hash_api_key(raw_key)
        usage_updates = [
            call for call in mock_session.execute.call_args_list if call.args and "UPDATE api_keys" in str(call.args[0])
        ]
        assert len(usage_updates) == 1
        assert "key_hash" not in str(usage_updates[0].args[0])
        assert usage_updates[0].args[1]["delta"] == 1
        assert usage_updates[0].args[1]["kid"] == key_id

    @pytest.mark.asyncio
    async def test_sysadmin_validate_migrates_legacy_hash_when_peppered(self, monkeypatch):
        """The explicitly privileged key-management store may migrate a digest."""
        from shared.api_key_store import (
            APIKeyModel,
            DatabaseAPIKeyStore,
            hash_api_key,
            legacy_hash_api_key,
        )

        raw_key = "rge_live_legacy.secret"
        key_id = raw_key.split(".", 1)[0]
        monkeypatch.setenv("REGENGINE_API_KEY_HASH_PEPPER", "pepper-value")
        model = APIKeyModel(
            key_id=key_id,
            key_hash=legacy_hash_api_key(raw_key),
            key_prefix=raw_key[:12],
            name="Legacy Key",
            tenant_id="00000000-0000-0000-0000-000000000000",
            allowed_jurisdictions=["US"],
            scopes=["read"],
            rate_limit_per_minute=60,
            rate_limit_per_hour=1000,
            rate_limit_per_day=10000,
            enabled=True,
            created_at=datetime.now(timezone.utc),
            total_requests=0,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=model)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        store = DatabaseAPIKeyStore(
            database_url=TEST_DATABASE_URL,
            arm_sysadmin_rls=True,
        )
        with patch.object(store, "_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await store.validate_key(raw_key)

        assert result is not None
        assert result.key_id == key_id
        assert model.key_hash == hash_api_key(raw_key)

    @pytest.mark.asyncio
    async def test_validate_rejects_forged_secret_against_legacy_hash_when_peppered(self, monkeypatch):
        """A leaked key_id plus wrong secret must not match legacy fallback."""
        from shared.api_key_store import (
            APIKeyModel,
            DatabaseAPIKeyStore,
            legacy_hash_api_key,
        )

        real_key = "rge_live_legacy.real-secret"
        forged_key = "rge_live_legacy.forged-secret"
        key_id = real_key.split(".", 1)[0]
        monkeypatch.setenv("REGENGINE_API_KEY_HASH_PEPPER", "pepper-value")

        model = APIKeyModel(
            key_id=key_id,
            key_hash=legacy_hash_api_key(real_key),
            key_prefix=real_key[:12],
            name="Legacy Key",
            enabled=True,
            created_at=datetime.now(timezone.utc),
            total_requests=0,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=model)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()

        store = DatabaseAPIKeyStore(database_url=TEST_DATABASE_URL)
        with patch.object(store, "_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await store.validate_key(forged_key)

        assert result is None
        assert model.key_hash == legacy_hash_api_key(real_key)
        assert model.total_requests == 0


class TestRateLimiting:
    """Test rate limiting functionality."""

    @pytest.mark.asyncio
    async def test_rate_limit_without_redis_fails_closed(self, monkeypatch):
        """Without Redis, distributed DB-key rate limiting fails closed."""
        from shared.api_key_store import DatabaseAPIKeyStore

        monkeypatch.delenv("REDIS_URL", raising=False)
        store = DatabaseAPIKeyStore(database_url=TEST_DATABASE_URL)
        # No Redis configured

        info = await store.check_rate_limit("rge_test", limit=60)
        assert info.allowed is False
        assert info.remaining == 0
        assert info.retry_after == 60

    @pytest.mark.asyncio
    async def test_rate_limit_with_redis_tracks_usage(self):
        """With Redis, rate limiting should track usage."""
        from shared.api_key_store import DatabaseAPIKeyStore

        store = DatabaseAPIKeyStore(database_url=TEST_DATABASE_URL)

        # Mock Redis
        mock_redis = AsyncMock()
        mock_pipe = MagicMock()  # Sync methods like incr, expire
        mock_pipe.execute = AsyncMock(return_value=[5, True])  # 5 requests
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        store._redis = mock_redis

        info = await store.check_rate_limit("rge_test", limit=60)
        assert info.allowed is True
        assert info.remaining == 55  # 60 - 5

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self):
        """Rate limit should block when exceeded."""
        from shared.api_key_store import DatabaseAPIKeyStore

        store = DatabaseAPIKeyStore(database_url=TEST_DATABASE_URL)

        # Mock Redis
        mock_redis = AsyncMock()
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[61, True])  # Over limit
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        store._redis = mock_redis

        info = await store.check_rate_limit("rge_test", limit=60)
        assert info.allowed is False
        assert info.remaining == 0
        assert info.retry_after is not None


class TestKeyRotation:
    """Test key rotation functionality."""

    @pytest.mark.asyncio
    async def test_rotate_key_creates_new_key(self):
        """rotate_key should create a new key with same settings."""
        from shared.api_key_store import APIKeyModel, DatabaseAPIKeyStore

        store = DatabaseAPIKeyStore(database_url=TEST_DATABASE_URL)

        # Mock database with old key
        old_key = MagicMock()
        old_key.name = "Old Key"
        old_key.description = "Old description"
        old_key.tenant_id = "00000000-0000-0000-0000-000000000000"
        old_key.billing_tier = "ENTERPRISE"
        old_key.allowed_jurisdictions = ["US", "EU"]
        old_key.scopes = ["read:all"]
        old_key.rate_limit_per_minute = 100
        old_key.rate_limit_per_hour = 2000
        old_key.rate_limit_per_day = 20000
        old_key.expires_at = None
        old_key.metadata = {"original": True}

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=old_key)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()

        with patch.object(store, "_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            # Mock create_key
            with patch.object(store, "create_key") as mock_create:
                mock_create.return_value = MagicMock(
                    key_id="rge_new_key",
                    raw_key="rge_new_key.secret",
                )

                # Mock revoke_key
                with patch.object(store, "revoke_key") as mock_revoke:
                    mock_revoke.return_value = True

                    result = await store.rotate_key(
                        "rge_old_key",
                        created_by="admin",
                        reason="Security rotation",
                    )

        assert result is not None
        mock_create.assert_called_once()
        mock_revoke.assert_called_once()


class TestMigration:
    """Test migration from in-memory store."""

    @pytest.mark.asyncio
    async def test_migrate_from_memory_store(self):
        """Should migrate keys from in-memory to database store."""
        from shared.api_key_store import DatabaseAPIKeyStore, migrate_from_memory_store
        from shared.auth import APIKey, APIKeyStore

        # Create in-memory store with test key
        memory_store = APIKeyStore()
        raw_key, old_key = memory_store.create_key(
            name="Legacy Key",
            tenant_id="00000000-0000-0000-0000-000000000000",
            rate_limit_per_minute=120,
        )

        # Create mock database store
        db_store = DatabaseAPIKeyStore(database_url=TEST_DATABASE_URL)

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()

        with patch.object(db_store, "_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            migrated = await migrate_from_memory_store(
                memory_store,
                db_store,
                created_by="migration-script",
            )

        assert len(migrated) == 1
        assert old_key.key_id in migrated


class TestSecurityFeatures:
    """Test security-related features."""

    def test_raw_key_never_stored_in_model(self):
        """APIKeyModel should not have a raw_key field."""
        from shared.api_key_store import APIKeyModel

        model_columns = {c.name for c in APIKeyModel.__table__.columns}
        assert "raw_key" not in model_columns
        assert "key_hash" in model_columns  # Hash is stored

    def test_api_key_response_excludes_hash(self):
        """APIKeyResponse should not expose key_hash."""
        from shared.api_key_store import APIKeyResponse

        fields = APIKeyResponse.model_fields
        assert "key_hash" not in fields

    @pytest.mark.asyncio
    async def test_validate_uses_constant_time_comparison(self):
        """validate_key must compare hashes with hmac.compare_digest.

        Spies on the real compare_digest (behavior preserved): if the
        implementation is ever swapped for ``==``, the spy records no
        calls and this test fails.
        """
        import shared.api_key_store as module
        from shared.api_key_store import APIKeyModel, DatabaseAPIKeyStore, hash_api_key

        raw_key = "rge_ctt_live.real-secret"
        key_id = raw_key.split(".", 1)[0]
        model = APIKeyModel(
            key_id=key_id,
            key_hash=hash_api_key(raw_key),
            key_prefix=raw_key[:12],
            name="Timing Key",
            tenant_id="00000000-0000-0000-0000-000000000000",
            allowed_jurisdictions=["US"],
            scopes=["read"],
            rate_limit_per_minute=60,
            rate_limit_per_hour=1000,
            rate_limit_per_day=10000,
            enabled=True,
            created_at=datetime.now(timezone.utc),
            total_requests=0,
        )

        def _mock_session_for(model_row):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none = MagicMock(return_value=model_row)
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.flush = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_session.rollback = AsyncMock()
            mock_session.close = AsyncMock()
            return mock_session

        store = DatabaseAPIKeyStore(database_url=TEST_DATABASE_URL)
        with patch.object(store, "_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=_mock_session_for(model))
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch.object(module.hmac, "compare_digest", wraps=module.hmac.compare_digest) as spy:
                result = await store.validate_key(raw_key)

        assert result is not None
        assert result.key_id == key_id
        assert spy.call_count >= 1, (
            "validate_key did not call hmac.compare_digest. Hash comparison is not constant-time"
        )

    @pytest.mark.asyncio
    async def test_validate_wrong_secret_fails_constant_time_check(self):
        """A correct key_id with a wrong secret must not validate.

        Guards the other half of the timing-attack surface: an attacker
        who learns a key_id must not match the stored hash, and the
        rejection must still go through hmac.compare_digest.
        """
        import shared.api_key_store as module
        from shared.api_key_store import APIKeyModel, DatabaseAPIKeyStore, hash_api_key

        real_key = "rge_ctt_live.real-secret"
        forged_key = "rge_ctt_live.forged-secret"
        key_id = real_key.split(".", 1)[0]
        model = APIKeyModel(
            key_id=key_id,
            key_hash=hash_api_key(real_key),
            key_prefix=real_key[:12],
            name="Timing Key",
            tenant_id="00000000-0000-0000-0000-000000000000",
            allowed_jurisdictions=["US"],
            scopes=["read"],
            rate_limit_per_minute=60,
            rate_limit_per_hour=1000,
            rate_limit_per_day=10000,
            enabled=True,
            created_at=datetime.now(timezone.utc),
            total_requests=0,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=model)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()

        store = DatabaseAPIKeyStore(database_url=TEST_DATABASE_URL)
        with patch.object(store, "_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch.object(module.hmac, "compare_digest", wraps=module.hmac.compare_digest) as spy:
                result = await store.validate_key(forged_key)

        assert result is None
        assert spy.call_count >= 1, "rejected key did not go through hmac.compare_digest"


class TestAuditFields:
    """Test audit trail fields."""

    def test_model_has_audit_fields(self):
        """APIKeyModel should have created_by, revoked_by, revoke_reason."""
        from shared.api_key_store import APIKeyModel

        model_columns = {c.name for c in APIKeyModel.__table__.columns}
        assert "created_by" in model_columns
        assert "revoked_by" in model_columns
        assert "revoke_reason" in model_columns
        assert "revoked_at" in model_columns

    def test_model_has_timestamp_fields(self):
        """APIKeyModel should have timestamp fields."""
        from shared.api_key_store import APIKeyModel

        model_columns = {c.name for c in APIKeyModel.__table__.columns}
        assert "created_at" in model_columns
        assert "updated_at" in model_columns
        assert "last_used_at" in model_columns
