"""
SEC-010: Session Management for RegEngine.

This module provides secure session management with:
- Server-side session storage
- Session ID security (cryptographically random)
- Session timeout and renewal
- Concurrent session limits
- Session binding (IP, User-Agent)
- Secure session cookies
- Session revocation

Usage:
    from shared.session_management import SessionManager, SessionConfig
    
    config = SessionConfig(
        secret_key="session-secret",
        max_age=3600,
        max_concurrent=3,
    )
    
    manager = SessionManager(config)
    
    # Create session
    session = await manager.create_session(user_id="user-123")
    
    # Get session
    session = await manager.get_session(session_id)
    
    # End session
    await manager.end_session(session_id)
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger("session_management")


# =============================================================================
# Configuration
# =============================================================================

class SessionCookieSettings(BaseModel):
    """Cookie settings for session cookies."""
    
    name: str = "regengine_session"
    path: str = "/"
    domain: Optional[str] = None
    secure: bool = True  # HTTPS only
    http_only: bool = True  # Not accessible via JavaScript
    same_site: str = "lax"  # CSRF protection
    
    def to_cookie_params(self) -> dict[str, Any]:
        """Convert to cookie parameters."""
        params = {
            "key": self.name,
            "path": self.path,
            "secure": self.secure,
            "httponly": self.http_only,
            "samesite": self.same_site,
        }
        if self.domain:
            params["domain"] = self.domain
        return params


@dataclass
class SessionConfig:
    """Session management configuration."""
    
    # Session lifetime
    max_age: int = 3600  # 1 hour default
    absolute_timeout: int = 86400  # 24 hours max session lifetime
    idle_timeout: int = 1800  # 30 minutes of inactivity
    
    # Session limits
    max_concurrent: int = 5  # Max sessions per user
    
    # Security settings
    bind_to_ip: bool = False  # Bind session to IP (can cause issues with mobile)
    bind_to_user_agent: bool = True  # Bind to user agent
    rotate_on_auth: bool = True  # New session ID after authentication
    
    # Session ID settings
    session_id_length: int = 32  # Bytes of entropy
    
    # Cookie settings
    cookie: SessionCookieSettings = field(default_factory=SessionCookieSettings)
    
    # Secret for signing (required).
    # SESSION_SECRET must be set in production; if unset the SessionManager
    # constructor will raise ValueError.
    secret_key: Optional[str] = field(default_factory=lambda: os.environ.get("SESSION_SECRET"))
    
    @classmethod
    def development(cls) -> "SessionConfig":
        """Create development configuration."""
        cookie = SessionCookieSettings(secure=False)
        return cls(
            max_age=7200,
            max_concurrent=10,
            bind_to_ip=False,
            cookie=cookie,
            secret_key=os.environ.get("SESSION_SECRET", "dev-only-" + os.urandom(16).hex()),
        )


# =============================================================================
# Session Models
# =============================================================================

class SessionStatus(str, Enum):
    """Session status."""
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    IDLE_TIMEOUT = "idle_timeout"


class Session(BaseModel):
    """Session data model."""
    
    # Identity
    session_id: str
    user_id: str
    tenant_id: Optional[str] = None
    
    # Timestamps
    created_at: float = Field(default_factory=time.time)
    accessed_at: float = Field(default_factory=time.time)
    expires_at: float
    
    # Binding
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    user_agent_hash: Optional[str] = None
    
    # Status
    status: SessionStatus = SessionStatus.ACTIVE
    
    # Session data
    data: dict[str, Any] = Field(default_factory=dict)
    
    # Authentication info
    auth_method: Optional[str] = None  # password, oauth, mfa
    mfa_verified: bool = False
    
    # Permissions snapshot (for fast access checks)
    roles: list[str] = Field(default_factory=list)
    
    @property
    def is_valid(self) -> bool:
        """Check if session is valid."""
        now = time.time()
        return (
            self.status == SessionStatus.ACTIVE
            and now < self.expires_at
        )
    
    @property
    def is_idle_expired(self) -> bool:
        """Check if session has expired due to idle timeout."""
        return False  # Checked externally with config
    
    def update_access(self) -> None:
        """Update last accessed time."""
        self.accessed_at = time.time()


class SessionMetadata(BaseModel):
    """Metadata about a session (for listing)."""
    
    session_id: str
    created_at: float
    accessed_at: float
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    is_current: bool = False


# =============================================================================
# Session ID Generator
# =============================================================================

class SessionIDGenerator:
    """Generate cryptographically secure session IDs."""
    
    @staticmethod
    def generate(num_bytes: int = 32) -> str:
        """Generate a random session ID.
        
        Args:
            num_bytes: Number of random bytes (default 32 = 256 bits)
            
        Returns:
            URL-safe session ID string
        """
        return secrets.token_urlsafe(num_bytes)
    
    @staticmethod
    def hash_user_agent(user_agent: str) -> str:
        """Hash a user agent string for comparison.
        
        Hashing provides some privacy while still allowing binding.
        """
        return hashlib.sha256(user_agent.encode()).hexdigest()[:32]


# =============================================================================
# Session Store Interface
# =============================================================================

class SessionStore(ABC):
    """Abstract base class for session storage."""
    
    @abstractmethod
    async def save(self, session: Session) -> None:
        """Save a session."""
        pass
    
    @abstractmethod
    async def get(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        pass
    
    @abstractmethod
    async def delete(self, session_id: str) -> None:
        """Delete a session."""
        pass
    
    @abstractmethod
    async def get_user_sessions(self, user_id: str) -> list[Session]:
        """Get all sessions for a user."""
        pass
    
    @abstractmethod
    async def delete_user_sessions(self, user_id: str) -> int:
        """Delete all sessions for a user."""
        pass
    
    @abstractmethod
    async def cleanup_expired(self) -> int:
        """Remove expired sessions."""
        pass


class InMemorySessionStore(SessionStore):
    """In-memory session store for development/testing."""
    
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._user_sessions: dict[str, set[str]] = {}
    
    async def save(self, session: Session) -> None:
        """Save a session."""
        self._sessions[session.session_id] = session
        
        if session.user_id not in self._user_sessions:
            self._user_sessions[session.user_id] = set()
        self._user_sessions[session.user_id].add(session.session_id)
    
    async def get(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        return self._sessions.get(session_id)
    
    async def delete(self, session_id: str) -> None:
        """Delete a session."""
        session = self._sessions.pop(session_id, None)
        if session and session.user_id in self._user_sessions:
            self._user_sessions[session.user_id].discard(session_id)
    
    async def get_user_sessions(self, user_id: str) -> list[Session]:
        """Get all sessions for a user."""
        session_ids = self._user_sessions.get(user_id, set())
        return [
            self._sessions[sid]
            for sid in session_ids
            if sid in self._sessions
        ]
    
    async def delete_user_sessions(self, user_id: str) -> int:
        """Delete all sessions for a user."""
        session_ids = self._user_sessions.pop(user_id, set())
        count = 0
        for sid in session_ids:
            if sid in self._sessions:
                del self._sessions[sid]
                count += 1
        return count
    
    async def cleanup_expired(self) -> int:
        """Remove expired sessions."""
        now = time.time()
        expired = [
            sid for sid, session in self._sessions.items()
            if session.expires_at < now or session.status != SessionStatus.ACTIVE
        ]
        
        for sid in expired:
            await self.delete(sid)
        
        return len(expired)


# =============================================================================
# Session Manager
# =============================================================================

class SessionManager:
    """Manages user sessions with security features."""
    
    def __init__(
        self,
        config: Optional[SessionConfig] = None,
        store: Optional[SessionStore] = None,
    ):
        """Initialize session manager.
        
        Args:
            config: Session configuration
            store: Session storage backend
        """
        self._config = config or SessionConfig()
        self._store = store or InMemorySessionStore()
        
        if not self._config.secret_key:
            raise ValueError("Session secret key is required")
    
    async def create_session(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        auth_method: Optional[str] = None,
        roles: Optional[list[str]] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> Session:
        """Create a new session.
        
        Args:
            user_id: User identifier
            tenant_id: Optional tenant identifier
            ip_address: Client IP address
            user_agent: Client user agent
            auth_method: How user authenticated
            roles: User's roles
            data: Initial session data
            
        Returns:
            New session
        """
        # Check concurrent session limit
        await self._enforce_session_limit(user_id)
        
        # Generate session ID
        session_id = SessionIDGenerator.generate(self._config.session_id_length)
        
        # Calculate expiration
        now = time.time()
        expires_at = now + self._config.max_age
        
        # Hash user agent if binding
        user_agent_hash = None
        if user_agent and self._config.bind_to_user_agent:
            user_agent_hash = SessionIDGenerator.hash_user_agent(user_agent)
        
        # Create session
        session = Session(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            created_at=now,
            accessed_at=now,
            expires_at=expires_at,
            ip_address=ip_address if self._config.bind_to_ip else None,
            user_agent=user_agent,
            user_agent_hash=user_agent_hash,
            auth_method=auth_method,
            roles=roles or [],
            data=data or {},
        )
        
        await self._store.save(session)
        
        logger.info(
            "session_created",
            session_id=session_id[:8] + "...",
            user_id=user_id,
        )
        
        return session
    
    async def get_session(
        self,
        session_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Optional[Session]:
        """Get and validate a session.
        
        Args:
            session_id: Session identifier
            ip_address: Current IP (for binding check)
            user_agent: Current user agent (for binding check)
            
        Returns:
            Session if valid, None otherwise
        """
        session = await self._store.get(session_id)
        
        if session is None:
            logger.debug("session_not_found", session_id=session_id[:8] + "...")
            return None
        
        # Check status
        if session.status != SessionStatus.ACTIVE:
            logger.debug(
                "session_invalid_status",
                session_id=session_id[:8] + "...",
                status=session.status,
            )
            return None
        
        # Check expiration
        now = time.time()
        if now >= session.expires_at:
            session.status = SessionStatus.EXPIRED
            await self._store.save(session)
            logger.debug("session_expired", session_id=session_id[:8] + "...")
            return None
        
        # Check idle timeout
        if now - session.accessed_at > self._config.idle_timeout:
            session.status = SessionStatus.IDLE_TIMEOUT
            await self._store.save(session)
            logger.debug("session_idle_timeout", session_id=session_id[:8] + "...")
            return None
        
        # Check absolute timeout
        if now - session.created_at > self._config.absolute_timeout:
            session.status = SessionStatus.EXPIRED
            await self._store.save(session)
            logger.debug("session_absolute_timeout", session_id=session_id[:8] + "...")
            return None
        
        # Check IP binding
        if self._config.bind_to_ip and session.ip_address:
            if ip_address and ip_address != session.ip_address:
                logger.warning(
                    "session_ip_mismatch",
                    session_id=session_id[:8] + "...",
                    expected=session.ip_address,
                    actual=ip_address,
                )
                return None
        
        # Check user agent binding
        if self._config.bind_to_user_agent and session.user_agent_hash:
            if user_agent:
                current_hash = SessionIDGenerator.hash_user_agent(user_agent)
                if current_hash != session.user_agent_hash:
                    logger.warning(
                        "session_user_agent_mismatch",
                        session_id=session_id[:8] + "...",
                    )
                    return None
        
        # Update last accessed
        session.update_access()
        await self._store.save(session)
        
        return session
    
    async def refresh_session(self, session: Session) -> Session:
        """Refresh session with new expiration.
        
        Args:
            session: Session to refresh
            
        Returns:
            Updated session
        """
        now = time.time()
        
        # Don't extend beyond absolute timeout
        max_expires = session.created_at + self._config.absolute_timeout
        new_expires = min(now + self._config.max_age, max_expires)
        
        session.expires_at = new_expires
        session.accessed_at = now
        await self._store.save(session)
        
        logger.debug(
            "session_refreshed",
            session_id=session.session_id[:8] + "...",
        )
        
        return session
    
    async def rotate_session(
        self,
        old_session: Session,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Session:
        """Rotate session ID (create new, invalidate old).
        
        Use after authentication state changes (login, privilege escalation).
        
        Args:
            old_session: Current session
            ip_address: Current IP
            user_agent: Current user agent
            
        Returns:
            New session with same data
        """
        # Create new session with same data
        new_session = await self.create_session(
            user_id=old_session.user_id,
            tenant_id=old_session.tenant_id,
            ip_address=ip_address or old_session.ip_address,
            user_agent=user_agent or old_session.user_agent,
            auth_method=old_session.auth_method,
            roles=old_session.roles,
            data=old_session.data.copy(),
        )
        
        # Copy MFA status
        new_session.mfa_verified = old_session.mfa_verified
        await self._store.save(new_session)
        
        # Invalidate old session
        old_session.status = SessionStatus.REVOKED
        await self._store.save(old_session)
        
        logger.info(
            "session_rotated",
            old_session=old_session.session_id[:8] + "...",
            new_session=new_session.session_id[:8] + "...",
        )
        
        return new_session
    
    async def end_session(self, session_id: str) -> bool:
        """End a session (logout).
        
        Args:
            session_id: Session to end
            
        Returns:
            True if session was ended
        """
        session = await self._store.get(session_id)
        if session is None:
            return False
        
        session.status = SessionStatus.REVOKED
        await self._store.save(session)
        await self._store.delete(session_id)
        
        logger.info(
            "session_ended",
            session_id=session_id[:8] + "...",
            user_id=session.user_id,
        )
        
        return True
    
    async def end_all_sessions(self, user_id: str, except_session: Optional[str] = None) -> int:
        """End all sessions for a user.
        
        Args:
            user_id: User identifier
            except_session: Session to keep (optional)
            
        Returns:
            Number of sessions ended
        """
        sessions = await self._store.get_user_sessions(user_id)
        count = 0
        
        for session in sessions:
            if except_session and session.session_id == except_session:
                continue
            
            session.status = SessionStatus.REVOKED
            await self._store.save(session)
            await self._store.delete(session.session_id)
            count += 1
        
        logger.info(
            "sessions_ended_all",
            user_id=user_id,
            count=count,
        )
        
        return count
    
    async def list_user_sessions(
        self,
        user_id: str,
        current_session_id: Optional[str] = None,
    ) -> list[SessionMetadata]:
        """List all active sessions for a user.
        
        Args:
            user_id: User identifier
            current_session_id: Current session (for marking)
            
        Returns:
            List of session metadata
        """
        sessions = await self._store.get_user_sessions(user_id)
        
        return [
            SessionMetadata(
                session_id=s.session_id,
                created_at=s.created_at,
                accessed_at=s.accessed_at,
                ip_address=s.ip_address,
                user_agent=s.user_agent,
                is_current=s.session_id == current_session_id,
            )
            for s in sessions
            if s.status == SessionStatus.ACTIVE
        ]
    
    async def update_session_data(
        self,
        session_id: str,
        data: dict[str, Any],
    ) -> Optional[Session]:
        """Update session data.
        
        Args:
            session_id: Session identifier
            data: Data to merge into session
            
        Returns:
            Updated session
        """
        session = await self._store.get(session_id)
        if session is None or session.status != SessionStatus.ACTIVE:
            return None
        
        session.data.update(data)
        session.update_access()
        await self._store.save(session)
        
        return session
    
    async def set_mfa_verified(self, session_id: str) -> Optional[Session]:
        """Mark session as MFA verified.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Updated session
        """
        session = await self._store.get(session_id)
        if session is None or session.status != SessionStatus.ACTIVE:
            return None
        
        session.mfa_verified = True
        session.update_access()
        await self._store.save(session)
        
        logger.info(
            "session_mfa_verified",
            session_id=session_id[:8] + "...",
        )
        
        return session
    
    async def cleanup_expired_sessions(self) -> int:
        """Cleanup expired sessions.
        
        Returns:
            Number of sessions cleaned up
        """
        count = await self._store.cleanup_expired()
        if count > 0:
            logger.info("sessions_cleaned_up", count=count)
        return count
    
    def sign_session_id(self, session_id: str) -> str:
        """Sign a session ID for secure cookie storage.
        
        Args:
            session_id: Session ID to sign
            
        Returns:
            Signed session ID
        """
        signature = hmac.new(
            self._config.secret_key.encode(),
            session_id.encode(),
            hashlib.sha256,
        ).hexdigest()[:32]
        
        return f"{session_id}.{signature}"
    
    def verify_signed_session_id(self, signed_id: str) -> Optional[str]:
        """Verify and extract session ID from signed value.
        
        Args:
            signed_id: Signed session ID
            
        Returns:
            Session ID if valid, None otherwise
        """
        try:
            session_id, signature = signed_id.rsplit(".", 1)
        except ValueError:
            return None
        
        expected_signature = hmac.new(
            self._config.secret_key.encode(),
            session_id.encode(),
            hashlib.sha256,
        ).hexdigest()[:32]
        
        if hmac.compare_digest(signature, expected_signature):
            return session_id
        
        return None
    
    async def _enforce_session_limit(self, user_id: str) -> None:
        """Enforce max concurrent sessions per user."""
        sessions = await self._store.get_user_sessions(user_id)
        active = [s for s in sessions if s.status == SessionStatus.ACTIVE]
        
        if len(active) >= self._config.max_concurrent:
            # Remove oldest sessions
            sorted_sessions = sorted(active, key=lambda s: s.created_at)
            to_remove = len(active) - self._config.max_concurrent + 1
            
            for session in sorted_sessions[:to_remove]:
                session.status = SessionStatus.REVOKED
                await self._store.save(session)
                await self._store.delete(session.session_id)
                
                logger.info(
                    "session_removed_limit",
                    session_id=session.session_id[:8] + "...",
                    user_id=user_id,
                )
    
    def get_cookie_settings(self, max_age: Optional[int] = None) -> dict[str, Any]:
        """Get cookie parameters for session cookie.
        
        Args:
            max_age: Override max age (for "remember me")
            
        Returns:
            Cookie parameters dict
        """
        params = self._config.cookie.to_cookie_params()
        params["max_age"] = max_age or self._config.max_age
        return params
