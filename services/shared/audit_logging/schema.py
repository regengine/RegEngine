"""
Audit event schema definitions.

Enums, data classes, and serialization for audit events.
These types are used by all audit subsystems (integrity, storage, writer).
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


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
