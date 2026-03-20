"""
SEC-043: Session Security.

Secure session management with ID generation, validation,
expiration, and fixation prevention.
"""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class SessionStatus(str, Enum):
    """Session status."""
    ACTIVE = "active"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    LOCKED = "locked"


class SessionEvent(str, Enum):
    """Session events for audit."""
    CREATED = "created"
    ACCESSED = "accessed"
    REFRESHED = "refreshed"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"
    LOCKED = "locked"
    UNLOCKED = "unlocked"


@dataclass
class SessionConfig:
    """Configuration for session security."""
    
    # ID generation
    session_id_length: int = 32
    use_secure_random: bool = True
    
    # Expiration
    idle_timeout_seconds: int = 1800  # 30 minutes
    absolute_timeout_seconds: int = 86400  # 24 hours
    
    # Security
    regenerate_on_privilege_change: bool = True
    bind_to_ip: bool = False
    bind_to_user_agent: bool = False
    
    # Limits
    max_sessions_per_user: int = 5
    max_failed_validations: int = 3
    
    # Cookie settings
    cookie_name: str = "session_id"
    cookie_secure: bool = True
    cookie_http_only: bool = True
    cookie_same_site: str = "Strict"


@dataclass
class Session:
    """Represents a user session."""
    
    session_id: str
    user_id: str
    status: SessionStatus = SessionStatus.ACTIVE
    
    # Timestamps
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    
    # Binding
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    # Metadata
    data: dict = field(default_factory=dict)
    
    # Security
    failed_validations: int = 0
    
    @property
    def is_active(self) -> bool:
        """Check if session is active."""
        return self.status == SessionStatus.ACTIVE
    
    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        if self.expires_at:
            return time.time() > self.expires_at
        return False
    
    def touch(self) -> None:
        """Update last accessed time."""
        self.last_accessed_at = time.time()


@dataclass
class SessionValidationResult:
    """Result of session validation."""
    
    is_valid: bool
    session: Optional[Session] = None
    error: Optional[str] = None


class SessionIdGenerator:
    """Generates secure session IDs."""
    
    def __init__(self, config: Optional[SessionConfig] = None):
        self.config = config or SessionConfig()
    
    def generate(self) -> str:
        """Generate a new session ID."""
        if self.config.use_secure_random:
            return secrets.token_urlsafe(self.config.session_id_length)
        else:
            # Fallback (not recommended)
            import uuid
            return str(uuid.uuid4()).replace("-", "")
    
    def generate_with_fingerprint(
        self,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Generate session ID with fingerprint.
        
        Returns tuple of (session_id, fingerprint).
        """
        session_id = self.generate()
        
        # Create fingerprint from binding data
        fingerprint_data = f"{ip_address or ''}{user_agent or ''}"
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]
        
        return session_id, fingerprint


class SessionValidator:
    """Validates sessions."""
    
    def __init__(self, config: Optional[SessionConfig] = None):
        self.config = config or SessionConfig()
    
    def validate(
        self,
        session: Session,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> SessionValidationResult:
        """Validate a session."""
        # Check status
        if session.status == SessionStatus.INVALIDATED:
            return SessionValidationResult(
                is_valid=False,
                session=session,
                error="Session has been invalidated",
            )
        
        if session.status == SessionStatus.LOCKED:
            return SessionValidationResult(
                is_valid=False,
                session=session,
                error="Session is locked",
            )
        
        # Check expiration
        if session.is_expired:
            session.status = SessionStatus.EXPIRED
            return SessionValidationResult(
                is_valid=False,
                session=session,
                error="Session has expired",
            )
        
        # Check idle timeout
        idle_time = time.time() - session.last_accessed_at
        if idle_time > self.config.idle_timeout_seconds:
            session.status = SessionStatus.EXPIRED
            return SessionValidationResult(
                is_valid=False,
                session=session,
                error="Session idle timeout",
            )
        
        # Check absolute timeout
        session_age = time.time() - session.created_at
        if session_age > self.config.absolute_timeout_seconds:
            session.status = SessionStatus.EXPIRED
            return SessionValidationResult(
                is_valid=False,
                session=session,
                error="Session absolute timeout",
            )
        
        # Check IP binding
        if self.config.bind_to_ip and session.ip_address:
            if ip_address != session.ip_address:
                session.failed_validations += 1
                if session.failed_validations >= self.config.max_failed_validations:
                    session.status = SessionStatus.LOCKED
                return SessionValidationResult(
                    is_valid=False,
                    session=session,
                    error="IP address mismatch",
                )
        
        # Check user agent binding
        if self.config.bind_to_user_agent and session.user_agent:
            if user_agent != session.user_agent:
                session.failed_validations += 1
                if session.failed_validations >= self.config.max_failed_validations:
                    session.status = SessionStatus.LOCKED
                return SessionValidationResult(
                    is_valid=False,
                    session=session,
                    error="User agent mismatch",
                )
        
        # Update access time
        session.touch()
        session.failed_validations = 0
        
        return SessionValidationResult(is_valid=True, session=session)


class SessionManager:
    """Manages session lifecycle."""
    
    def __init__(self, config: Optional[SessionConfig] = None):
        self.config = config or SessionConfig()
        self.id_generator = SessionIdGenerator(self.config)
        self.validator = SessionValidator(self.config)
        
        # In-memory storage
        self._sessions: dict[str, Session] = {}
        self._user_sessions: dict[str, set[str]] = {}
    
    def create(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        data: Optional[dict] = None,
    ) -> Session:
        """Create a new session."""
        # Check max sessions per user
        user_session_ids = self._user_sessions.get(user_id, set())
        if len(user_session_ids) >= self.config.max_sessions_per_user:
            # Remove oldest session
            oldest = self._get_oldest_session(user_session_ids)
            if oldest:
                self.invalidate(oldest)
        
        # Generate session ID
        session_id = self.id_generator.generate()
        
        # Calculate expiration
        expires_at = time.time() + self.config.absolute_timeout_seconds
        
        # Create session
        session = Session(
            session_id=session_id,
            user_id=user_id,
            expires_at=expires_at,
            ip_address=ip_address if self.config.bind_to_ip else None,
            user_agent=user_agent if self.config.bind_to_user_agent else None,
            data=data or {},
        )
        
        # Store session
        self._sessions[session_id] = session
        
        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = set()
        self._user_sessions[user_id].add(session_id)
        
        return session
    
    def _get_oldest_session(self, session_ids: set[str]) -> Optional[str]:
        """Get oldest session ID from set."""
        oldest_id = None
        oldest_time = float("inf")
        
        for sid in session_ids:
            session = self._sessions.get(sid)
            if session and session.created_at < oldest_time:
                oldest_time = session.created_at
                oldest_id = sid
        
        return oldest_id
    
    def get(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        return self._sessions.get(session_id)
    
    def validate(
        self,
        session_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> SessionValidationResult:
        """Validate a session by ID."""
        session = self._sessions.get(session_id)
        
        if not session:
            return SessionValidationResult(
                is_valid=False,
                error="Session not found",
            )
        
        return self.validator.validate(session, ip_address, user_agent)
    
    def regenerate(
        self,
        session_id: str,
    ) -> Optional[Session]:
        """
        Regenerate session ID (for fixation prevention).
        
        Returns new session or None if not found.
        """
        session = self._sessions.get(session_id)
        
        if not session:
            return None
        
        # Generate new ID
        new_session_id = self.id_generator.generate()
        
        # Update references
        del self._sessions[session_id]
        session.session_id = new_session_id
        self._sessions[new_session_id] = session
        
        # Update user sessions
        if session.user_id in self._user_sessions:
            self._user_sessions[session.user_id].discard(session_id)
            self._user_sessions[session.user_id].add(new_session_id)
        
        return session
    
    def invalidate(self, session_id: str) -> bool:
        """Invalidate a session."""
        session = self._sessions.get(session_id)
        
        if not session:
            return False
        
        session.status = SessionStatus.INVALIDATED
        
        # Remove from storage
        del self._sessions[session_id]
        
        if session.user_id in self._user_sessions:
            self._user_sessions[session.user_id].discard(session_id)
        
        return True
    
    def invalidate_all(self, user_id: str) -> int:
        """Invalidate all sessions for user. Returns count."""
        session_ids = self._user_sessions.get(user_id, set()).copy()
        count = 0
        
        for session_id in session_ids:
            if self.invalidate(session_id):
                count += 1
        
        return count
    
    def update_data(
        self,
        session_id: str,
        data: dict,
    ) -> bool:
        """Update session data."""
        session = self._sessions.get(session_id)
        
        if not session or not session.is_active:
            return False
        
        session.data.update(data)
        return True
    
    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count removed."""
        expired = []
        
        for session_id, session in self._sessions.items():
            result = self.validator.validate(session)
            if not result.is_valid:
                expired.append(session_id)
        
        for session_id in expired:
            self.invalidate(session_id)
        
        return len(expired)


class SessionSecurityService:
    """Comprehensive session security service."""
    
    _instance: Optional["SessionSecurityService"] = None
    
    def __init__(self, config: Optional[SessionConfig] = None):
        self.config = config or SessionConfig()
        self.manager = SessionManager(self.config)
    
    @classmethod
    def get_instance(cls) -> "SessionSecurityService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(cls, config: SessionConfig) -> "SessionSecurityService":
        """Configure and return singleton."""
        cls._instance = cls(config)
        return cls._instance
    
    def create_session(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        data: Optional[dict] = None,
    ) -> Session:
        """Create a new session."""
        return self.manager.create(user_id, ip_address, user_agent, data)
    
    def validate_session(
        self,
        session_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> SessionValidationResult:
        """Validate a session."""
        return self.manager.validate(session_id, ip_address, user_agent)
    
    def regenerate_session(self, session_id: str) -> Optional[Session]:
        """Regenerate session ID (fixation prevention)."""
        return self.manager.regenerate(session_id)
    
    def logout(self, session_id: str) -> bool:
        """Logout (invalidate session)."""
        return self.manager.invalidate(session_id)
    
    def logout_all(self, user_id: str) -> int:
        """Logout all sessions for user."""
        return self.manager.invalidate_all(user_id)
    
    def get_user_sessions(self, user_id: str) -> list[Session]:
        """Get all active sessions for user."""
        session_ids = self.manager._user_sessions.get(user_id, set())
        sessions = []
        
        for session_id in session_ids:
            session = self.manager.get(session_id)
            if session and session.is_active:
                sessions.append(session)
        
        return sessions
    
    def get_cookie_config(self) -> dict:
        """Get cookie configuration for session."""
        return {
            "name": self.config.cookie_name,
            "secure": self.config.cookie_secure,
            "httponly": self.config.cookie_http_only,
            "samesite": self.config.cookie_same_site,
            "max_age": self.config.absolute_timeout_seconds,
        }


# Convenience functions
def get_session_service() -> SessionSecurityService:
    """Get session service instance."""
    return SessionSecurityService.get_instance()


def create_session(
    user_id: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Session:
    """Create a new session."""
    return get_session_service().create_session(
        user_id, ip_address, user_agent
    )


def validate_session(
    session_id: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> SessionValidationResult:
    """Validate a session."""
    return get_session_service().validate_session(
        session_id, ip_address, user_agent
    )
