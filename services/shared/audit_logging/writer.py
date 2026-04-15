"""
Audit logger — main interface for recording audit events.

Includes convenience methods for common audit scenarios and
the audit_action decorator for automatic function-level auditing.
"""

import functools
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from shared.audit_logging.schema import (
    AuditActor,
    AuditContext,
    AuditEvent,
    AuditEventCategory,
    AuditEventType,
    AuditResource,
    AuditSeverity,
)
from shared.audit_logging.integrity import AuditIntegrity
from shared.audit_logging.storage import AuditStorageBackend, InMemoryAuditStorage

logger = logging.getLogger(__name__)


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
        """Log an audit event."""
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

        await self._storage.store(event)

        for hook in self._hooks:
            try:
                hook(event)
            except Exception as e:
                logger.error("Audit hook error: %s", e)

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
        self, user_id: str, username: str, ip_address: str,
        user_agent: Optional[str] = None, tenant_id: Optional[str] = None,
        mfa_used: bool = False,
    ) -> AuditEvent:
        """Log successful login."""
        return await self.log(
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=AuditActor(
                actor_id=user_id, actor_type="user", username=username,
                ip_address=ip_address, user_agent=user_agent, tenant_id=tenant_id,
            ),
            action="login", outcome="success",
            message=f"User {username} logged in successfully",
            details={"mfa_used": mfa_used}, tags=["authentication"],
        )

    async def log_login_failure(
        self, username: str, ip_address: str, reason: str,
        user_agent: Optional[str] = None, tenant_id: Optional[str] = None,
    ) -> AuditEvent:
        """Log failed login attempt."""
        return await self.log(
            event_type=AuditEventType.LOGIN_FAILURE,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.WARNING,
            actor=AuditActor(
                actor_id=f"unknown:{username}", actor_type="user", username=username,
                ip_address=ip_address, user_agent=user_agent, tenant_id=tenant_id,
            ),
            action="login", outcome="failure",
            message=f"Login failed for {username}: {reason}",
            details={"reason": reason}, tags=["authentication", "security"],
        )

    async def log_access_denied(
        self, actor: AuditActor, resource: AuditResource,
        required_permission: str, context: Optional[AuditContext] = None,
    ) -> AuditEvent:
        """Log access denied event."""
        return await self.log(
            event_type=AuditEventType.ACCESS_DENIED,
            category=AuditEventCategory.AUTHORIZATION,
            severity=AuditSeverity.WARNING,
            actor=actor, action="access", outcome="denied",
            resource=resource, context=context,
            message=f"Access denied: {required_permission} on {resource.resource_type}/{resource.resource_id}",
            details={"required_permission": required_permission},
            tags=["authorization", "security"],
        )

    async def log_data_access(
        self, actor: AuditActor, resource: AuditResource,
        access_type: str = "read", fields_accessed: Optional[List[str]] = None,
        context: Optional[AuditContext] = None,
    ) -> AuditEvent:
        """Log data access event."""
        return await self.log(
            event_type=AuditEventType.DATA_READ,
            category=AuditEventCategory.DATA_ACCESS,
            severity=AuditSeverity.INFO,
            actor=actor, action=access_type, outcome="success",
            resource=resource, context=context,
            message=f"Data accessed: {resource.resource_type}/{resource.resource_id}",
            details={"fields_accessed": fields_accessed or []},
            tags=["data_access"],
        )

    async def log_data_modification(
        self, actor: AuditActor, resource: AuditResource,
        operation: str, changes: Optional[Dict[str, Any]] = None,
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
            actor=actor, action=operation, outcome="success",
            resource=resource, context=context,
            message=f"Data {operation}: {resource.resource_type}/{resource.resource_id}",
            details={"changes": changes or {}},
            tags=["data_modification"],
        )

    async def log_security_event(
        self, event_type: AuditEventType, actor: AuditActor,
        description: str, severity: AuditSeverity = AuditSeverity.WARNING,
        details: Optional[Dict[str, Any]] = None,
        context: Optional[AuditContext] = None,
    ) -> AuditEvent:
        """Log a security-related event."""
        return await self.log(
            event_type=event_type,
            category=AuditEventCategory.SECURITY,
            severity=severity,
            actor=actor, action="security_event", outcome="detected",
            context=context, message=description,
            details=details or {}, tags=["security", "alert"],
        )

    async def log_sensitive_data_access(
        self, actor: AuditActor, resource: AuditResource,
        data_classification: str, reason: str,
        context: Optional[AuditContext] = None,
    ) -> AuditEvent:
        """Log access to sensitive/PII data."""
        return await self.log(
            event_type=AuditEventType.SENSITIVE_DATA_ACCESS,
            category=AuditEventCategory.DATA_ACCESS,
            severity=AuditSeverity.INFO,
            actor=actor, action="sensitive_access", outcome="success",
            resource=resource, context=context,
            message=f"Sensitive data accessed: {resource.resource_type}/{resource.resource_id}",
            details={
                "data_classification": data_classification,
                "access_reason": reason,
            },
            tags=["sensitive_data", "pii", "compliance"],
        )


# =============================================================================
# Audit Decorator
# =============================================================================

def audit_action(
    event_type: AuditEventType,
    category: AuditEventCategory,
    action: str,
    resource_type: Optional[str] = None,
):
    """Decorator to automatically audit a function call."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            audit_logger = AuditLogger.get_instance()

            actor = kwargs.get("actor") or kwargs.get("audit_actor")
            if not actor:
                actor = AuditActor(actor_id="system", actor_type="system")

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

                resource = None
                if resource_type:
                    resource_id = kwargs.get("id") or kwargs.get(f"{resource_type}_id")
                    if resource_id:
                        resource = AuditResource(
                            resource_type=resource_type,
                            resource_id=str(resource_id),
                        )

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
