"""
Tests for SEC-043: Session Security.

Tests cover:
- Session ID generation
- Session validation
- Timeout handling
- Fixation prevention
"""

import time
import pytest

from shared.session_security import (
    # Enums
    SessionStatus,
    SessionEvent,
    # Data classes
    SessionConfig,
    Session,
    SessionValidationResult,
    # Classes
    SessionIdGenerator,
    SessionValidator,
    SessionManager,
    SessionSecurityService,
    # Convenience functions
    get_session_service,
    create_session,
    validate_session,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create session config."""
    return SessionConfig(
        idle_timeout_seconds=1800,
        absolute_timeout_seconds=86400,
    )


@pytest.fixture
def id_generator(config):
    """Create ID generator."""
    return SessionIdGenerator(config)


@pytest.fixture
def validator(config):
    """Create validator."""
    return SessionValidator(config)


@pytest.fixture
def manager(config):
    """Create session manager."""
    return SessionManager(config)


@pytest.fixture
def service(config):
    """Create session service."""
    SessionSecurityService._instance = None
    return SessionSecurityService(config)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_session_status(self):
        """Should have expected status values."""
        assert SessionStatus.ACTIVE == "active"
        assert SessionStatus.EXPIRED == "expired"
        assert SessionStatus.INVALIDATED == "invalidated"
        assert SessionStatus.LOCKED == "locked"
    
    def test_session_events(self):
        """Should have expected event values."""
        assert SessionEvent.CREATED == "created"
        assert SessionEvent.ACCESSED == "accessed"
        assert SessionEvent.INVALIDATED == "invalidated"


# =============================================================================
# Test: SessionConfig
# =============================================================================

class TestSessionConfig:
    """Test SessionConfig class."""
    
    def test_default_values(self):
        """Should have secure defaults."""
        config = SessionConfig()
        
        assert config.session_id_length == 32
        assert config.use_secure_random is True
        assert config.cookie_secure is True
        assert config.cookie_http_only is True
    
    def test_custom_timeouts(self):
        """Should allow custom timeouts."""
        config = SessionConfig(
            idle_timeout_seconds=300,
            absolute_timeout_seconds=3600,
        )
        
        assert config.idle_timeout_seconds == 300
        assert config.absolute_timeout_seconds == 3600


# =============================================================================
# Test: Session
# =============================================================================

class TestSession:
    """Test Session class."""
    
    def test_is_active(self):
        """Should check active status."""
        session = Session(
            session_id="test",
            user_id="user-1",
            status=SessionStatus.ACTIVE,
        )
        
        assert session.is_active is True
    
    def test_is_expired(self):
        """Should check expiration."""
        session = Session(
            session_id="test",
            user_id="user-1",
            expires_at=time.time() - 1000,
        )
        
        assert session.is_expired is True
    
    def test_touch(self):
        """Should update last accessed time."""
        session = Session(
            session_id="test",
            user_id="user-1",
        )
        old_time = session.last_accessed_at
        
        time.sleep(0.01)
        session.touch()
        
        assert session.last_accessed_at > old_time


# =============================================================================
# Test: SessionIdGenerator
# =============================================================================

class TestSessionIdGenerator:
    """Test SessionIdGenerator."""
    
    def test_generates_unique_ids(self, id_generator):
        """Should generate unique IDs."""
        id1 = id_generator.generate()
        id2 = id_generator.generate()
        
        assert id1 != id2
    
    def test_generates_long_ids(self, id_generator):
        """Should generate long IDs."""
        session_id = id_generator.generate()
        
        assert len(session_id) >= 32
    
    def test_generates_with_fingerprint(self, id_generator):
        """Should generate with fingerprint."""
        session_id, fingerprint = id_generator.generate_with_fingerprint(
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )
        
        assert session_id is not None
        assert len(fingerprint) == 16


# =============================================================================
# Test: SessionValidator
# =============================================================================

class TestSessionValidator:
    """Test SessionValidator."""
    
    def test_validates_active_session(self, validator):
        """Should validate active session."""
        session = Session(
            session_id="test",
            user_id="user-1",
            status=SessionStatus.ACTIVE,
        )
        
        result = validator.validate(session)
        
        assert result.is_valid is True
    
    def test_rejects_invalidated(self, validator):
        """Should reject invalidated session."""
        session = Session(
            session_id="test",
            user_id="user-1",
            status=SessionStatus.INVALIDATED,
        )
        
        result = validator.validate(session)
        
        assert result.is_valid is False
        assert "invalidated" in result.error.lower()
    
    def test_rejects_locked(self, validator):
        """Should reject locked session."""
        session = Session(
            session_id="test",
            user_id="user-1",
            status=SessionStatus.LOCKED,
        )
        
        result = validator.validate(session)
        
        assert result.is_valid is False
        assert "locked" in result.error.lower()
    
    def test_rejects_expired(self, validator):
        """Should reject expired session."""
        session = Session(
            session_id="test",
            user_id="user-1",
            expires_at=time.time() - 1000,
        )
        
        result = validator.validate(session)
        
        assert result.is_valid is False
        assert "expired" in result.error.lower()
    
    def test_rejects_idle_timeout(self):
        """Should reject idle timeout."""
        config = SessionConfig(idle_timeout_seconds=1)
        validator = SessionValidator(config)
        session = Session(
            session_id="test",
            user_id="user-1",
            last_accessed_at=time.time() - 10,
        )
        
        result = validator.validate(session)
        
        assert result.is_valid is False
        assert "idle" in result.error.lower()
    
    def test_rejects_absolute_timeout(self):
        """Should reject absolute timeout."""
        config = SessionConfig(absolute_timeout_seconds=1)
        validator = SessionValidator(config)
        session = Session(
            session_id="test",
            user_id="user-1",
            created_at=time.time() - 10,
        )
        
        result = validator.validate(session)
        
        assert result.is_valid is False
        assert "absolute" in result.error.lower()
    
    def test_checks_ip_binding(self):
        """Should check IP binding."""
        config = SessionConfig(bind_to_ip=True)
        validator = SessionValidator(config)
        session = Session(
            session_id="test",
            user_id="user-1",
            ip_address="192.168.1.1",
        )
        
        result = validator.validate(session, ip_address="10.0.0.1")
        
        assert result.is_valid is False
        assert "IP" in result.error
    
    def test_checks_user_agent_binding(self):
        """Should check user agent binding."""
        config = SessionConfig(bind_to_user_agent=True)
        validator = SessionValidator(config)
        session = Session(
            session_id="test",
            user_id="user-1",
            user_agent="Mozilla/5.0",
        )
        
        result = validator.validate(session, user_agent="Evil/1.0")
        
        assert result.is_valid is False
        assert "agent" in result.error.lower()
    
    def test_locks_after_failed_validations(self):
        """Should lock after max failed validations."""
        config = SessionConfig(
            bind_to_ip=True,
            max_failed_validations=2,
        )
        validator = SessionValidator(config)
        session = Session(
            session_id="test",
            user_id="user-1",
            ip_address="192.168.1.1",
        )
        
        validator.validate(session, ip_address="wrong")
        validator.validate(session, ip_address="wrong")
        
        assert session.status == SessionStatus.LOCKED


# =============================================================================
# Test: SessionManager
# =============================================================================

class TestSessionManager:
    """Test SessionManager."""
    
    def test_creates_session(self, manager):
        """Should create session."""
        session = manager.create("user-1")
        
        assert session is not None
        assert session.user_id == "user-1"
        assert session.is_active is True
    
    def test_gets_session(self, manager):
        """Should get session by ID."""
        session = manager.create("user-1")
        
        found = manager.get(session.session_id)
        
        assert found is not None
        assert found.session_id == session.session_id
    
    def test_validates_session(self, manager):
        """Should validate session."""
        session = manager.create("user-1")
        
        result = manager.validate(session.session_id)
        
        assert result.is_valid is True
    
    def test_regenerates_session(self, manager):
        """Should regenerate session ID."""
        session = manager.create("user-1")
        old_id = session.session_id
        
        new_session = manager.regenerate(old_id)
        
        assert new_session is not None
        assert new_session.session_id != old_id
        assert new_session.user_id == "user-1"
        assert manager.get(old_id) is None
    
    def test_invalidates_session(self, manager):
        """Should invalidate session."""
        session = manager.create("user-1")
        
        success = manager.invalidate(session.session_id)
        
        assert success is True
        assert manager.get(session.session_id) is None
    
    def test_invalidates_all(self, manager):
        """Should invalidate all user sessions."""
        manager.create("user-1")
        manager.create("user-1")
        
        count = manager.invalidate_all("user-1")
        
        assert count == 2
    
    def test_limits_sessions_per_user(self):
        """Should limit sessions per user."""
        config = SessionConfig(max_sessions_per_user=2)
        manager = SessionManager(config)
        
        s1 = manager.create("user-1")
        s2 = manager.create("user-1")
        s3 = manager.create("user-1")
        
        # Oldest should be removed
        assert manager.get(s1.session_id) is None
        assert manager.get(s2.session_id) is not None
        assert manager.get(s3.session_id) is not None
    
    def test_updates_data(self, manager):
        """Should update session data."""
        session = manager.create("user-1")
        
        success = manager.update_data(session.session_id, {"key": "value"})
        
        assert success is True
        assert session.data["key"] == "value"
    
    def test_cleanup_expired(self):
        """Should cleanup expired sessions."""
        config = SessionConfig(idle_timeout_seconds=1)
        manager = SessionManager(config)
        session = manager.create("user-1")
        session.last_accessed_at = time.time() - 10
        
        count = manager.cleanup_expired()
        
        assert count == 1


# =============================================================================
# Test: SessionSecurityService
# =============================================================================

class TestSessionSecurityService:
    """Test SessionSecurityService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        SessionSecurityService._instance = None
        
        s1 = get_session_service()
        s2 = get_session_service()
        
        assert s1 is s2
    
    def test_configure(self):
        """Should configure service."""
        SessionSecurityService._instance = None
        config = SessionConfig(idle_timeout_seconds=300)
        
        service = SessionSecurityService.configure(config)
        
        assert service.config.idle_timeout_seconds == 300
    
    def test_create_session(self, service):
        """Should create session."""
        session = service.create_session("user-1")
        
        assert session is not None
        assert session.user_id == "user-1"
    
    def test_validate_session(self, service):
        """Should validate session."""
        session = service.create_session("user-1")
        
        result = service.validate_session(session.session_id)
        
        assert result.is_valid is True
    
    def test_regenerate_session(self, service):
        """Should regenerate session."""
        session = service.create_session("user-1")
        old_id = session.session_id
        
        new_session = service.regenerate_session(old_id)
        
        assert new_session.session_id != old_id
    
    def test_logout(self, service):
        """Should logout session."""
        session = service.create_session("user-1")
        
        success = service.logout(session.session_id)
        
        assert success is True
    
    def test_logout_all(self, service):
        """Should logout all sessions."""
        service.create_session("user-1")
        service.create_session("user-1")
        
        count = service.logout_all("user-1")
        
        assert count == 2
    
    def test_get_user_sessions(self, service):
        """Should get user sessions."""
        service.create_session("user-1")
        service.create_session("user-1")
        
        sessions = service.get_user_sessions("user-1")
        
        assert len(sessions) == 2
    
    def test_get_cookie_config(self, service):
        """Should get cookie config."""
        config = service.get_cookie_config()
        
        assert config["secure"] is True
        assert config["httponly"] is True
        assert config["samesite"] == "Strict"


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_create_session(self):
        """Should create via convenience function."""
        SessionSecurityService._instance = None
        
        session = create_session("user-1")
        
        assert session is not None
    
    def test_validate_session(self):
        """Should validate via convenience function."""
        SessionSecurityService._instance = None
        session = create_session("user-1")
        
        result = validate_session(session.session_id)
        
        assert result.is_valid is True


# =============================================================================
# Test: Security
# =============================================================================

class TestSecurity:
    """Test security aspects."""
    
    def test_secure_random_ids(self, id_generator):
        """Should use secure random."""
        ids = [id_generator.generate() for _ in range(10)]
        
        # All should be unique
        assert len(set(ids)) == 10
    
    def test_session_fixation_prevention(self, manager):
        """Should prevent session fixation."""
        session = manager.create("user-1")
        old_id = session.session_id
        
        # Simulate privilege escalation
        new_session = manager.regenerate(old_id)
        
        # Old ID should be invalid
        result = manager.validate(old_id)
        assert result.is_valid is False
        
        # New ID should be valid
        result = manager.validate(new_session.session_id)
        assert result.is_valid is True
    
    def test_binding_prevents_hijack(self):
        """Should prevent session hijacking."""
        config = SessionConfig(
            bind_to_ip=True,
            bind_to_user_agent=True,
        )
        manager = SessionManager(config)
        
        session = manager.create(
            "user-1",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )
        
        # Different client should fail
        result = manager.validate(
            session.session_id,
            ip_address="10.0.0.1",
            user_agent="Evil/1.0",
        )
        
        assert result.is_valid is False
