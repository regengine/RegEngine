"""
Tests for SEC-016: Comprehensive Audit Logging.

Tests cover:
- Audit event creation and serialization
- Integrity hash chains
- Storage backends
- Query functionality
- Convenience methods
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from shared.audit_logging import (
    # Enums
    AuditEventCategory,
    AuditEventType,
    AuditSeverity,
    # Data classes
    AuditActor,
    AuditResource,
    AuditContext,
    AuditEvent,
    # Integrity
    AuditIntegrity,
    # Storage
    AuditStorageBackend,
    InMemoryAuditStorage,
    # Logger
    AuditLogger,
    # Decorators
    audit_action,
    # Functions
    get_audit_logger,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def actor():
    """Create a test actor."""
    return AuditActor(
        actor_id="user-123",
        actor_type="user",
        username="testuser",
        email="test@example.com",
        ip_address="192.168.1.100",
        user_agent="Mozilla/5.0",
        session_id="sess-456",
        tenant_id="tenant-789",
        roles=["admin", "user"],
    )


@pytest.fixture
def resource():
    """Create a test resource."""
    return AuditResource(
        resource_type="document",
        resource_id="doc-123",
        resource_name="Test Document",
        tenant_id="tenant-789",
        attributes={"status": "active"},
    )


@pytest.fixture
def context():
    """Create a test context."""
    return AuditContext(
        request_id="req-123",
        correlation_id="corr-456",
        environment="test",
        service_name="test-service",
        endpoint="/api/v1/test",
        http_method="POST",
        http_status=200,
        duration_ms=150.5,
    )


@pytest.fixture
def storage():
    """Create test storage."""
    return InMemoryAuditStorage()


@pytest.fixture
def audit_logger(storage):
    """Create test audit logger."""
    return AuditLogger(
        storage=storage,
        service_name="test-service",
        environment="test",
    )


# =============================================================================
# Test: Enums
# =============================================================================

class TestAuditEnums:
    """Test audit enums."""
    
    def test_event_categories(self):
        """Should have expected categories."""
        assert AuditEventCategory.AUTHENTICATION == "authentication"
        assert AuditEventCategory.AUTHORIZATION == "authorization"
        assert AuditEventCategory.DATA_ACCESS == "data_access"
        assert AuditEventCategory.SECURITY == "security"
    
    def test_event_types(self):
        """Should have authentication event types."""
        assert AuditEventType.LOGIN_SUCCESS == "login_success"
        assert AuditEventType.LOGIN_FAILURE == "login_failure"
        assert AuditEventType.ACCESS_DENIED == "access_denied"
    
    def test_severity_levels(self):
        """Should have severity levels."""
        assert AuditSeverity.DEBUG == "debug"
        assert AuditSeverity.INFO == "info"
        assert AuditSeverity.WARNING == "warning"
        assert AuditSeverity.ERROR == "error"
        assert AuditSeverity.CRITICAL == "critical"


# =============================================================================
# Test: Data Classes
# =============================================================================

class TestAuditActor:
    """Test AuditActor data class."""
    
    def test_actor_creation(self, actor):
        """Should create actor with all fields."""
        assert actor.actor_id == "user-123"
        assert actor.actor_type == "user"
        assert actor.username == "testuser"
        assert actor.ip_address == "192.168.1.100"
    
    def test_actor_to_dict(self, actor):
        """Should convert to dict."""
        data = actor.to_dict()
        assert data["actor_id"] == "user-123"
        assert data["username"] == "testuser"
        assert "roles" in data
    
    def test_actor_to_dict_excludes_none(self):
        """Should exclude None values in dict."""
        actor = AuditActor(
            actor_id="user-123",
            actor_type="user",
        )
        data = actor.to_dict()
        assert "username" not in data
        assert "email" not in data


class TestAuditResource:
    """Test AuditResource data class."""
    
    def test_resource_creation(self, resource):
        """Should create resource with all fields."""
        assert resource.resource_type == "document"
        assert resource.resource_id == "doc-123"
        assert resource.attributes["status"] == "active"
    
    def test_resource_to_dict(self, resource):
        """Should convert to dict."""
        data = resource.to_dict()
        assert data["resource_type"] == "document"
        assert data["resource_id"] == "doc-123"
        assert "attributes" in data


class TestAuditContext:
    """Test AuditContext data class."""
    
    def test_context_creation(self, context):
        """Should create context with all fields."""
        assert context.request_id == "req-123"
        assert context.endpoint == "/api/v1/test"
        assert context.http_status == 200
    
    def test_context_to_dict(self, context):
        """Should convert to dict."""
        data = context.to_dict()
        assert data["http_method"] == "POST"
        assert data["duration_ms"] == 150.5


class TestAuditEvent:
    """Test AuditEvent data class."""
    
    def test_event_creation(self, actor, resource, context):
        """Should create complete event."""
        event = AuditEvent(
            event_id="evt-123",
            timestamp=datetime.now(timezone.utc),
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
            outcome="success",
            resource=resource,
            context=context,
            message="User logged in",
            details={"method": "password"},
            tags=["auth"],
        )
        
        assert event.event_id == "evt-123"
        assert event.event_type == AuditEventType.LOGIN_SUCCESS
        assert event.outcome == "success"
    
    def test_event_to_dict(self, actor):
        """Should convert to dict."""
        event = AuditEvent(
            event_id="evt-123",
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
            outcome="success",
        )
        
        data = event.to_dict()
        assert data["event_id"] == "evt-123"
        assert data["timestamp"] == "2024-01-15T12:00:00+00:00"
        assert data["event_type"] == "login_success"
    
    def test_event_to_json(self, actor):
        """Should convert to JSON."""
        event = AuditEvent(
            event_id="evt-123",
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
            outcome="success",
        )
        
        json_str = event.to_json()
        assert '"event_id": "evt-123"' in json_str
        assert '"login_success"' in json_str


# =============================================================================
# Test: Integrity
# =============================================================================

class TestAuditIntegrity:
    """Test AuditIntegrity hash chains."""
    
    def test_compute_hash(self, actor):
        """Should compute integrity hash."""
        integrity = AuditIntegrity(secret_key="test-key")
        
        event = AuditEvent(
            event_id="evt-123",
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
            outcome="success",
        )
        
        hash1 = integrity.compute_hash(event)
        assert len(hash1) == 64  # SHA256 hex
        
        # Same event should produce same hash
        hash2 = integrity.compute_hash(event)
        assert hash1 == hash2
    
    def test_sign_event(self, actor):
        """Should sign event with hash."""
        integrity = AuditIntegrity(secret_key="test-key")
        
        event = AuditEvent(
            event_id="evt-123",
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
            outcome="success",
        )
        
        signed = integrity.sign_event(event)
        assert signed.integrity_hash is not None
        assert signed.previous_hash is None  # First event
    
    def test_sign_chain(self, actor):
        """Should create hash chain."""
        integrity = AuditIntegrity(secret_key="test-key")
        
        event1 = AuditEvent(
            event_id="evt-1",
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
            outcome="success",
        )
        
        event2 = AuditEvent(
            event_id="evt-2",
            timestamp=datetime(2024, 1, 15, 12, 0, 1, tzinfo=timezone.utc),
            event_type=AuditEventType.LOGOUT,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="logout",
            outcome="success",
        )
        
        signed1 = integrity.sign_event(event1)
        signed2 = integrity.sign_event(event2)
        
        assert signed2.previous_hash == signed1.integrity_hash
    
    def test_verify_event(self, actor):
        """Should verify event integrity."""
        integrity = AuditIntegrity(secret_key="test-key")
        
        event = AuditEvent(
            event_id="evt-123",
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
            outcome="success",
        )
        
        signed = integrity.sign_event(event)
        assert integrity.verify_event(signed) is True
    
    def test_verify_tampered_event(self, actor):
        """Should detect tampered event."""
        integrity = AuditIntegrity(secret_key="test-key")
        
        event = AuditEvent(
            event_id="evt-123",
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
            outcome="success",
        )
        
        signed = integrity.sign_event(event)
        
        # Tamper with event
        signed.action = "tampered"
        
        assert integrity.verify_event(signed) is False
    
    def test_verify_chain(self, actor):
        """Should verify event chain."""
        integrity = AuditIntegrity(secret_key="test-key")
        
        events = []
        for i in range(5):
            event = AuditEvent(
                event_id=f"evt-{i}",
                timestamp=datetime(2024, 1, 15, 12, 0, i, tzinfo=timezone.utc),
                event_type=AuditEventType.API_CALL,
                category=AuditEventCategory.API,
                severity=AuditSeverity.INFO,
                actor=actor,
                action=f"action-{i}",
                outcome="success",
            )
            events.append(integrity.sign_event(event))
        
        assert integrity.verify_chain(events) is True
    
    def test_detect_broken_chain(self, actor):
        """Should detect broken chain."""
        integrity = AuditIntegrity(secret_key="test-key")
        
        events = []
        for i in range(3):
            event = AuditEvent(
                event_id=f"evt-{i}",
                timestamp=datetime(2024, 1, 15, 12, 0, i, tzinfo=timezone.utc),
                event_type=AuditEventType.API_CALL,
                category=AuditEventCategory.API,
                severity=AuditSeverity.INFO,
                actor=actor,
                action=f"action-{i}",
                outcome="success",
            )
            events.append(integrity.sign_event(event))
        
        # Break the chain
        events[1].previous_hash = "fake-hash"
        
        assert integrity.verify_chain(events) is False


# =============================================================================
# Test: Storage
# =============================================================================

class TestInMemoryStorage:
    """Test InMemoryAuditStorage."""
    
    @pytest.mark.asyncio
    async def test_store_event(self, storage, actor):
        """Should store event."""
        event = AuditEvent(
            event_id="evt-123",
            timestamp=datetime.now(timezone.utc),
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
            outcome="success",
        )
        
        result = await storage.store(event)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_get_by_id(self, storage, actor):
        """Should retrieve event by ID."""
        event = AuditEvent(
            event_id="evt-123",
            timestamp=datetime.now(timezone.utc),
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
            outcome="success",
        )
        
        await storage.store(event)
        
        retrieved = await storage.get_by_id("evt-123")
        assert retrieved is not None
        assert retrieved.event_id == "evt-123"
    
    @pytest.mark.asyncio
    async def test_query_by_time_range(self, storage, actor):
        """Should query by time range."""
        now = datetime.now(timezone.utc)
        
        for i in range(10):
            event = AuditEvent(
                event_id=f"evt-{i}",
                timestamp=now - timedelta(hours=i),
                event_type=AuditEventType.API_CALL,
                category=AuditEventCategory.API,
                severity=AuditSeverity.INFO,
                actor=actor,
                action="api_call",
                outcome="success",
            )
            await storage.store(event)
        
        # Query last 5 hours
        results = await storage.query(
            start_time=now - timedelta(hours=5),
            end_time=now,
        )
        
        assert len(results) == 6  # 0-5 hours ago
    
    @pytest.mark.asyncio
    async def test_query_by_event_type(self, storage, actor):
        """Should query by event type."""
        event_types = [
            AuditEventType.LOGIN_SUCCESS,
            AuditEventType.LOGIN_FAILURE,
            AuditEventType.LOGIN_SUCCESS,
        ]
        
        for i, et in enumerate(event_types):
            event = AuditEvent(
                event_id=f"evt-{i}",
                timestamp=datetime.now(timezone.utc),
                event_type=et,
                category=AuditEventCategory.AUTHENTICATION,
                severity=AuditSeverity.INFO,
                actor=actor,
                action="login",
                outcome="success" if "SUCCESS" in et.name else "failure",
            )
            await storage.store(event)
        
        results = await storage.query(
            event_types=[AuditEventType.LOGIN_FAILURE],
        )
        
        assert len(results) == 1
    
    @pytest.mark.asyncio
    async def test_query_by_actor(self, storage, actor):
        """Should query by actor ID."""
        other_actor = AuditActor(
            actor_id="other-user",
            actor_type="user",
        )
        
        for i in range(5):
            a = actor if i < 3 else other_actor
            event = AuditEvent(
                event_id=f"evt-{i}",
                timestamp=datetime.now(timezone.utc),
                event_type=AuditEventType.API_CALL,
                category=AuditEventCategory.API,
                severity=AuditSeverity.INFO,
                actor=a,
                action="api_call",
                outcome="success",
            )
            await storage.store(event)
        
        results = await storage.query(actor_id="user-123")
        assert len(results) == 3
    
    @pytest.mark.asyncio
    async def test_query_pagination(self, storage, actor):
        """Should support pagination."""
        for i in range(20):
            event = AuditEvent(
                event_id=f"evt-{i}",
                timestamp=datetime.now(timezone.utc),
                event_type=AuditEventType.API_CALL,
                category=AuditEventCategory.API,
                severity=AuditSeverity.INFO,
                actor=actor,
                action="api_call",
                outcome="success",
            )
            await storage.store(event)
        
        page1 = await storage.query(limit=10, offset=0)
        page2 = await storage.query(limit=10, offset=10)
        
        assert len(page1) == 10
        assert len(page2) == 10
        assert page1[0].event_id != page2[0].event_id
    
    @pytest.mark.asyncio
    async def test_max_events_trimming(self, actor):
        """Should trim old events when max reached."""
        storage = InMemoryAuditStorage(max_events=5)
        
        for i in range(10):
            event = AuditEvent(
                event_id=f"evt-{i}",
                timestamp=datetime.now(timezone.utc),
                event_type=AuditEventType.API_CALL,
                category=AuditEventCategory.API,
                severity=AuditSeverity.INFO,
                actor=actor,
                action="api_call",
                outcome="success",
            )
            await storage.store(event)
        
        results = await storage.query()
        assert len(results) == 5
        
        # First events should be trimmed
        assert await storage.get_by_id("evt-0") is None
        assert await storage.get_by_id("evt-9") is not None


# =============================================================================
# Test: Audit Logger
# =============================================================================

class TestAuditLogger:
    """Test AuditLogger main class."""
    
    @pytest.mark.asyncio
    async def test_log_event(self, audit_logger, actor):
        """Should log event."""
        event = await audit_logger.log(
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
            outcome="success",
            message="Test login",
        )
        
        assert event.event_id is not None
        assert event.integrity_hash is not None
    
    @pytest.mark.asyncio
    async def test_log_with_resource(self, audit_logger, actor, resource):
        """Should log event with resource."""
        event = await audit_logger.log(
            event_type=AuditEventType.DATA_READ,
            category=AuditEventCategory.DATA_ACCESS,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="read",
            outcome="success",
            resource=resource,
        )
        
        assert event.resource is not None
        assert event.resource.resource_id == "doc-123"
    
    @pytest.mark.asyncio
    async def test_log_with_context(self, audit_logger, actor, context):
        """Should log event with context."""
        event = await audit_logger.log(
            event_type=AuditEventType.API_CALL,
            category=AuditEventCategory.API,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="api_call",
            outcome="success",
            context=context,
        )
        
        assert event.context is not None
        assert event.context.endpoint == "/api/v1/test"
    
    @pytest.mark.asyncio
    async def test_query_events(self, audit_logger, actor):
        """Should query logged events."""
        await audit_logger.log(
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
            outcome="success",
        )
        
        events = await audit_logger.query()
        assert len(events) == 1
    
    @pytest.mark.asyncio
    async def test_get_event(self, audit_logger, actor):
        """Should get event by ID."""
        logged = await audit_logger.log(
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
            outcome="success",
        )
        
        retrieved = await audit_logger.get_event(logged.event_id)
        assert retrieved is not None
        assert retrieved.event_id == logged.event_id
    
    @pytest.mark.asyncio
    async def test_hook_called(self, audit_logger, actor):
        """Should call registered hooks."""
        hook_called = []
        
        def test_hook(event: AuditEvent):
            hook_called.append(event)
        
        audit_logger.add_hook(test_hook)
        
        await audit_logger.log(
            event_type=AuditEventType.LOGIN_SUCCESS,
            category=AuditEventCategory.AUTHENTICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action="login",
            outcome="success",
        )
        
        assert len(hook_called) == 1


# =============================================================================
# Test: Convenience Methods
# =============================================================================

class TestConvenienceMethods:
    """Test audit logger convenience methods."""
    
    @pytest.mark.asyncio
    async def test_log_login_success(self, audit_logger):
        """Should log successful login."""
        event = await audit_logger.log_login_success(
            user_id="user-123",
            username="testuser",
            ip_address="192.168.1.100",
            mfa_used=True,
        )
        
        assert event.event_type == AuditEventType.LOGIN_SUCCESS
        assert event.outcome == "success"
        assert event.details["mfa_used"] is True
    
    @pytest.mark.asyncio
    async def test_log_login_failure(self, audit_logger):
        """Should log failed login."""
        event = await audit_logger.log_login_failure(
            username="testuser",
            ip_address="192.168.1.100",
            reason="invalid_password",
        )
        
        assert event.event_type == AuditEventType.LOGIN_FAILURE
        assert event.outcome == "failure"
        assert event.severity == AuditSeverity.WARNING
    
    @pytest.mark.asyncio
    async def test_log_access_denied(self, audit_logger, actor, resource):
        """Should log access denied."""
        event = await audit_logger.log_access_denied(
            actor=actor,
            resource=resource,
            required_permission="admin:write",
        )
        
        assert event.event_type == AuditEventType.ACCESS_DENIED
        assert event.details["required_permission"] == "admin:write"
    
    @pytest.mark.asyncio
    async def test_log_data_access(self, audit_logger, actor, resource):
        """Should log data access."""
        event = await audit_logger.log_data_access(
            actor=actor,
            resource=resource,
            access_type="read",
            fields_accessed=["name", "email"],
        )
        
        assert event.event_type == AuditEventType.DATA_READ
        assert "name" in event.details["fields_accessed"]
    
    @pytest.mark.asyncio
    async def test_log_data_modification(self, audit_logger, actor, resource):
        """Should log data modification."""
        event = await audit_logger.log_data_modification(
            actor=actor,
            resource=resource,
            operation="update",
            changes={"status": {"old": "draft", "new": "published"}},
        )
        
        assert event.event_type == AuditEventType.DATA_UPDATE
        assert "changes" in event.details
    
    @pytest.mark.asyncio
    async def test_log_security_event(self, audit_logger, actor):
        """Should log security event."""
        event = await audit_logger.log_security_event(
            event_type=AuditEventType.INJECTION_ATTEMPT,
            actor=actor,
            description="SQL injection attempt detected",
            severity=AuditSeverity.CRITICAL,
            details={"payload": "'; DROP TABLE users;--"},
        )
        
        assert event.event_type == AuditEventType.INJECTION_ATTEMPT
        assert event.severity == AuditSeverity.CRITICAL
        assert "security" in event.tags
    
    @pytest.mark.asyncio
    async def test_log_sensitive_data_access(self, audit_logger, actor, resource):
        """Should log sensitive data access."""
        event = await audit_logger.log_sensitive_data_access(
            actor=actor,
            resource=resource,
            data_classification="PII",
            reason="Customer support request",
        )
        
        assert event.event_type == AuditEventType.SENSITIVE_DATA_ACCESS
        assert event.details["data_classification"] == "PII"
        assert "pii" in event.tags


# =============================================================================
# Test: Singleton
# =============================================================================

class TestSingleton:
    """Test singleton pattern."""
    
    def test_get_instance(self):
        """Should return singleton instance."""
        logger1 = AuditLogger.get_instance()
        logger2 = AuditLogger.get_instance()
        assert logger1 is logger2
    
    def test_configure_creates_new_instance(self):
        """Should configure new instance."""
        logger = AuditLogger.configure(
            service_name="custom-service",
            environment="production",
        )
        
        assert logger._service_name == "custom-service"
        assert logger._environment == "production"


# =============================================================================
# Test: Decorator
# =============================================================================

class TestAuditDecorator:
    """Test audit_action decorator."""
    
    @pytest.mark.asyncio
    async def test_decorator_logs_success(self):
        """Should log successful action."""
        storage = InMemoryAuditStorage()
        AuditLogger.configure(storage=storage)
        
        @audit_action(
            event_type=AuditEventType.DATA_CREATE,
            category=AuditEventCategory.DATA_MODIFICATION,
            action="create_item",
        )
        async def create_item(data: dict, actor: AuditActor):
            return {"id": "new-123"}
        
        actor = AuditActor(actor_id="user-123", actor_type="user")
        result = await create_item({"name": "test"}, actor=actor)
        
        assert result["id"] == "new-123"
        
        events = await storage.query()
        assert len(events) == 1
        assert events[0].outcome == "success"
    
    @pytest.mark.asyncio
    async def test_decorator_logs_failure(self):
        """Should log failed action."""
        storage = InMemoryAuditStorage()
        AuditLogger.configure(storage=storage)
        
        @audit_action(
            event_type=AuditEventType.DATA_CREATE,
            category=AuditEventCategory.DATA_MODIFICATION,
            action="create_item",
        )
        async def failing_action(actor: AuditActor):
            raise ValueError("Test error")
        
        actor = AuditActor(actor_id="user-123", actor_type="user")
        
        with pytest.raises(ValueError):
            await failing_action(actor=actor)
        
        events = await storage.query()
        assert len(events) == 1
        assert events[0].outcome == "failure"
        assert events[0].severity == AuditSeverity.ERROR


# =============================================================================
# Test: Global Function
# =============================================================================

class TestGlobalFunction:
    """Test get_audit_logger function."""
    
    def test_get_audit_logger(self):
        """Should return logger instance."""
        logger = get_audit_logger()
        assert isinstance(logger, AuditLogger)
