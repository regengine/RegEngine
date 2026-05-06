"""Unit tests for Redis session store.

Tests cover:
- Session creation and retrieval
- Token-based lookup
- Session updates and rotation
- Revocation (single and bulk)
- TTL and expiration
- Cleanup operations
"""

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.session_store import InMemorySessionStore, RedisSessionStore, SessionData


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    redis = AsyncMock()
    redis.pipeline = MagicMock()
    
    # Mock pipeline context manager
    pipe = AsyncMock()
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock()
    redis.pipeline.return_value = pipe
    
    return redis


@pytest.fixture
def session_store(mock_redis):
    """Session store with mocked Redis."""
    store = RedisSessionStore("redis://localhost:6379/0")
    store._client = mock_redis
    return store


@pytest.fixture
def sample_session():
    """Sample session data for testing."""
    now = datetime.now(timezone.utc)
    return SessionData(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        refresh_token_hash="abc123hash",
        family_id=uuid.uuid4(),
        is_revoked=False,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=30),
        user_agent="TestAgent/1.0",
        ip_address="192.168.1.1"
    )


class TestSessionData:
    """Test SessionData model."""
    
    def test_to_redis_hash(self, sample_session):
        """Test conversion to Redis hash format."""
        hash_data = sample_session.to_redis_hash()
        
        assert hash_data["user_id"] == str(sample_session.user_id)
        assert hash_data["refresh_token_hash"] == "abc123hash"
        assert hash_data["is_revoked"] == "false"
        assert hash_data["user_agent"] == "TestAgent/1.0"
    
    def test_from_redis_hash(self, sample_session):
        """Test parsing from Redis hash format."""
        hash_data = sample_session.to_redis_hash()
        parsed = SessionData.from_redis_hash(sample_session.id, hash_data)
        
        assert parsed.id == sample_session.id
        assert parsed.user_id == sample_session.user_id
        assert parsed.refresh_token_hash == sample_session.refresh_token_hash
        assert parsed.is_revoked == sample_session.is_revoked
    
    def test_boolean_conversion(self):
        """Test is_revoked boolean conversion."""
        data = {
            "user_id": str(uuid.uuid4()),
            "refresh_token_hash": "hash",
            "family_id": str(uuid.uuid4()),
            "is_revoked": "true",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_used_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "user_agent": "",
            "ip_address": ""
        }
        
        session = SessionData.from_redis_hash(uuid.uuid4(), data)
        assert session.is_revoked is True


class TestRedisSessionStore:
    """Test RedisSessionStore operations."""
    
    @pytest.mark.asyncio
    async def test_create_session(self, session_store, mock_redis, sample_session):
        """Test session creation."""
        # Setup
        pipe = mock_redis.pipeline.return_value.__aenter__.return_value
        
        # Execute
        result = await session_store.create_session(sample_session)
        
        # Verify
        assert result == sample_session
        assert pipe.hset.called
        assert pipe.expire.called
        assert pipe.sadd.called
        assert pipe.setex.called
        assert pipe.execute.called
    
    @pytest.mark.asyncio
    async def test_get_session(self, session_store, mock_redis, sample_session):
        """Test session retrieval by ID."""
        # Setup
        mock_redis.hgetall.return_value = sample_session.to_redis_hash()
        
        # Execute
        result = await session_store.get_session(sample_session.id)
        
        # Verify
        assert result is not None
        assert result.id == sample_session.id
        assert result.user_id == sample_session.user_id
        mock_redis.hgetall.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_session_not_found(self, session_store, mock_redis):
        """Test session retrieval returns None if not found."""
        # Setup
        mock_redis.hgetall.return_value = {}
        
        # Execute
        result = await session_store.get_session(uuid.uuid4())
        
        # Verify
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_session_by_token(self, session_store, mock_redis, sample_session):
        """Test session retrieval by token hash."""
        # Setup
        mock_redis.get.return_value = str(sample_session.id)
        mock_redis.hgetall.return_value = sample_session.to_redis_hash()
        
        # Execute
        result = await session_store.get_session_by_token("abc123hash")
        
        # Verify
        assert result is not None
        assert result.id == sample_session.id
        mock_redis.get.assert_called_once()
        mock_redis.hgetall.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_session_by_token_not_found(self, session_store, mock_redis):
        """Test token lookup returns None if not found."""
        # Setup
        mock_redis.get.return_value = None
        
        # Execute
        result = await session_store.get_session_by_token("invalidhash")
        
        # Verify
        assert result is None
        mock_redis.hgetall.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_update_session(self, session_store, mock_redis, sample_session):
        """Test session update."""
        # Setup
        mock_redis.exists.return_value = 1
        mock_redis.ttl.return_value = 86400
        pipe = mock_redis.pipeline.return_value.__aenter__.return_value
        
        updates = {"last_used_at": datetime.now(timezone.utc).isoformat()}
        
        # Execute
        result = await session_store.update_session(sample_session.id, updates)
        
        # Verify
        assert result is True
        pipe.hset.assert_called_once()
        pipe.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_session_with_token_rotation(self, session_store, mock_redis, sample_session):
        """Test session update with token rotation."""
        # Setup
        mock_redis.exists.return_value = 1
        mock_redis.ttl.return_value = 86400
        pipe = mock_redis.pipeline.return_value.__aenter__.return_value
        
        # Execute
        result = await session_store.update_session(
            sample_session.id,
            {"last_used_at": datetime.now(timezone.utc).isoformat()},
            new_token_hash="newhash",
            old_token_hash="oldhash"
        )
        
        # Verify
        assert result is True
        pipe.delete.assert_called()  # Old token deleted
        pipe.setex.assert_called()   # New token created
    
    @pytest.mark.asyncio
    async def test_revoke_session(self, session_store, mock_redis, sample_session):
        """Test session revocation."""
        # Setup
        mock_redis.exists.return_value = 1
        mock_redis.ttl.return_value = 86400
        pipe = mock_redis.pipeline.return_value.__aenter__.return_value
        
        # Execute
        result = await session_store.revoke_session(sample_session.id)
        
        # Verify
        assert result is True
        pipe.hset.assert_called()
        # Should set is_revoked to "true"
        call_args = pipe.hset.call_args
        assert "is_revoked" in call_args[1]["mapping"]
        assert call_args[1]["mapping"]["is_revoked"] == "true"
    
    @pytest.mark.asyncio
    async def test_delete_session(self, session_store, mock_redis, sample_session):
        """Test session deletion."""
        # Setup
        mock_redis.hgetall.return_value = sample_session.to_redis_hash()
        pipe = mock_redis.pipeline.return_value.__aenter__.return_value
        
        # Execute
        result = await session_store.delete_session(sample_session.id)
        
        # Verify
        assert result is True
        pipe.delete.assert_called()  # session key deleted
        pipe.srem.assert_called()    # removed from user_sessions set
        pipe.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_delete_session_not_found(self, session_store, mock_redis):
        """Test deleting non-existent session."""
        # Setup
        mock_redis.hgetall.return_value = {}
        
        # Execute
        result = await session_store.delete_session(uuid.uuid4())
        
        # Verify
        assert result is False


    @pytest.mark.asyncio
    async def test_list_user_sessions(self, session_store, mock_redis, sample_session):
        """Test listing user sessions."""
        # Setup
        session_id_str = str(sample_session.id)
        mock_redis.smembers.return_value = {session_id_str}
        
        pipe = mock_redis.pipeline.return_value.__aenter__.return_value
        pipe.execute.return_value = [sample_session.to_redis_hash()]
        
        # Execute
        result = await session_store.list_user_sessions(sample_session.user_id)
        
        # Verify
        assert len(result) == 1
        assert result[0].id == sample_session.id
        assert result[0].user_id == sample_session.user_id
    
    @pytest.mark.asyncio
    async def test_list_user_sessions_filters_revoked(self, session_store, mock_redis, sample_session):
        """Test listing sessions filters out revoked when active_only=True."""
        # Setup
        sample_session.is_revoked = True
        session_id_str = str(sample_session.id)
        mock_redis.smembers.return_value = {session_id_str}
        
        pipe = mock_redis.pipeline.return_value.__aenter__.return_value
        pipe.execute.return_value = [sample_session.to_redis_hash()]
        
        # Execute
        result = await session_store.list_user_sessions(sample_session.user_id, active_only=True)
        
        # Verify
        assert len(result) == 0  # Revoked session filtered out
    
    @pytest.mark.asyncio
    async def test_list_user_sessions_filters_expired(self, session_store, mock_redis, sample_session):
        """Test listing sessions filters out expired when active_only=True."""
        # Setup - expired session
        sample_session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        session_id_str = str(sample_session.id)
        mock_redis.smembers.return_value = {session_id_str}
        
        pipe = mock_redis.pipeline.return_value.__aenter__.return_value
        pipe.execute.return_value = [sample_session.to_redis_hash()]
        
        # Execute
        result = await session_store.list_user_sessions(sample_session.user_id, active_only=True)
        
        # Verify
        assert len(result) == 0  # Expired session filtered out
    
    @pytest.mark.asyncio
    async def test_revoke_all_user_sessions(self, session_store, mock_redis, sample_session):
        """Test revoking all sessions for a user."""
        # Setup
        session_id_str = str(sample_session.id)
        mock_redis.smembers.return_value = {session_id_str}
        
        pipe = mock_redis.pipeline.return_value.__aenter__.return_value
        pipe.execute.return_value = [sample_session.to_redis_hash()]
        
        # Execute
        count = await session_store.revoke_all_user_sessions(sample_session.user_id)
        
        # Verify
        assert count == 1
        # Should have called hset to set is_revoked
        assert pipe.hset.called
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, session_store, mock_redis):
        """Test health check when Redis is accessible."""
        # Setup
        mock_redis.ping = AsyncMock(return_value=True)
        
        # Execute
        result = await session_store.health_check()
        
        # Verify
        assert result is True
        mock_redis.ping.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self, session_store, mock_redis):
        """Test health check when Redis is not accessible."""
        # Setup
        mock_redis.ping = AsyncMock(side_effect=Exception("Connection refused"))
        
        # Execute
        result = await session_store.health_check()
        
        # Verify
        assert result is False
    
    def test_calculate_ttl(self, session_store):
        """Test TTL calculation."""
        # Future expiration
        future = datetime.now(timezone.utc) + timedelta(hours=24)
        ttl = session_store._calculate_ttl(future)
        assert 86300 < ttl < 86500  # ~24 hours in seconds
        
        # Past expiration (should return minimum 60 seconds)
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        ttl = session_store._calculate_ttl(past)
        assert ttl == 60
    
    def test_key_generation(self, session_store):
        """Test Redis key generation."""
        session_id = uuid.uuid4()
        user_id = uuid.uuid4()
        token_hash = "abc123"
        
        assert session_store._session_key(session_id) == f"session:{session_id}"
        assert session_store._user_sessions_key(user_id) == f"user_sessions:{user_id}"
        assert session_store._token_hash_key(token_hash) == f"token_hash:{token_hash}"


class TestInMemorySessionStore:
    """Integration-style tests for the local Redis fallback."""

    @pytest.fixture
    def in_memory_store(self):
        return InMemorySessionStore()

    @pytest.mark.asyncio
    async def test_round_trip_and_rotation(self, in_memory_store, sample_session):
        await in_memory_store.create_session(sample_session)

        by_id = await in_memory_store.get_session(sample_session.id)
        assert by_id is not None
        assert by_id.refresh_token_hash == sample_session.refresh_token_hash

        by_token = await in_memory_store.get_session_by_token(sample_session.refresh_token_hash)
        assert by_token is not None
        assert by_token.id == sample_session.id

        claimed = await in_memory_store.claim_session_by_token(sample_session.refresh_token_hash)
        assert claimed is not None
        assert claimed.id == sample_session.id
        assert await in_memory_store.get_session_by_token(sample_session.refresh_token_hash) is None

        rotated = await in_memory_store.update_session(
            sample_session.id,
            {"last_used_at": datetime.now(timezone.utc).isoformat()},
            new_token_hash="rotated-hash",
            old_token_hash=sample_session.refresh_token_hash,
        )
        assert rotated is True

        rotated_session = await in_memory_store.get_session_by_token("rotated-hash")
        assert rotated_session is not None
        assert rotated_session.id == sample_session.id

    @pytest.mark.asyncio
    async def test_raw_client_supports_nx_and_ttl(self, in_memory_store):
        client = await in_memory_store._get_client()

        inserted = await client.set("auth:recovery:used:test", "1", nx=True, ex=120)
        duplicate = await client.set("auth:recovery:used:test", "1", nx=True, ex=120)
        ttl = await client.ttl("auth:recovery:used:test")
        count = await client.incr("login_attempts:test@example.com")

        assert inserted is True
        assert duplicate is False
        assert ttl > 0
        assert count == 1
