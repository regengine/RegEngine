"""Compatibility smoke tests for the current shared audit logging API."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from shared.audit_logging import (
    AuditActor,
    AuditEvent,
    AuditEventCategory,
    AuditEventType,
    AuditLogger,
    AuditResource,
    AuditSeverity,
    InMemoryAuditStorage,
)


@pytest.fixture(autouse=True)
def _audit_integrity_key(monkeypatch):
    monkeypatch.setenv("AUDIT_INTEGRITY_KEY", "test-audit-key")


@pytest.fixture
def actor() -> AuditActor:
    return AuditActor(
        actor_id="admin_user_1",
        actor_type="admin",
        email="admin@example.com",
        tenant_id="tenant-1",
        ip_address="192.168.1.100",
    )


@pytest.fixture
def resource() -> AuditResource:
    return AuditResource(
        resource_type="api_key",
        resource_id="rge_abc123",
        tenant_id="tenant-1",
        attributes={"key_name": "Production API Key"},
    )


@pytest.fixture
def audit_logger() -> AuditLogger:
    return AuditLogger(
        storage=InMemoryAuditStorage(),
        service_name="test-service",
        environment="test",
    )


class TestAuditEvent:
    def test_create_audit_event(self, actor: AuditActor, resource: AuditResource) -> None:
        event = AuditEvent(
            event_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            event_type=AuditEventType.DATA_CREATE,
            category=AuditEventCategory.ADMIN,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="create_api_key",
            outcome="success",
            resource=resource,
            details={"key_name": "Production API Key"},
        )

        assert event.event_type == AuditEventType.DATA_CREATE
        assert event.severity == AuditSeverity.INFO
        assert event.actor.actor_type == "admin"
        assert event.resource is resource
        assert event.details["key_name"] == "Production API Key"

    def test_event_serializes_current_schema(self, actor: AuditActor, resource: AuditResource) -> None:
        event = AuditEvent(
            event_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            event_type=AuditEventType.LOGIN_FAILURE,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.WARNING,
            actor=actor,
            action="login",
            outcome="failure",
            resource=resource,
            details={"reason": "Invalid API key format"},
        )

        payload = event.to_dict()

        assert payload["event_type"] == "login_failure"
        assert payload["severity"] == "warning"
        assert payload["actor"]["actor_id"] == "admin_user_1"
        assert payload["resource"]["resource_type"] == "api_key"


class TestAuditLogger:
    @pytest.mark.asyncio
    async def test_log_login_success(self, audit_logger: AuditLogger) -> None:
        event = await audit_logger.log_login_success(
            user_id="user-1",
            username="admin@example.com",
            ip_address="192.168.1.100",
            tenant_id="tenant-1",
        )

        assert event.event_type == AuditEventType.LOGIN_SUCCESS
        assert event.category == AuditEventCategory.AUTHENTICATION
        assert event.outcome == "success"
        assert event.actor.tenant_id == "tenant-1"

    @pytest.mark.asyncio
    async def test_log_login_failure(self, audit_logger: AuditLogger) -> None:
        event = await audit_logger.log_login_failure(
            username="admin@example.com",
            ip_address="192.168.1.100",
            reason="invalid_password",
        )

        assert event.event_type == AuditEventType.LOGIN_FAILURE
        assert event.severity == AuditSeverity.WARNING
        assert event.details["reason"] == "invalid_password"

    @pytest.mark.asyncio
    async def test_log_access_denied(
        self,
        audit_logger: AuditLogger,
        actor: AuditActor,
        resource: AuditResource,
    ) -> None:
        event = await audit_logger.log_access_denied(
            actor=actor,
            resource=resource,
            required_permission="api_keys:write",
        )

        assert event.event_type == AuditEventType.ACCESS_DENIED
        assert event.category == AuditEventCategory.AUTHORIZATION
        assert event.details["required_permission"] == "api_keys:write"

    @pytest.mark.asyncio
    async def test_log_data_access(
        self,
        audit_logger: AuditLogger,
        actor: AuditActor,
        resource: AuditResource,
    ) -> None:
        event = await audit_logger.log_data_access(
            actor=actor,
            resource=resource,
            access_type="read",
            fields_accessed=["name", "scopes"],
        )

        assert event.event_type == AuditEventType.DATA_READ
        assert event.details["fields_accessed"] == ["name", "scopes"]

    @pytest.mark.asyncio
    async def test_log_data_modification(
        self,
        audit_logger: AuditLogger,
        actor: AuditActor,
        resource: AuditResource,
    ) -> None:
        event = await audit_logger.log_data_modification(
            actor=actor,
            resource=resource,
            operation="update",
            changes={"scopes": {"old": ["read"], "new": ["read", "write"]}},
        )

        assert event.event_type == AuditEventType.DATA_UPDATE
        assert event.category == AuditEventCategory.DATA_MODIFICATION
        assert "scopes" in event.details["changes"]

    @pytest.mark.asyncio
    async def test_log_security_event(self, audit_logger: AuditLogger, actor: AuditActor) -> None:
        event = await audit_logger.log_security_event(
            event_type=AuditEventType.INJECTION_ATTEMPT,
            actor=actor,
            description="SQL injection attempt detected",
            severity=AuditSeverity.CRITICAL,
            details={"detector": "input-filter"},
        )

        assert event.event_type == AuditEventType.INJECTION_ATTEMPT
        assert event.severity == AuditSeverity.CRITICAL
        assert "security" in event.tags


class TestAuditEventTypes:
    def test_current_event_types_exist(self) -> None:
        expected_types = [
            "LOGIN_SUCCESS",
            "LOGIN_FAILURE",
            "ACCESS_DENIED",
            "DATA_CREATE",
            "DATA_READ",
            "DATA_UPDATE",
            "INJECTION_ATTEMPT",
        ]

        for event_type in expected_types:
            assert hasattr(AuditEventType, event_type)

    def test_severity_levels_use_lowercase_values(self) -> None:
        assert AuditSeverity.INFO.value == "info"
        assert AuditSeverity.WARNING.value == "warning"
        assert AuditSeverity.ERROR.value == "error"
        assert AuditSeverity.CRITICAL.value == "critical"
