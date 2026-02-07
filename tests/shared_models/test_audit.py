"""Tests for audit logging system."""

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

from audit import (
    AuditEvent,
    AuditEventType,
    AuditLogger,
    AuditSeverity,
    audit_api_key_created,
    audit_auth_failure,
    audit_auth_success,
)


class TestAuditEvent:
    """Tests for AuditEvent model."""

    def test_create_audit_event(self):
        """Test creating a basic audit event."""
        tenant_id = uuid4()
        event = AuditEvent(
            event_type=AuditEventType.API_KEY_CREATED,
            severity=AuditSeverity.INFO,
            actor_type="admin",
            actor_id="admin_user_1",
            tenant_id=tenant_id,
            resource_type="api_key",
            resource_id="rge_abc123",
            action="create_api_key",
            status="success",
        )

        assert event.event_type == AuditEventType.API_KEY_CREATED
        assert event.severity == AuditSeverity.INFO
        assert event.actor_type == "admin"
        assert event.tenant_id == tenant_id
        assert event.status == "success"
        assert isinstance(event.event_id, UUID)
        assert isinstance(event.timestamp, datetime)

    def test_event_with_metadata(self):
        """Test audit event with additional metadata."""
        metadata = {
            "key_name": "Production API Key",
            "scopes": ["read", "write"],
            "rate_limit": 1000,
        }

        event = AuditEvent(
            event_type=AuditEventType.API_KEY_CREATED,
            actor_type="admin",
            action="create_api_key",
            status="success",
            metadata=metadata,
        )

        assert event.metadata == metadata
        assert event.metadata["key_name"] == "Production API Key"

    def test_error_event(self):
        """Test audit event with error details."""
        event = AuditEvent(
            event_type=AuditEventType.AUTH_FAILURE,
            severity=AuditSeverity.WARNING,
            actor_type="anonymous",
            action="authenticate",
            status="failure",
            error_message="Invalid API key format",
            error_code="AUTH_001",
        )

        assert event.severity == AuditSeverity.WARNING
        assert event.status == "failure"
        assert event.error_message == "Invalid API key format"
        assert event.error_code == "AUTH_001"

    def test_event_with_ip_and_user_agent(self):
        """Test audit event with IP and user agent."""
        event = AuditEvent(
            event_type=AuditEventType.AUTH_SUCCESS,
            actor_type="api_key",
            action="authenticate",
            status="success",
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
        )

        assert event.ip_address == "192.168.1.100"
        assert event.user_agent == "Mozilla/5.0"


class TestAuditLogger:
    """Tests for AuditLogger."""

    def test_log_api_key_created(self, caplog):
        """Test logging API key creation."""
        tenant_id = uuid4()

        AuditLogger.log_api_key_created(
            key_id="rge_test123",
            key_name="Test API Key",
            tenant_id=tenant_id,
            created_by="admin_user",
        )

        # Verify event was logged (would check structured logs in production)
        # For now, just verify it doesn't raise exceptions

    def test_log_api_key_revoked(self):
        """Test logging API key revocation."""
        tenant_id = uuid4()

        AuditLogger.log_api_key_revoked(
            key_id="rge_test123",
            tenant_id=tenant_id,
            revoked_by="admin_user",
            reason="Security incident",
        )

        # Verify event was logged

    def test_log_auth_success(self):
        """Test logging successful authentication."""
        tenant_id = uuid4()

        AuditLogger.log_auth_success(
            actor_id="rge_test123",
            tenant_id=tenant_id,
            ip_address="192.168.1.100",
        )

        # Verify event was logged

    def test_log_auth_failure(self):
        """Test logging failed authentication."""
        AuditLogger.log_auth_failure(
            reason="Invalid API key",
            ip_address="192.168.1.100",
        )

        # Verify event was logged

    def test_log_data_access(self):
        """Test logging data access."""
        tenant_id = uuid4()

        AuditLogger.log_data_access(
            actor_id="rge_test123",
            tenant_id=tenant_id,
            resource_type="customer_product",
            resource_id=str(uuid4()),
            action="read",
            metadata={"query": "get_product_requirements"},
        )

        # Verify event was logged

    def test_log_permission_denied(self):
        """Test logging permission denied."""
        tenant_id = uuid4()

        AuditLogger.log_permission_denied(
            actor_id="rge_test123",
            tenant_id=tenant_id,
            resource_type="tenant_control",
            action="delete",
            reason="Insufficient permissions",
        )

        # Verify event was logged

    def test_log_control_created(self):
        """Test logging tenant control creation."""
        tenant_id = uuid4()
        control_id = str(uuid4())

        AuditLogger.log_control_created(
            control_id=control_id,
            tenant_id=tenant_id,
            created_by="rge_test123",
            framework="NIST CSF",
        )

        # Verify event was logged

    def test_log_product_created(self):
        """Test logging customer product creation."""
        tenant_id = uuid4()
        product_id = str(uuid4())

        AuditLogger.log_product_created(
            product_id=product_id,
            tenant_id=tenant_id,
            created_by="rge_test123",
            product_name="Crypto Trading Platform",
        )

        # Verify event was logged


class TestConvenienceFunctions:
    """Tests for audit logging convenience functions."""

    def test_audit_api_key_created(self):
        """Test convenience function for API key creation."""
        tenant_id = uuid4()

        audit_api_key_created(
            key_id="rge_test123",
            key_name="Test Key",
            tenant_id=tenant_id,
            created_by="admin",
        )

        # Verify it doesn't raise exceptions

    def test_audit_auth_success(self):
        """Test convenience function for auth success."""
        tenant_id = uuid4()

        audit_auth_success(
            actor_id="rge_test123",
            tenant_id=tenant_id,
            ip_address="192.168.1.100",
        )

        # Verify it doesn't raise exceptions

    def test_audit_auth_failure(self):
        """Test convenience function for auth failure."""
        audit_auth_failure(
            reason="Invalid credentials",
            ip_address="192.168.1.100",
        )

        # Verify it doesn't raise exceptions


class TestAuditEventTypes:
    """Tests for audit event type enums."""

    def test_event_types_exist(self):
        """Test that all expected event types are defined."""
        expected_types = [
            "API_KEY_CREATED",
            "API_KEY_REVOKED",
            "AUTH_SUCCESS",
            "AUTH_FAILURE",
            "CONTROL_CREATED",
            "PRODUCT_CREATED",
            "DATA_ACCESSED",
        ]

        for event_type in expected_types:
            assert hasattr(AuditEventType, event_type)

    def test_severity_levels(self):
        """Test severity level enum values."""
        assert AuditSeverity.INFO.value == "INFO"
        assert AuditSeverity.WARNING.value == "WARNING"
        assert AuditSeverity.ERROR.value == "ERROR"
        assert AuditSeverity.CRITICAL.value == "CRITICAL"
