"""
SEC-055: Security Event Logging Module.

Provides comprehensive security event logging with:
- Structured security event capture
- Event severity classification
- Audit trail generation
- Event correlation
- Tamper-evident logging
"""

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List, Callable
from collections import deque
import threading


class SecurityEventType(Enum):
    """Types of security events."""
    AUTHENTICATION_SUCCESS = "auth_success"
    AUTHENTICATION_FAILURE = "auth_failure"
    AUTHORIZATION_SUCCESS = "authz_success"
    AUTHORIZATION_FAILURE = "authz_failure"
    ACCESS_DENIED = "access_denied"
    SESSION_CREATED = "session_created"
    SESSION_DESTROYED = "session_destroyed"
    SESSION_EXPIRED = "session_expired"
    PASSWORD_CHANGE = "password_change"
    PASSWORD_RESET = "password_reset"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_UNLOCKED = "account_unlocked"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    SENSITIVE_DATA_ACCESS = "sensitive_data_access"
    CONFIGURATION_CHANGE = "config_change"
    SECURITY_ALERT = "security_alert"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    INJECTION_ATTEMPT = "injection_attempt"
    INVALID_INPUT = "invalid_input"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    DATA_EXPORT = "data_export"
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"
    ENCRYPTION_OPERATION = "encryption_op"
    SIGNATURE_VERIFICATION = "signature_verify"
    CUSTOM = "custom"


class EventSeverity(Enum):
    """Severity levels for security events."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class SecurityEventConfig:
    """Configuration for security event logging."""
    max_events_in_memory: int = 10000
    include_stack_trace: bool = False
    hash_sensitive_data: bool = True
    enable_correlation: bool = True
    retention_hours: int = 168  # 7 days
    min_severity: EventSeverity = EventSeverity.INFO


@dataclass
class SecurityEvent:
    """Represents a security event."""
    event_id: str
    event_type: SecurityEventType
    severity: EventSeverity
    timestamp: datetime
    message: str
    source: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    resource: Optional[str] = None
    action: Optional[str] = None
    outcome: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None
    previous_hash: Optional[str] = None
    event_hash: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "source": self.source,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "ip_address": self.ip_address,
            "resource": self.resource,
            "action": self.action,
            "outcome": self.outcome,
            "details": self.details,
            "correlation_id": self.correlation_id,
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
        }
    
    def to_json(self) -> str:
        """Convert event to JSON string."""
        return json.dumps(self.to_dict(), default=str)


class EventBuilder:
    """Builder for creating security events."""
    
    def __init__(self, event_type: SecurityEventType, message: str, source: str):
        """Initialize event builder."""
        self._event_type = event_type
        self._message = message
        self._source = source
        self._severity = EventSeverity.INFO
        self._user_id: Optional[str] = None
        self._session_id: Optional[str] = None
        self._ip_address: Optional[str] = None
        self._resource: Optional[str] = None
        self._action: Optional[str] = None
        self._outcome: Optional[str] = None
        self._details: Dict[str, Any] = {}
        self._correlation_id: Optional[str] = None
    
    def severity(self, severity: EventSeverity) -> "EventBuilder":
        """Set event severity."""
        self._severity = severity
        return self
    
    def user(self, user_id: str) -> "EventBuilder":
        """Set user ID."""
        self._user_id = user_id
        return self
    
    def session(self, session_id: str) -> "EventBuilder":
        """Set session ID."""
        self._session_id = session_id
        return self
    
    def ip(self, ip_address: str) -> "EventBuilder":
        """Set IP address."""
        self._ip_address = ip_address
        return self
    
    def resource(self, resource: str) -> "EventBuilder":
        """Set resource."""
        self._resource = resource
        return self
    
    def action(self, action: str) -> "EventBuilder":
        """Set action."""
        self._action = action
        return self
    
    def outcome(self, outcome: str) -> "EventBuilder":
        """Set outcome."""
        self._outcome = outcome
        return self
    
    def detail(self, key: str, value: Any) -> "EventBuilder":
        """Add a detail."""
        self._details[key] = value
        return self
    
    def details(self, details: Dict[str, Any]) -> "EventBuilder":
        """Set all details."""
        self._details.update(details)
        return self
    
    def correlate(self, correlation_id: str) -> "EventBuilder":
        """Set correlation ID."""
        self._correlation_id = correlation_id
        return self
    
    def build(self) -> SecurityEvent:
        """Build the security event."""
        return SecurityEvent(
            event_id=str(uuid.uuid4()),
            event_type=self._event_type,
            severity=self._severity,
            timestamp=datetime.now(timezone.utc),
            message=self._message,
            source=self._source,
            user_id=self._user_id,
            session_id=self._session_id,
            ip_address=self._ip_address,
            resource=self._resource,
            action=self._action,
            outcome=self._outcome,
            details=self._details,
            correlation_id=self._correlation_id,
        )


class EventHasher:
    """Generates tamper-evident hashes for events."""
    
    def __init__(self):
        """Initialize hasher."""
        self._previous_hash: Optional[str] = None
        self._lock = threading.Lock()
    
    def hash_event(self, event: SecurityEvent) -> str:
        """Generate hash for event including chain link."""
        with self._lock:
            # Build hash input
            hash_input = {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "timestamp": event.timestamp.isoformat(),
                "message": event.message,
                "source": event.source,
                "previous_hash": self._previous_hash,
            }
            
            # Generate hash
            hash_str = json.dumps(hash_input, sort_keys=True)
            event_hash = hashlib.sha256(hash_str.encode()).hexdigest()
            
            # Update chain
            event.previous_hash = self._previous_hash
            event.event_hash = event_hash
            self._previous_hash = event_hash
            
            return event_hash
    
    def verify_chain(self, events: List[SecurityEvent]) -> bool:
        """Verify event chain integrity."""
        if not events:
            return True
        
        previous_hash = None
        for event in events:
            # Check previous hash link
            if event.previous_hash != previous_hash:
                return False
            
            # Verify event hash
            hash_input = {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "timestamp": event.timestamp.isoformat(),
                "message": event.message,
                "source": event.source,
                "previous_hash": event.previous_hash,
            }
            
            hash_str = json.dumps(hash_input, sort_keys=True)
            expected_hash = hashlib.sha256(hash_str.encode()).hexdigest()
            
            if event.event_hash != expected_hash:
                return False
            
            previous_hash = event.event_hash
        
        return True
    
    def reset(self) -> None:
        """Reset the hash chain."""
        with self._lock:
            self._previous_hash = None


class EventStore:
    """In-memory store for security events."""
    
    def __init__(self, max_events: int = 10000):
        """Initialize event store."""
        self._max_events = max_events
        self._events: deque = deque(maxlen=max_events)
        self._lock = threading.Lock()
        self._indexes: Dict[str, List[SecurityEvent]] = {
            "user": {},
            "session": {},
            "correlation": {},
            "type": {},
        }
    
    def add(self, event: SecurityEvent) -> None:
        """Add event to store."""
        with self._lock:
            self._events.append(event)
            self._index_event(event)
    
    def _index_event(self, event: SecurityEvent) -> None:
        """Index event for fast lookup."""
        if event.user_id:
            if event.user_id not in self._indexes["user"]:
                self._indexes["user"][event.user_id] = []
            self._indexes["user"][event.user_id].append(event)
        
        if event.session_id:
            if event.session_id not in self._indexes["session"]:
                self._indexes["session"][event.session_id] = []
            self._indexes["session"][event.session_id].append(event)
        
        if event.correlation_id:
            if event.correlation_id not in self._indexes["correlation"]:
                self._indexes["correlation"][event.correlation_id] = []
            self._indexes["correlation"][event.correlation_id].append(event)
        
        type_key = event.event_type.value
        if type_key not in self._indexes["type"]:
            self._indexes["type"][type_key] = []
        self._indexes["type"][type_key].append(event)
    
    def get_by_user(self, user_id: str) -> List[SecurityEvent]:
        """Get events for a user."""
        with self._lock:
            return self._indexes["user"].get(user_id, []).copy()
    
    def get_by_session(self, session_id: str) -> List[SecurityEvent]:
        """Get events for a session."""
        with self._lock:
            return self._indexes["session"].get(session_id, []).copy()
    
    def get_by_correlation(self, correlation_id: str) -> List[SecurityEvent]:
        """Get correlated events."""
        with self._lock:
            return self._indexes["correlation"].get(correlation_id, []).copy()
    
    def get_by_type(self, event_type: SecurityEventType) -> List[SecurityEvent]:
        """Get events by type."""
        with self._lock:
            return self._indexes["type"].get(event_type.value, []).copy()
    
    def get_all(self) -> List[SecurityEvent]:
        """Get all events."""
        with self._lock:
            return list(self._events)
    
    def get_recent(self, count: int = 100) -> List[SecurityEvent]:
        """Get most recent events."""
        with self._lock:
            events = list(self._events)
            return events[-count:] if len(events) > count else events
    
    def count(self) -> int:
        """Get total event count."""
        with self._lock:
            return len(self._events)
    
    def clear(self) -> None:
        """Clear all events."""
        with self._lock:
            self._events.clear()
            for index in self._indexes.values():
                index.clear()


class EventFilter:
    """Filter security events."""
    
    def __init__(self):
        """Initialize filter."""
        self._min_severity: Optional[EventSeverity] = None
        self._event_types: Optional[List[SecurityEventType]] = None
        self._user_id: Optional[str] = None
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None
    
    def min_severity(self, severity: EventSeverity) -> "EventFilter":
        """Filter by minimum severity."""
        self._min_severity = severity
        return self
    
    def event_types(self, types: List[SecurityEventType]) -> "EventFilter":
        """Filter by event types."""
        self._event_types = types
        return self
    
    def user(self, user_id: str) -> "EventFilter":
        """Filter by user ID."""
        self._user_id = user_id
        return self
    
    def time_range(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> "EventFilter":
        """Filter by time range."""
        self._start_time = start
        self._end_time = end
        return self
    
    def apply(self, events: List[SecurityEvent]) -> List[SecurityEvent]:
        """Apply filter to events."""
        result = events
        
        severity_order = [
            EventSeverity.DEBUG,
            EventSeverity.INFO,
            EventSeverity.WARNING,
            EventSeverity.ERROR,
            EventSeverity.CRITICAL,
        ]
        
        if self._min_severity:
            min_idx = severity_order.index(self._min_severity)
            result = [
                e for e in result
                if severity_order.index(e.severity) >= min_idx
            ]
        
        if self._event_types:
            result = [e for e in result if e.event_type in self._event_types]
        
        if self._user_id:
            result = [e for e in result if e.user_id == self._user_id]
        
        if self._start_time:
            result = [e for e in result if e.timestamp >= self._start_time]
        
        if self._end_time:
            result = [e for e in result if e.timestamp <= self._end_time]
        
        return result


class EventHandler:
    """Base class for event handlers."""
    
    def handle(self, event: SecurityEvent) -> None:
        """Handle a security event."""
        raise NotImplementedError


class ConsoleEventHandler(EventHandler):
    """Handler that prints events to console."""
    
    def __init__(self, min_severity: EventSeverity = EventSeverity.INFO):
        """Initialize handler."""
        self._min_severity = min_severity
        self._severity_order = [
            EventSeverity.DEBUG,
            EventSeverity.INFO,
            EventSeverity.WARNING,
            EventSeverity.ERROR,
            EventSeverity.CRITICAL,
        ]
    
    def handle(self, event: SecurityEvent) -> None:
        """Print event to console."""
        if self._severity_order.index(event.severity) >= self._severity_order.index(self._min_severity):
            logging.getLogger(__name__).info(
                "[%s] %s - %s", event.severity.value.upper(), event.timestamp.isoformat(), event.message
            )


class CallbackEventHandler(EventHandler):
    """Handler that calls a callback function."""
    
    def __init__(self, callback: Callable[[SecurityEvent], None]):
        """Initialize handler."""
        self._callback = callback
    
    def handle(self, event: SecurityEvent) -> None:
        """Call the callback with the event."""
        self._callback(event)


class SecurityEventLogger:
    """Main security event logger."""
    
    def __init__(self, config: Optional[SecurityEventConfig] = None):
        """Initialize logger."""
        self._config = config or SecurityEventConfig()
        self._store = EventStore(self._config.max_events_in_memory)
        self._hasher = EventHasher()
        self._handlers: List[EventHandler] = []
        self._lock = threading.Lock()
    
    def add_handler(self, handler: EventHandler) -> None:
        """Add an event handler."""
        with self._lock:
            self._handlers.append(handler)
    
    def remove_handler(self, handler: EventHandler) -> None:
        """Remove an event handler."""
        with self._lock:
            if handler in self._handlers:
                self._handlers.remove(handler)
    
    def log(self, event: SecurityEvent) -> SecurityEvent:
        """Log a security event."""
        # Check minimum severity
        severity_order = [
            EventSeverity.DEBUG,
            EventSeverity.INFO,
            EventSeverity.WARNING,
            EventSeverity.ERROR,
            EventSeverity.CRITICAL,
        ]
        
        if severity_order.index(event.severity) < severity_order.index(self._config.min_severity):
            return event
        
        # Hash event
        self._hasher.hash_event(event)
        
        # Store event
        self._store.add(event)
        
        # Notify handlers
        with self._lock:
            handlers = self._handlers.copy()
        
        for handler in handlers:
            try:
                handler.handle(event)
            except Exception:
                pass  # Don't let handler errors affect logging
        
        return event
    
    def log_auth_success(
        self,
        user_id: str,
        source: str,
        ip_address: Optional[str] = None,
        **details
    ) -> SecurityEvent:
        """Log successful authentication."""
        builder = EventBuilder(
            SecurityEventType.AUTHENTICATION_SUCCESS,
            f"User {user_id} authenticated successfully",
            source
        ).severity(EventSeverity.INFO).user(user_id)
        
        if ip_address:
            builder.ip(ip_address)
        
        builder.details(details)
        return self.log(builder.build())
    
    def log_auth_failure(
        self,
        user_id: Optional[str],
        source: str,
        reason: str,
        ip_address: Optional[str] = None,
        **details
    ) -> SecurityEvent:
        """Log authentication failure."""
        msg = f"Authentication failed for user {user_id}: {reason}" if user_id else f"Authentication failed: {reason}"
        builder = EventBuilder(
            SecurityEventType.AUTHENTICATION_FAILURE,
            msg,
            source
        ).severity(EventSeverity.WARNING)
        
        if user_id:
            builder.user(user_id)
        if ip_address:
            builder.ip(ip_address)
        
        builder.detail("reason", reason)
        builder.details(details)
        return self.log(builder.build())
    
    def log_access_denied(
        self,
        user_id: str,
        resource: str,
        action: str,
        source: str,
        **details
    ) -> SecurityEvent:
        """Log access denied event."""
        builder = EventBuilder(
            SecurityEventType.ACCESS_DENIED,
            f"Access denied for user {user_id} to {action} on {resource}",
            source
        ).severity(EventSeverity.WARNING).user(user_id).resource(resource).action(action)
        
        builder.details(details)
        return self.log(builder.build())
    
    def log_security_alert(
        self,
        message: str,
        source: str,
        severity: EventSeverity = EventSeverity.CRITICAL,
        **details
    ) -> SecurityEvent:
        """Log a security alert."""
        builder = EventBuilder(
            SecurityEventType.SECURITY_ALERT,
            message,
            source
        ).severity(severity)
        
        builder.details(details)
        return self.log(builder.build())
    
    def get_events(self) -> List[SecurityEvent]:
        """Get all logged events."""
        return self._store.get_all()
    
    def get_recent_events(self, count: int = 100) -> List[SecurityEvent]:
        """Get recent events."""
        return self._store.get_recent(count)
    
    def get_user_events(self, user_id: str) -> List[SecurityEvent]:
        """Get events for a user."""
        return self._store.get_by_user(user_id)
    
    def query(self, filter: EventFilter) -> List[SecurityEvent]:
        """Query events with filter."""
        events = self._store.get_all()
        return filter.apply(events)
    
    def verify_integrity(self) -> bool:
        """Verify event chain integrity."""
        events = self._store.get_all()
        return self._hasher.verify_chain(events)
    
    def get_event_count(self) -> int:
        """Get total event count."""
        return self._store.count()
    
    def clear(self) -> None:
        """Clear all events."""
        self._store.clear()
        self._hasher.reset()


class SecurityEventLoggingService:
    """Main service for security event logging."""
    
    _instance: Optional["SecurityEventLoggingService"] = None
    
    def __new__(cls) -> "SecurityEventLoggingService":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize service."""
        if self._initialized:
            return
        
        self._config = SecurityEventConfig()
        self._logger = SecurityEventLogger(self._config)
        self._initialized = True
    
    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance."""
        cls._instance = None
    
    def configure(self, config: SecurityEventConfig) -> None:
        """Update configuration."""
        self._config = config
        self._logger = SecurityEventLogger(config)
    
    def get_config(self) -> SecurityEventConfig:
        """Get current configuration."""
        return self._config
    
    def get_logger(self) -> SecurityEventLogger:
        """Get the event logger."""
        return self._logger
    
    def log_event(self, event: SecurityEvent) -> SecurityEvent:
        """Log a security event."""
        return self._logger.log(event)
    
    def create_event(
        self,
        event_type: SecurityEventType,
        message: str,
        source: str
    ) -> EventBuilder:
        """Create an event builder."""
        return EventBuilder(event_type, message, source)
    
    def add_handler(self, handler: EventHandler) -> None:
        """Add an event handler."""
        self._logger.add_handler(handler)
    
    def get_events(self) -> List[SecurityEvent]:
        """Get all events."""
        return self._logger.get_events()
    
    def query_events(self, filter: EventFilter) -> List[SecurityEvent]:
        """Query events with filter."""
        return self._logger.query(filter)


# Convenience functions
def get_security_logger() -> SecurityEventLoggingService:
    """Get the security logging service singleton."""
    return SecurityEventLoggingService()


def log_security_event(
    event_type: SecurityEventType,
    message: str,
    source: str,
    severity: EventSeverity = EventSeverity.INFO,
    **details
) -> SecurityEvent:
    """Log a security event."""
    svc = get_security_logger()
    builder = svc.create_event(event_type, message, source).severity(severity)
    builder.details(details)
    return svc.log_event(builder.build())


def log_auth_success(user_id: str, source: str, **details) -> SecurityEvent:
    """Log successful authentication."""
    return get_security_logger().get_logger().log_auth_success(user_id, source, **details)


def log_auth_failure(user_id: Optional[str], source: str, reason: str, **details) -> SecurityEvent:
    """Log authentication failure."""
    return get_security_logger().get_logger().log_auth_failure(user_id, source, reason, **details)
