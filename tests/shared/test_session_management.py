"""
SEC-010: Tests for Session Management.
"""

import time
from unittest.mock import patch

import pytest


class TestSessionCookieSettings:
    """Test SessionCookieSettings model."""

    def test_default_settings(self):
        """Should have secure defaults."""
        from shared.session_management import SessionCookieSettings

        settings = SessionCookieSettings()

        assert settings.name == "regengine_session"
        assert settings.secure is True  # HTTPS only
        assert settings.http_only is True  # No JS access
        assert settings.same_site == "lax"  # CSRF protection

    def test_to_cookie_params(self):
        """Should convert to cookie parameters."""
        from shared.session_management import SessionCookieSettings

        settings = SessionCookieSettings(
            name="my_session",
            domain=".example.com",
        )

        params = settings.to_cookie_params()

        assert params["key"] == "my_session"
        assert params["domain"] == ".example.com"
        assert params["httponly"] is True


class TestSessionConfig:
    """Test SessionConfig class."""

    def test_default_config(self):
        """Should have secure defaults."""
        from shared.session_management import SessionConfig

        with patch.dict("os.environ", {"SESSION_SECRET": "test-secret"}):
            config = SessionConfig()

        assert config.max_age == 3600  # 1 hour
        assert config.absolute_timeout == 86400  # 24 hours
        assert config.idle_timeout == 1800  # 30 minutes
        assert config.max_concurrent == 5
        assert config.rotate_on_auth is True

    def test_development_config(self):
        """Should create development config."""
        from shared.session_management import SessionConfig

        config = SessionConfig.development()

        assert config.cookie.secure is False  # Allow HTTP
        assert config.max_concurrent == 10


class TestSessionStatus:
    """Test SessionStatus enum."""

    def test_statuses(self):
        """Should define all statuses."""
        from shared.session_management import SessionStatus

        assert SessionStatus.ACTIVE.value == "active"
        assert SessionStatus.EXPIRED.value == "expired"
        assert SessionStatus.REVOKED.value == "revoked"
        assert SessionStatus.IDLE_TIMEOUT.value == "idle_timeout"


class TestSession:
    """Test Session model."""

    def test_create_session(self):
        """Should create session."""
        from shared.session_management import Session, SessionStatus

        now = time.time()
        session = Session(
            session_id="test-session-id",
            user_id="user-123",
            expires_at=now + 3600,
        )

        assert session.session_id == "test-session-id"
        assert session.user_id == "user-123"
        assert session.status == SessionStatus.ACTIVE
        assert session.is_valid is True

    def test_expired_session(self):
        """Should detect expired session."""
        from shared.session_management import Session, SessionStatus

        session = Session(
            session_id="test",
            user_id="user-123",
            expires_at=time.time() - 100,  # Already expired
        )

        assert session.is_valid is False

    def test_revoked_session(self):
        """Should detect revoked session."""
        from shared.session_management import Session, SessionStatus

        session = Session(
            session_id="test",
            user_id="user-123",
            expires_at=time.time() + 3600,
            status=SessionStatus.REVOKED,
        )

        assert session.is_valid is False

    def test_update_access(self):
        """Should update access time."""
        from shared.session_management import Session

        session = Session(
            session_id="test",
            user_id="user-123",
            expires_at=time.time() + 3600,
            accessed_at=time.time() - 100,
        )

        old_accessed = session.accessed_at
        session.update_access()

        assert session.accessed_at > old_accessed


class TestSessionIDGenerator:
    """Test SessionIDGenerator."""

    def test_generate_unique_ids(self):
        """Should generate unique IDs."""
        from shared.session_management import SessionIDGenerator

        ids = [SessionIDGenerator.generate() for _ in range(100)]

        assert len(set(ids)) == 100

    def test_generate_proper_length(self):
        """Should generate proper entropy."""
        from shared.session_management import SessionIDGenerator

        session_id = SessionIDGenerator.generate(32)

        # 32 bytes = ~43 chars in base64
        assert len(session_id) >= 40

    def test_hash_user_agent(self):
        """Should hash user agent."""
        from shared.session_management import SessionIDGenerator

        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        hash1 = SessionIDGenerator.hash_user_agent(ua)
        hash2 = SessionIDGenerator.hash_user_agent(ua)

        assert hash1 == hash2  # Same input = same hash
        assert len(hash1) == 32


class TestInMemorySessionStore:
    """Test InMemorySessionStore."""

    @pytest.fixture
    def store(self):
        """Create store."""
        from shared.session_management import InMemorySessionStore

        return InMemorySessionStore()

    @pytest.fixture
    def session(self):
        """Create test session."""
        from shared.session_management import Session

        return Session(
            session_id="test-session",
            user_id="user-123",
            expires_at=time.time() + 3600,
        )

    @pytest.mark.asyncio
    async def test_save_and_get(self, store, session):
        """Should save and retrieve session."""
        await store.save(session)
        result = await store.get("test-session")

        assert result is not None
        assert result.session_id == "test-session"

    @pytest.mark.asyncio
    async def test_delete(self, store, session):
        """Should delete session."""
        await store.save(session)
        await store.delete("test-session")
        result = await store.get("test-session")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_sessions(self, store):
        """Should get all user sessions."""
        from shared.session_management import Session

        s1 = Session(
            session_id="s1",
            user_id="user-1",
            expires_at=time.time() + 3600,
        )
        s2 = Session(
            session_id="s2",
            user_id="user-1",
            expires_at=time.time() + 3600,
        )
        s3 = Session(
            session_id="s3",
            user_id="user-2",
            expires_at=time.time() + 3600,
        )

        await store.save(s1)
        await store.save(s2)
        await store.save(s3)

        sessions = await store.get_user_sessions("user-1")

        assert len(sessions) == 2
        assert all(s.user_id == "user-1" for s in sessions)

    @pytest.mark.asyncio
    async def test_delete_user_sessions(self, store):
        """Should delete all user sessions."""
        from shared.session_management import Session

        s1 = Session(session_id="s1", user_id="user-1", expires_at=time.time() + 3600)
        s2 = Session(session_id="s2", user_id="user-1", expires_at=time.time() + 3600)

        await store.save(s1)
        await store.save(s2)

        count = await store.delete_user_sessions("user-1")

        assert count == 2
        assert await store.get("s1") is None
        assert await store.get("s2") is None

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, store):
        """Should cleanup expired sessions."""
        from shared.session_management import Session

        valid = Session(
            session_id="valid",
            user_id="user-1",
            expires_at=time.time() + 3600,
        )
        expired = Session(
            session_id="expired",
            user_id="user-1",
            expires_at=time.time() - 100,
        )

        await store.save(valid)
        await store.save(expired)

        count = await store.cleanup_expired()

        assert count == 1
        assert await store.get("valid") is not None
        assert await store.get("expired") is None


class TestSessionManager:
    """Test SessionManager."""

    @pytest.fixture
    def manager(self):
        """Create session manager."""
        from shared.session_management import SessionManager, SessionConfig

        config = SessionConfig(
            secret_key="test-secret-key",
            max_age=3600,
            idle_timeout=1800,
            max_concurrent=3,
        )
        return SessionManager(config)

    def test_requires_secret(self):
        """Should require secret key."""
        from shared.session_management import SessionManager, SessionConfig

        with patch.dict("os.environ", {}, clear=True):
            config = SessionConfig(secret_key=None)
            with pytest.raises(ValueError, match="secret"):
                SessionManager(config)

    @pytest.mark.asyncio
    async def test_create_session(self, manager):
        """Should create session."""
        session = await manager.create_session(
            user_id="user-123",
            ip_address="192.168.1.1",
            user_agent="TestBrowser/1.0",
        )

        assert session.user_id == "user-123"
        assert session.session_id is not None
        assert session.is_valid is True

    @pytest.mark.asyncio
    async def test_get_session(self, manager):
        """Should get valid session."""
        session = await manager.create_session(user_id="user-123")

        result = await manager.get_session(session.session_id)

        assert result is not None
        assert result.session_id == session.session_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, manager):
        """Should return None for nonexistent session."""
        result = await manager.get_session("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_end_session(self, manager):
        """Should end session."""
        session = await manager.create_session(user_id="user-123")

        result = await manager.end_session(session.session_id)

        assert result is True
        assert await manager.get_session(session.session_id) is None

    @pytest.mark.asyncio
    async def test_end_all_sessions(self, manager):
        """Should end all user sessions."""
        await manager.create_session(user_id="user-1")
        await manager.create_session(user_id="user-1")
        await manager.create_session(user_id="user-1")

        count = await manager.end_all_sessions("user-1")

        assert count == 3

    @pytest.mark.asyncio
    async def test_end_all_except_current(self, manager):
        """Should end all except current session."""
        s1 = await manager.create_session(user_id="user-1")
        await manager.create_session(user_id="user-1")
        await manager.create_session(user_id="user-1")

        count = await manager.end_all_sessions("user-1", except_session=s1.session_id)

        assert count == 2
        assert await manager.get_session(s1.session_id) is not None

    @pytest.mark.asyncio
    async def test_session_limit_enforcement(self, manager):
        """Should enforce max concurrent sessions."""
        # Create max sessions
        sessions = []
        for i in range(3):
            s = await manager.create_session(user_id="user-1")
            sessions.append(s)

        # Create one more (should remove oldest)
        new_session = await manager.create_session(user_id="user-1")

        # Oldest should be gone
        assert await manager.get_session(sessions[0].session_id) is None
        # Newest should exist
        assert await manager.get_session(new_session.session_id) is not None

    @pytest.mark.asyncio
    async def test_refresh_session(self, manager):
        """Should refresh session expiration."""
        session = await manager.create_session(user_id="user-123")
        original_expires = session.expires_at

        # Wait a tiny bit
        time.sleep(0.01)

        refreshed = await manager.refresh_session(session)

        assert refreshed.expires_at >= original_expires

    @pytest.mark.asyncio
    async def test_rotate_session(self, manager):
        """Should rotate session ID."""
        old_session = await manager.create_session(
            user_id="user-123",
            data={"key": "value"},
        )
        old_id = old_session.session_id

        new_session = await manager.rotate_session(old_session)

        assert new_session.session_id != old_id
        assert new_session.user_id == "user-123"
        assert new_session.data["key"] == "value"
        # Old session should be revoked
        assert await manager.get_session(old_id) is None


class TestSessionBinding:
    """Test session binding features."""

    @pytest.fixture
    def ip_bound_manager(self):
        """Create manager with IP binding."""
        from shared.session_management import SessionManager, SessionConfig

        config = SessionConfig(
            secret_key="test-secret",
            bind_to_ip=True,
        )
        return SessionManager(config)

    @pytest.fixture
    def ua_bound_manager(self):
        """Create manager with user agent binding."""
        from shared.session_management import SessionManager, SessionConfig

        config = SessionConfig(
            secret_key="test-secret",
            bind_to_user_agent=True,
        )
        return SessionManager(config)

    @pytest.mark.asyncio
    async def test_ip_binding(self, ip_bound_manager):
        """Should validate IP binding."""
        session = await ip_bound_manager.create_session(
            user_id="user-123",
            ip_address="192.168.1.1",
        )

        # Same IP works
        result = await ip_bound_manager.get_session(
            session.session_id,
            ip_address="192.168.1.1",
        )
        assert result is not None

        # Different IP fails
        result = await ip_bound_manager.get_session(
            session.session_id,
            ip_address="10.0.0.1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_user_agent_binding(self, ua_bound_manager):
        """Should validate user agent binding."""
        session = await ua_bound_manager.create_session(
            user_id="user-123",
            user_agent="Chrome/100",
        )

        # Same UA works
        result = await ua_bound_manager.get_session(
            session.session_id,
            user_agent="Chrome/100",
        )
        assert result is not None

        # Different UA fails
        result = await ua_bound_manager.get_session(
            session.session_id,
            user_agent="Firefox/90",
        )
        assert result is None


class TestSessionTimeouts:
    """Test session timeout features."""

    @pytest.mark.asyncio
    async def test_idle_timeout(self):
        """Should enforce idle timeout."""
        from shared.session_management import SessionManager, SessionConfig

        config = SessionConfig(
            secret_key="test-secret",
            idle_timeout=1,  # 1 second
        )
        manager = SessionManager(config)

        session = await manager.create_session(user_id="user-123")

        # Wait for idle timeout
        time.sleep(1.5)

        result = await manager.get_session(session.session_id)
        assert result is None


class TestSessionSigning:
    """Test session ID signing."""

    @pytest.fixture
    def manager(self):
        """Create manager."""
        from shared.session_management import SessionManager, SessionConfig

        config = SessionConfig(secret_key="test-secret")
        return SessionManager(config)

    def test_sign_session_id(self, manager):
        """Should sign session ID."""
        session_id = "test-session-id"
        signed = manager.sign_session_id(session_id)

        assert "." in signed
        assert signed.startswith(session_id)

    def test_verify_valid_signature(self, manager):
        """Should verify valid signature."""
        session_id = "test-session-id"
        signed = manager.sign_session_id(session_id)

        result = manager.verify_signed_session_id(signed)

        assert result == session_id

    def test_reject_tampered_signature(self, manager):
        """Should reject tampered signature."""
        session_id = "test-session-id"
        signed = manager.sign_session_id(session_id)

        # Tamper with signature
        tampered = signed[:-5] + "xxxxx"

        result = manager.verify_signed_session_id(tampered)

        assert result is None

    def test_reject_invalid_format(self, manager):
        """Should reject invalid format."""
        result = manager.verify_signed_session_id("no-signature-here")

        assert result is None


class TestMFASupport:
    """Test MFA support in sessions."""

    @pytest.fixture
    def manager(self):
        """Create manager."""
        from shared.session_management import SessionManager, SessionConfig

        config = SessionConfig(secret_key="test-secret")
        return SessionManager(config)

    @pytest.mark.asyncio
    async def test_set_mfa_verified(self, manager):
        """Should mark session as MFA verified."""
        session = await manager.create_session(user_id="user-123")
        assert session.mfa_verified is False

        result = await manager.set_mfa_verified(session.session_id)

        assert result.mfa_verified is True

    @pytest.mark.asyncio
    async def test_mfa_preserved_on_rotate(self, manager):
        """MFA status should be preserved on rotation."""
        session = await manager.create_session(user_id="user-123")
        await manager.set_mfa_verified(session.session_id)

        # Get updated session
        session = await manager.get_session(session.session_id)

        new_session = await manager.rotate_session(session)

        assert new_session.mfa_verified is True


class TestSessionData:
    """Test session data management."""

    @pytest.fixture
    def manager(self):
        """Create manager."""
        from shared.session_management import SessionManager, SessionConfig

        config = SessionConfig(secret_key="test-secret")
        return SessionManager(config)

    @pytest.mark.asyncio
    async def test_initial_data(self, manager):
        """Should store initial data."""
        session = await manager.create_session(
            user_id="user-123",
            data={"theme": "dark"},
        )

        assert session.data["theme"] == "dark"

    @pytest.mark.asyncio
    async def test_update_session_data(self, manager):
        """Should update session data."""
        session = await manager.create_session(
            user_id="user-123",
            data={"key1": "value1"},
        )

        updated = await manager.update_session_data(
            session.session_id,
            {"key2": "value2"},
        )

        assert updated.data["key1"] == "value1"
        assert updated.data["key2"] == "value2"

    @pytest.mark.asyncio
    async def test_list_user_sessions(self, manager):
        """Should list user sessions."""
        s1 = await manager.create_session(user_id="user-1", ip_address="1.1.1.1")
        s2 = await manager.create_session(user_id="user-1", ip_address="2.2.2.2")

        sessions = await manager.list_user_sessions("user-1", current_session_id=s1.session_id)

        assert len(sessions) == 2
        current = [s for s in sessions if s.is_current]
        assert len(current) == 1
        assert current[0].session_id == s1.session_id
