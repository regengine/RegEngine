"""Audit logging system for RegEngine.

This module provides comprehensive audit logging for all sensitive operations
including API key management, tenant operations, and data access.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger("audit")


class AuditEventType(str, Enum):
    """Types of auditable events in the system."""

    # API Key Management
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"
    API_KEY_VALIDATED = "api_key_validated"
    API_KEY_FAILED = "api_key_failed"

    # Tenant Operations
    TENANT_CREATED = "tenant_created"
    TENANT_UPDATED = "tenant_updated"
    TENANT_DELETED = "tenant_deleted"

    # Content Graph Overlay
    CONTROL_CREATED = "control_created"
    CONTROL_UPDATED = "control_updated"
    CONTROL_DELETED = "control_deleted"
    PRODUCT_CREATED = "product_created"
    PRODUCT_UPDATED = "product_updated"
    PRODUCT_DELETED = "product_deleted"
    MAPPING_CREATED = "mapping_created"
    MAPPING_DELETED = "mapping_deleted"

    # Data Access
    DATA_ACCESSED = "data_accessed"
    DATA_EXPORTED = "data_exported"
    QUERY_EXECUTED = "query_executed"

    # Authentication & Authorization
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    PERMISSION_DENIED = "permission_denied"

    # Configuration Changes
    CONFIG_UPDATED = "config_updated"
    SECRETS_ROTATED = "secrets_rotated"

    # System Events
    SERVICE_STARTED = "service_started"
    SERVICE_STOPPED = "service_stopped"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AuditEvent(BaseModel):
    """Audit event model for logging sensitive operations."""

    event_id: UUID = Field(default_factory=uuid4)
    event_type: AuditEventType
    severity: AuditSeverity = AuditSeverity.INFO
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Actor information
    actor_type: str = Field(..., description="Type of actor (user, service, system)")
    actor_id: Optional[str] = None
    tenant_id: Optional[UUID] = None

    # Event details
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    action: str
    status: str = Field(..., description="success, failure, denied")

    # Additional context
    metadata: dict[str, Any] = Field(default_factory=dict)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    # Error details (if applicable)
    error_message: Optional[str] = None
    error_code: Optional[str] = None


class AuditLogger:
    """Centralized audit logging with structured output."""

    @staticmethod
    def log_event(event: AuditEvent) -> None:
        """Log an audit event to structured logger.

        Args:
            event: AuditEvent to log
        """
        log_data = {
            "event_id": str(event.event_id),
            "event_type": event.event_type.value,
            "severity": event.severity.value,
            "timestamp": event.timestamp.isoformat(),
            "actor_type": event.actor_type,
            "actor_id": event.actor_id,
            "tenant_id": str(event.tenant_id) if event.tenant_id else None,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "action": event.action,
            "status": event.status,
            "metadata": event.metadata,
            "ip_address": event.ip_address,
            "user_agent": event.user_agent,
            "error_message": event.error_message,
            "error_code": event.error_code,
        }

        # Log with appropriate severity
        if event.severity == AuditSeverity.CRITICAL:
            logger.critical("audit_event", **log_data)
        elif event.severity == AuditSeverity.ERROR:
            logger.error("audit_event", **log_data)
        elif event.severity == AuditSeverity.WARNING:
            logger.warning("audit_event", **log_data)
        else:
            logger.info("audit_event", **log_data)

    @staticmethod
    def log_api_key_created(
        key_id: str,
        key_name: str,
        tenant_id: Optional[UUID],
        created_by: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """Log API key creation event.

        Args:
            key_id: API key identifier
            key_name: Human-readable key name
            tenant_id: Tenant UUID
            created_by: Actor who created the key
            metadata: Additional metadata
        """
        event = AuditEvent(
            event_type=AuditEventType.API_KEY_CREATED,
            severity=AuditSeverity.INFO,
            actor_type="admin",
            actor_id=created_by,
            tenant_id=tenant_id,
            resource_type="api_key",
            resource_id=key_id,
            action="create_api_key",
            status="success",
            metadata={"key_name": key_name, **(metadata or {})},
        )
        AuditLogger.log_event(event)

    @staticmethod
    def log_api_key_revoked(
        key_id: str,
        tenant_id: Optional[UUID],
        revoked_by: str,
        reason: Optional[str] = None,
    ) -> None:
        """Log API key revocation event.

        Args:
            key_id: API key identifier
            tenant_id: Tenant UUID
            revoked_by: Actor who revoked the key
            reason: Reason for revocation
        """
        event = AuditEvent(
            event_type=AuditEventType.API_KEY_REVOKED,
            severity=AuditSeverity.WARNING,
            actor_type="admin",
            actor_id=revoked_by,
            tenant_id=tenant_id,
            resource_type="api_key",
            resource_id=key_id,
            action="revoke_api_key",
            status="success",
            metadata={"reason": reason} if reason else {},
        )
        AuditLogger.log_event(event)

    @staticmethod
    def log_auth_success(
        actor_id: str,
        tenant_id: Optional[UUID],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Log successful authentication.

        Args:
            actor_id: Actor identifier (API key ID)
            tenant_id: Tenant UUID
            ip_address: Client IP address
            user_agent: Client user agent
        """
        event = AuditEvent(
            event_type=AuditEventType.AUTH_SUCCESS,
            severity=AuditSeverity.INFO,
            actor_type="api_key",
            actor_id=actor_id,
            tenant_id=tenant_id,
            resource_type="authentication",
            action="authenticate",
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        AuditLogger.log_event(event)

    @staticmethod
    def log_auth_failure(
        reason: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Log failed authentication attempt.

        Args:
            reason: Failure reason
            ip_address: Client IP address
            user_agent: Client user agent
            metadata: Additional metadata
        """
        event = AuditEvent(
            event_type=AuditEventType.AUTH_FAILURE,
            severity=AuditSeverity.WARNING,
            actor_type="anonymous",
            resource_type="authentication",
            action="authenticate",
            status="failure",
            error_message=reason,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=metadata or {},
        )
        AuditLogger.log_event(event)

    @staticmethod
    def log_data_access(
        actor_id: str,
        tenant_id: Optional[UUID],
        resource_type: str,
        resource_id: str,
        action: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """Log data access event.

        Args:
            actor_id: Actor identifier
            tenant_id: Tenant UUID
            resource_type: Type of resource accessed
            resource_id: Resource identifier
            action: Action performed (read, write, delete, etc.)
            metadata: Additional metadata
        """
        event = AuditEvent(
            event_type=AuditEventType.DATA_ACCESSED,
            severity=AuditSeverity.INFO,
            actor_type="api_key",
            actor_id=actor_id,
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            status="success",
            metadata=metadata or {},
        )
        AuditLogger.log_event(event)

    @staticmethod
    def log_permission_denied(
        actor_id: str,
        tenant_id: Optional[UUID],
        resource_type: str,
        action: str,
        reason: str,
    ) -> None:
        """Log permission denied event.

        Args:
            actor_id: Actor identifier
            tenant_id: Tenant UUID
            resource_type: Type of resource
            action: Attempted action
            reason: Reason for denial
        """
        event = AuditEvent(
            event_type=AuditEventType.PERMISSION_DENIED,
            severity=AuditSeverity.WARNING,
            actor_type="api_key",
            actor_id=actor_id,
            tenant_id=tenant_id,
            resource_type=resource_type,
            action=action,
            status="denied",
            error_message=reason,
        )
        AuditLogger.log_event(event)

    @staticmethod
    def log_control_created(
        control_id: str,
        tenant_id: UUID,
        created_by: str,
        framework: str,
    ) -> None:
        """Log tenant control creation.

        Args:
            control_id: Control identifier
            tenant_id: Tenant UUID
            created_by: Actor who created the control
            framework: Control framework (NIST CSF, SOC2, etc.)
        """
        event = AuditEvent(
            event_type=AuditEventType.CONTROL_CREATED,
            severity=AuditSeverity.INFO,
            actor_type="api_key",
            actor_id=created_by,
            tenant_id=tenant_id,
            resource_type="tenant_control",
            resource_id=control_id,
            action="create_control",
            status="success",
            metadata={"framework": framework},
        )
        AuditLogger.log_event(event)

    @staticmethod
    def log_product_created(
        product_id: str,
        tenant_id: UUID,
        created_by: str,
        product_name: str,
    ) -> None:
        """Log customer product creation.

        Args:
            product_id: Product identifier
            tenant_id: Tenant UUID
            created_by: Actor who created the product
            product_name: Product name
        """
        event = AuditEvent(
            event_type=AuditEventType.PRODUCT_CREATED,
            severity=AuditSeverity.INFO,
            actor_type="api_key",
            actor_id=created_by,
            tenant_id=tenant_id,
            resource_type="customer_product",
            resource_id=product_id,
            action="create_product",
            status="success",
            metadata={"product_name": product_name},
        )
        AuditLogger.log_event(event)


# Convenience functions for common audit logging scenarios


def audit_api_key_created(key_id: str, key_name: str, tenant_id: Optional[UUID], created_by: str) -> None:
    """Audit API key creation."""
    AuditLogger.log_api_key_created(key_id, key_name, tenant_id, created_by)


def audit_api_key_revoked(key_id: str, tenant_id: Optional[UUID], revoked_by: str, reason: Optional[str] = None) -> None:
    """Audit API key revocation."""
    AuditLogger.log_api_key_revoked(key_id, tenant_id, revoked_by, reason)


def audit_auth_success(actor_id: str, tenant_id: Optional[UUID], ip_address: Optional[str] = None) -> None:
    """Audit successful authentication."""
    AuditLogger.log_auth_success(actor_id, tenant_id, ip_address)


def audit_auth_failure(reason: str, ip_address: Optional[str] = None) -> None:
    """Audit failed authentication."""
    AuditLogger.log_auth_failure(reason, ip_address)
