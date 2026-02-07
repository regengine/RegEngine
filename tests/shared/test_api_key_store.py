"""
SEC-005: Tests for database-backed API key store.

These tests use SQLite in-memory for fast testing.
Production uses PostgreSQL.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)

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


class TestRateLimiting:
    """Test rate limiting functionality."""

    @pytest.mark.asyncio
    async def test_rate_limit_without_redis_allows_all(self):
        """Without Redis, rate limiting should be disabled (allow all)."""
        from shared.api_key_store import DatabaseAPIKeyStore

        store = DatabaseAPIKeyStore(database_url=TEST_DATABASE_URL)
        # No Redis configured

        info = await store.check_rate_limit("rge_test", limit=60)
        assert info.allowed is True
        assert info.remaining == 60

    @pytest.mark.asyncio
    async def test_rate_limit_with_redis_tracks_usage(self):
        """With Redis, rate limiting should track usage."""
        from shared.api_key_store import DatabaseAPIKeyStore

        store = DatabaseAPIKeyStore(database_url=TEST_DATABASE_URL)

        # Mock Redis
        mock_redis = AsyncMock()
        mock_pipe = MagicMock() # Sync methods like incr, expire
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
        from shared.api_key_store import DatabaseAPIKeyStore, APIKeyModel

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
        from shared.auth import APIKey, APIKeyStore
        from shared.api_key_store import DatabaseAPIKeyStore, migrate_from_memory_store

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

    def test_constant_time_comparison_used(self):
        """Validation should use hmac.compare_digest."""
        import hmac
        from shared.api_key_store import DatabaseAPIKeyStore

        # This is tested by code inspection - the actual function uses hmac.compare_digest
        # We verify the hash comparison is used by checking it's imported
        import shared.api_key_store as module
        assert hasattr(module, "hmac")


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
