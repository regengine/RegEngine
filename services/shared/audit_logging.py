# ============================================================
# UNSAFE ZONE: This file (1069 lines) mixes application security
# audit (login, access control) with compliance audit (data
# modification, export events), plus tamper-evident hash/HMAC
# integrity logic, logging decorators, and report generation.
# The trust-critical integrity code (hashing/chaining) is
# entangled with routine application logging concerns.
# Refactoring target — see PHASE 3.4 in REGENGINE_CODEBASE_REMEDIATION_PRD.md
# Changes to integrity logic risk silent audit chain corruption.
# ============================================================
"""
SEC-016: Comprehensive Audit Logging.

This module provides a secure, tamper-evident audit logging system
for tracking security-relevant events across the application.
"""

import functools
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, TypeVar, Union


logger = logging.getLogger(__name__)


# =============================================================================
# Audit Event Types
# =============================================================================

class AuditEventCategory(str, Enum):
    """Categories of audit events."""
    
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    CONFIGURATION = "configuration"
    SECURITY = "security"
    SYSTEM = "system"
    ADMIN = "admin"
    API = "api"
    FILE = "file"


class AuditEventType(str, Enum):
    """Specific audit event types."""
    
    # Authentication events
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    PASSWORD_CHANGE = "password_change"
    PASSWORD_RESET_REQUEST = "password_reset_request"
    PASSWORD_RESET_COMPLETE = "password_reset_complete"
    MFA_ENABLED = "mfa_enabled"
    MFA_DISABLED = "mfa_disabled"
    MFA_CHALLENGE = "mfa_challenge"
    SESSION_CREATED = "session_created"
    SESSION_EXPIRED = "session_expired"
    SESSION_REVOKED = "session_revoked"
    TOKEN_ISSUED = "token_issued"
    TOKEN_REVOKED = "token_revoked"
    TOKEN_REFRESH = "token_refresh"
    
    # Authorization events
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_REVOKED = "permission_revoked"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_REMOVED = "role_removed"
    
    # Data access events
    DATA_READ = "data_read"
    DATA_SEARCH = "data_search"
    DATA_EXPORT = "data_export"
    SENSITIVE_DATA_ACCESS = "sensitive_data_access"
    PII_ACCESS = "pii_access"
    
    # Data modification events
    DATA_CREATE = "data_create"
    DATA_UPDATE = "data_update"
    DATA_DELETE = "data_delete"
    DATA_BULK_OPERATION = "data_bulk_operation"
    
    # Configuration events
    CONFIG_CHANGE = "config_change"
    SETTINGS_UPDATE = "settings_update"
    FEATURE_ENABLED = "feature_enabled"
    FEATURE_DISABLED = "feature_disabled"
    
    # Security events
    SECURITY_ALERT = "security_alert"
    INTRUSION_ATTEMPT = "intrusion_attempt"
    INJECTION_ATTEMPT = "injection_attempt"
    XSS_ATTEMPT = "xss_attempt"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    IP_BLOCKED = "ip_blocked"
    API_KEY_COMPROMISED = "api_key_compromised"
    
    # System events
    SYSTEM_START = "system_start"
    SYSTEM_SHUTDOWN = "system_shutdown"
    SERVICE_HEALTH = "service_health"
    ERROR = "error"
    
    # Admin events
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    USER_SUSPENDED = "user_suspended"
    USER_ACTIVATED = "user_activated"
    TENANT_CREATED = "tenant_created"
    TENANT_UPDATED = "tenant_updated"
    TENANT_DELETED = "tenant_deleted"
    
    # API events
    API_CALL = "api_call"
    API_ERROR = "api_error"
    WEBHOOK_SENT = "webhook_sent"
    WEBHOOK_RECEIVED = "webhook_received"
    
    # File events
    FILE_UPLOAD = "file_upload"
    FILE_DOWNLOAD = "file_download"
    FILE_DELETE = "file_delete"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""
    
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# =============================================================================
# Audit Event Data Classes
# =============================================================================

@dataclass
class AuditActor:
    """The entity performing the action."""
    
    actor_id: str
    actor_type: str = "user"  # user, service, system, api_key
    username: Optional[str] = None
    email: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    tenant_id: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class AuditResource:
    """The resource being acted upon."""
    
    resource_type: str  # e.g., "user", "document", "setting"
    resource_id: str
    resource_name: Optional[str] = None
    tenant_id: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
        }
        if self.resource_name:
            result["resource_name"] = self.resource_name
        if self.tenant_id:
            result["tenant_id"] = self.tenant_id
        if self.attributes:
            result["attributes"] = self.attributes
        return result


@dataclass
class AuditContext:
    """Additional context for the audit event."""
    
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    environment: Optional[str] = None
    service_name: Optional[str] = None
    service_version: Optional[str] = None
    endpoint: Optional[str] = None
    http_method: Optional[str] = None
    http_status: Optional[int] = None
    duration_ms: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {k: v for k, v in asdict(self).items() if v is not None and v != {}}


@dataclass
class AuditEvent:
    """A complete audit event record."""
    
    event_id: str
    timestamp: datetime
    event_type: AuditEventType
    category: AuditEventCategory
    severity: AuditSeverity
    actor: AuditActor
    action: str
    outcome: str  # "success", "failure", "error"
    resource: Optional[AuditResource] = None
    context: Optional[AuditContext] = None
    message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    integrity_hash: Optional[str] = None
    previous_hash: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "category": self.category.value,
            "severity": self.severity.value,
            "actor": self.actor.to_dict(),
            "action": self.action,
            "outcome": self.outcome,
            "resource": self.resource.to_dict() if self.resource else None,
            "context": self.context.to_dict() if self.context else None,
            "message": self.message,
            "details": self.details,
            "tags": self.tags,
            "integrity_hash": self.integrity_hash,
            "previous_hash": self.previous_hash,
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


# =============================================================================
# Integrity Verification
# =============================================================================

class AuditIntegrity:
    """Ensure audit log integrity with hash chains."""
    
    def __init__(self, secret_key: Optional[str] = None):
        """Initialize integrity checker.
        
        Args:
            secret_key: Secret key for HMAC (uses env var if not provided)
        """
        resolved = secret_key or os.environ.get("AUDIT_INTEGRITY_KEY")
        if not resolved:
            raise ValueError(
                "Audit integrity key is required. Set the AUDIT_INTEGRITY_KEY "
                "environment variable or pass secret_key explicitly."
            )
        self._secret_key = resolved.encode()
        self._last_hash: Optional[str] = None
    
    def compute_hash(self, event: AuditEvent) -> str:
        """Compute integrity hash for an event.
        
        Args:
            event: Audit event to hash
            
        Returns:
            Hex-encoded HMAC hash
        """
        # Create canonical representation (excluding hash fields)
        canonical = {
            "event_id": event.event_id,
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type.value,
            "category": event.category.value,
            "actor": event.actor.to_dict(),
            "action": event.action,
            "outcome": event.outcome,
            "previous_hash": event.previous_hash,
        }
        
        if event.resource:
            canonical["resource"] = event.resource.to_dict()
        if event.details:
            canonical["details"] = event.details
        
        data = json.dumps(canonical, sort_keys=True, default=str)
        
        return hmac.new(
            self._secret_key,
            data.encode(),
            hashlib.sha256
        ).hexdigest()
    
    def sign_event(self, event: AuditEvent) -> AuditEvent:
        """Sign an event with integrity hash.
        
        Args:
            event: Event to sign
            
        Returns:
            Event with integrity hash set
        """
        event.previous_hash = self._last_hash
        event.integrity_hash = self.compute_hash(event)
        self._last_hash = event.integrity_hash
        return event
    
    def verify_event(self, event: AuditEvent) -> bool:
        """Verify an event's integrity.
        
        Args:
            event: Event to verify
            
        Returns:
            True if integrity hash is valid
        """
        if not event.integrity_hash:
            return False
        
        expected = self.compute_hash(event)
        return hmac.compare_digest(event.integrity_hash, expected)
    
    def verify_chain(self, events: List[AuditEvent]) -> bool:
        """Verify integrity of an event chain.
        
        Args:
            events: List of events in order
            
        Returns:
            True if chain is valid
        """
        if not events:
            return True
        
        previous_hash = None
        
        for event in events:
            # Check previous hash reference
            if event.previous_hash != previous_hash:
                logger.warning(
                    "Audit chain broken at event %s",
                    event.event_id,
                )
                return False
            
            # Verify event integrity
            if not self.verify_event(event):
                logger.warning(
                    "Audit event integrity failed: %s",
                    event.event_id,
                )
                return False
            
            previous_hash = event.integrity_hash
        
        return True


# =============================================================================
# Audit Storage Backends
# =============================================================================

class AuditStorageBackend(ABC):
    """Abstract base class for audit storage backends."""
    
    @abstractmethod
    async def store(self, event: AuditEvent) -> bool:
        """Store an audit event.
        
        Args:
            event: Event to store
            
        Returns:
            True if stored successfully
        """
        pass
    
    @abstractmethod
    async def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[AuditEventType]] = None,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        severity: Optional[AuditSeverity] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        """Query audit events.
        
        Args:
            Various filter parameters
            
        Returns:
            List of matching events
        """
        pass
    
    @abstractmethod
    async def get_by_id(self, event_id: str) -> Optional[AuditEvent]:
        """Get an event by ID.
        
        Args:
            event_id: Event ID
            
        Returns:
            Event if found
        """
        pass


class InMemoryAuditStorage(AuditStorageBackend):
    """In-memory audit storage for testing."""
    
    def __init__(self, max_events: int = 10000):
        """Initialize in-memory storage.
        
        Args:
            max_events: Maximum events to store
        """
        self._events: List[AuditEvent] = []
        self._max_events = max_events
        self._events_by_id: Dict[str, AuditEvent] = {}
    
    async def store(self, event: AuditEvent) -> bool:
        """Store an event."""
        self._events.append(event)
        self._events_by_id[event.event_id] = event
        
        # Trim if needed
        if len(self._events) > self._max_events:
            removed = self._events.pop(0)
            del self._events_by_id[removed.event_id]
        
        return True
    
    async def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[AuditEventType]] = None,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        severity: Optional[AuditSeverity] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        """Query events with filters."""
        results = []
        
        for event in self._events:
            # Apply filters
            if start_time and event.timestamp < start_time:
                continue
            if end_time and event.timestamp > end_time:
                continue
            if event_types and event.event_type not in event_types:
                continue
            if actor_id and event.actor.actor_id != actor_id:
                continue
            if resource_type and (
                not event.resource or 
                event.resource.resource_type != resource_type
            ):
                continue
            if resource_id and (
                not event.resource or 
                event.resource.resource_id != resource_id
            ):
                continue
            if tenant_id and event.actor.tenant_id != tenant_id:
                continue
            if severity and event.severity != severity:
                continue
            
            results.append(event)
        
        # Apply pagination
        return results[offset:offset + limit]
    
    async def get_by_id(self, event_id: str) -> Optional[AuditEvent]:
        """Get event by ID."""
        return self._events_by_id.get(event_id)
    
    def clear(self) -> None:
        """Clear all events."""
        self._events.clear()
        self._events_by_id.clear()


# =============================================================================
# Audit Logger
# =============================================================================

class AuditLogger:
    """Main audit logging interface."""
    
    _instance: Optional["AuditLogger"] = None
    
    def __init__(
        self,
        storage: Optional[AuditStorageBackend] = None,
        integrity: Optional[AuditIntegrity] = None,
        service_name: str = "regengine",
        environment: str = "development",
    ):
        """Initialize audit logger.
        
        Args:
            storage: Storage backend
            integrity: Integrity checker
            service_name: Name of the service
            environment: Environment name
        """
        self._storage = storage or InMemoryAuditStorage()
        self._integrity = integrity or AuditIntegrity()
        self._service_name = service_name
        self._environment = environment
        self._hooks: List[Callable[[AuditEvent], None]] = []
    
    @classmethod
    def get_instance(cls) -> "AuditLogger":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(
        cls,
        storage: Optional[AuditStorageBackend] = None,
        integrity: Optional[AuditIntegrity] = None,
        service_name: str = "regengine",
        environment: str = "development",
    ) -> "AuditLogger":
        """Configure and return singleton instance."""
        cls._instance = cls(
            storage=storage,
            integrity=integrity,
            service_name=service_name,
            environment=environment,
        )
        return cls._instance
    
    def add_hook(self, hook: Callable[[AuditEvent], None]) -> None:
        """Add a hook to be called after each event is logged."""
        self._hooks.append(hook)
    
    def _create_event(
        self,
        event_type: AuditEventType,
        category: AuditEventCategory,
        severity: AuditSeverity,
        actor: AuditActor,
        action: str,
        outcome: str,
        resource: Optional[AuditResource] = None,
        context: Optional[AuditContext] = None,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> AuditEvent:
        """Create an audit event."""
        # Create context if not provided
        if context is None:
            context = AuditContext()
        
        context.service_name = self._service_name
        context.environment = self._environment
        
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            category=category,
            severity=severity,
            actor=actor,
            action=action,
            outcome=outcome,
            resource=resource,
            context=context,
            message=message,
            details=details or {},
            tags=tags or [],
        )
        
        # Sign the event
        return self._integrity.sign_event(event)
    
    async def log(
        self,
        event_type: AuditEventType,
        category: AuditEventCategory,
        severity: AuditSeverity,
        actor: AuditActor,
        action: str,
        outcome: str,
        resource: Optional[AuditResource] = None,
        context: Optional[AuditContext] = None,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> AuditEvent:
        """Log an audit event.
        
        Args:
            event_type: Type of event
            category: Event category
            severity: Event severity
            actor: Who performed the action
            action: What action was performed
            outcome: Result of the action
            resource: Resource acted upon
            context: Additional context
            message: Human-readable message
            details: Additional details
            tags: Event tags
            
        Returns:
            The logged event
        """
        event = self._create_event(
            event_type=event_type,
            category=category,
            severity=severity,
            actor=actor,
            action=action,
            outcome=outcome,
            resource=resource,
            context=context,
            message=message,
            details=details,
            tags=tags,
        )
        
        # Store the event
        await self._storage.store(event)
        
        # Call hooks
        for hook in self._hooks:
            try:
                hook(event)
            except Exception as e:
                logger.error("Audit hook error: %s", e)
        
        # Also log to standard logger for visibility
        logger.info(
            "AUDIT: [%s] %s - %s by %s: %s",
            event.severity.value.upper(),
            event.event_type.value,
            event.action,
            event.actor.actor_id,
            event.outcome,
        )
        
        return event
    
    async def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[AuditEventType]] = None,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        severity: Optional[AuditSeverity] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        """Query audit events."""
        return await self._storage.query(
            start_time=start_time,
            end_time=end_time,
            event_types=event_types,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            tenant_id=tenant_id,
            severity=severity,
            limit=limit,
            offset=offset,
        )
    
    async def get_event(self, event_id: str) -> Optional[AuditEvent]:
        """Get an event by ID."""
        return await self._storage.get_by_id(event_id)
    
    # =========================================================================
    # Convenience Methods
    # =========================================================================
    
    async def log_login_success(
        self,
        user_id: str,
        username: str,
        ip_address: str,
        user_agent: Optional[str] = None,
        tenant_id: Optional[str] = None,
        mfa_used: bool = False,
    ) -> AuditEvent:
        """Log successful login."""
        return await self.log(
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=AuditActor(
                actor_id=user_id,
                actor_type="user",
                username=username,
                ip_address=ip_address,
                user_agent=user_agent,
                tenant_id=tenant_id,
            ),
            action="login",
            outcome="success",
            message=f"User {username} logged in successfully",
            details={"mfa_used": mfa_used},
            tags=["authentication"],
        )
    
    async def log_login_failure(
        self,
        username: str,
        ip_address: str,
        reason: str,
        user_agent: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> AuditEvent:
        """Log failed login attempt."""
        return await self.log(
            event_type=AuditEventType.LOGIN_FAILURE,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.WARNING,
            actor=AuditActor(
                actor_id=f"unknown:{username}",
                actor_type="user",
                username=username,
                ip_address=ip_address,
                user_agent=user_agent,
                tenant_id=tenant_id,
            ),
            action="login",
            outcome="failure",
            message=f"Login failed for {username}: {reason}",
            details={"reason": reason},
            tags=["authentication", "security"],
        )
    
    async def log_access_denied(
        self,
        actor: AuditActor,
        resource: AuditResource,
        required_permission: str,
        context: Optional[AuditContext] = None,
    ) -> AuditEvent:
        """Log access denied event."""
        return await self.log(
            event_type=AuditEventType.ACCESS_DENIED,
            category=AuditEventCategory.AUTHORIZATION,
            severity=AuditSeverity.WARNING,
            actor=actor,
            action="access",
            outcome="denied",
            resource=resource,
            context=context,
            message=f"Access denied: {required_permission} on {resource.resource_type}/{resource.resource_id}",
            details={"required_permission": required_permission},
            tags=["authorization", "security"],
        )
    
    async def log_data_access(
        self,
        actor: AuditActor,
        resource: AuditResource,
        access_type: str = "read",
        fields_accessed: Optional[List[str]] = None,
        context: Optional[AuditContext] = None,
    ) -> AuditEvent:
        """Log data access event."""
        return await self.log(
            event_type=AuditEventType.DATA_READ,
            category=AuditEventCategory.DATA_ACCESS,
            severity=AuditSeverity.INFO,
            actor=actor,
            action=access_type,
            outcome="success",
            resource=resource,
            context=context,
            message=f"Data accessed: {resource.resource_type}/{resource.resource_id}",
            details={"fields_accessed": fields_accessed or []},
            tags=["data_access"],
        )
    
    async def log_data_modification(
        self,
        actor: AuditActor,
        resource: AuditResource,
        operation: str,
        changes: Optional[Dict[str, Any]] = None,
        context: Optional[AuditContext] = None,
    ) -> AuditEvent:
        """Log data modification event."""
        event_type_map = {
            "create": AuditEventType.DATA_CREATE,
            "update": AuditEventType.DATA_UPDATE,
            "delete": AuditEventType.DATA_DELETE,
        }
        
        return await self.log(
            event_type=event_type_map.get(operation, AuditEventType.DATA_UPDATE),
            category=AuditEventCategory.DATA_MODIFICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action=operation,
            outcome="success",
            resource=resource,
            context=context,
            message=f"Data {operation}: {resource.resource_type}/{resource.resource_id}",
            details={"changes": changes or {}},
            tags=["data_modification"],
        )
    
    async def log_security_event(
        self,
        event_type: AuditEventType,
        actor: AuditActor,
        description: str,
        severity: AuditSeverity = AuditSeverity.WARNING,
        details: Optional[Dict[str, Any]] = None,
        context: Optional[AuditContext] = None,
    ) -> AuditEvent:
        """Log a security-related event."""
        return await self.log(
            event_type=event_type,
            category=AuditEventCategory.SECURITY,
            severity=severity,
            actor=actor,
            action="security_event",
            outcome="detected",
            context=context,
            message=description,
            details=details or {},
            tags=["security", "alert"],
        )
    
    async def log_sensitive_data_access(
        self,
        actor: AuditActor,
        resource: AuditResource,
        data_classification: str,
        reason: str,
        context: Optional[AuditContext] = None,
    ) -> AuditEvent:
        """Log access to sensitive/PII data."""
        return await self.log(
            event_type=AuditEventType.SENSITIVE_DATA_ACCESS,
            category=AuditEventCategory.DATA_ACCESS,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="sensitive_access",
            outcome="success",
            resource=resource,
            context=context,
            message=f"Sensitive data accessed: {resource.resource_type}/{resource.resource_id}",
            details={
                "data_classification": data_classification,
                "access_reason": reason,
            },
            tags=["sensitive_data", "pii", "compliance"],
        )


# =============================================================================
# Audit Decorators
# =============================================================================

def audit_action(
    event_type: AuditEventType,
    category: AuditEventCategory,
    action: str,
    resource_type: Optional[str] = None,
):
    """Decorator to automatically audit a function call.
    
    Usage:
        @audit_action(
            event_type=AuditEventType.DATA_CREATE,
            category=AuditEventCategory.DATA_MODIFICATION,
            action="create_user",
            resource_type="user",
        )
        async def create_user(user_data: dict, actor: AuditActor):
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            audit_logger = AuditLogger.get_instance()
            
            # Get actor from kwargs
            actor = kwargs.get("actor") or kwargs.get("audit_actor")
            if not actor:
                actor = AuditActor(actor_id="system", actor_type="system")
            
            # Try to execute the function
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                outcome = "success"
                severity = AuditSeverity.INFO
                error_detail = None
            except Exception as e:
                outcome = "failure"
                severity = AuditSeverity.ERROR
                error_detail = str(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                
                # Build resource if possible
                resource = None
                if resource_type:
                    resource_id = kwargs.get("id") or kwargs.get(f"{resource_type}_id")
                    if resource_id:
                        resource = AuditResource(
                            resource_type=resource_type,
                            resource_id=str(resource_id),
                        )
                
                # Log the event
                context = AuditContext(duration_ms=duration_ms)
                
                details = {}
                if error_detail:
                    details["error"] = error_detail
                
                await audit_logger.log(
                    event_type=event_type,
                    category=category,
                    severity=severity,
                    actor=actor,
                    action=action,
                    outcome=outcome,
                    resource=resource,
                    context=context,
                    details=details,
                )
            
            return result
        
        return wrapper
    return decorator


# =============================================================================
# Convenience Functions
# =============================================================================

def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    return AuditLogger.get_instance()


# =============================================================================
# Hash-Chain Integrity Verification (ISO 27001 Tamper-Evident Audit)
# =============================================================================


def verify_audit_chain(
    events: List[AuditEvent],
    integrity: Optional[AuditIntegrity] = None,
) -> Dict[str, Any]:
    """
    Verify hash-chain integrity for a sequence of audit log entries.

    Each audit entry contains an ``integrity_hash`` computed over its contents
    plus a ``previous_hash`` that references the preceding entry's hash.
    This function walks the chain and detects:

    1. **Hash tampering** -- an entry's ``integrity_hash`` does not match a
       fresh recomputation of its canonical fields.
    2. **Chain breaks** -- an entry's ``previous_hash`` does not match the
       ``integrity_hash`` of its predecessor.
    3. **Missing hashes** -- an entry has no ``integrity_hash`` at all.

    Args:
        events: Ordered list of ``AuditEvent`` objects (oldest first).
        integrity: Optional ``AuditIntegrity`` instance for HMAC
            verification.  If ``None``, a default instance is created.

    Returns:
        Dict with:
            - ``total_entries`` (int): Number of entries examined.
            - ``is_valid`` (bool): ``True`` if the entire chain is intact.
            - ``tampered_entries`` (list[dict]): Details for each
              violation found, with ``event_id``, ``index``, and
              ``issue`` keys.
    """
    if integrity is None:
        integrity = AuditIntegrity()

    tampered: List[Dict[str, Any]] = []

    if not events:
        return {
            "total_entries": 0,
            "is_valid": True,
            "tampered_entries": [],
        }

    previous_hash: Optional[str] = None

    for i, event in enumerate(events):
        # Check 1: integrity_hash must be present.
        if not event.integrity_hash:
            tampered.append({
                "event_id": event.event_id,
                "index": i,
                "issue": "missing_integrity_hash",
            })
            previous_hash = None
            continue

        # Check 2: previous_hash must reference predecessor.
        if event.previous_hash != previous_hash:
            tampered.append({
                "event_id": event.event_id,
                "index": i,
                "issue": "chain_link_broken",
                "expected_previous": previous_hash,
                "actual_previous": event.previous_hash,
            })

        # Check 3: recompute the HMAC and compare.
        if not integrity.verify_event(event):
            tampered.append({
                "event_id": event.event_id,
                "index": i,
                "issue": "hash_mismatch",
            })

        previous_hash = event.integrity_hash

    return {
        "total_entries": len(events),
        "is_valid": len(tampered) == 0,
        "tampered_entries": tampered,
    }
