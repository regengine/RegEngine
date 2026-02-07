"""
Tests for SEC-055: Security Event Logging Module.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

from shared.security_event_logging import (
    SecurityEventType,
    EventSeverity,
    SecurityEventConfig,
    SecurityEvent,
    EventBuilder,
    EventHasher,
    EventStore,
    EventFilter,
    EventHandler,
    ConsoleEventHandler,
    CallbackEventHandler,
    SecurityEventLogger,
    SecurityEventLoggingService,
    get_security_logger,
    log_security_event,
    log_auth_success,
    log_auth_failure,
)


class TestSecurityEventType:
    """Tests for SecurityEventType enum."""
    
    def test_auth_events(self):
        """Test authentication event types."""
        assert SecurityEventType.AUTHENTICATION_SUCCESS.value == "auth_success"
        assert SecurityEventType.AUTHENTICATION_FAILURE.value == "auth_failure"
    
    def test_authz_events(self):
        """Test authorization event types."""
        assert SecurityEventType.AUTHORIZATION_SUCCESS.value == "authz_success"
        assert SecurityEventType.AUTHORIZATION_FAILURE.value == "authz_failure"
    
    def test_session_events(self):
        """Test session event types."""
        assert SecurityEventType.SESSION_CREATED.value == "session_created"
        assert SecurityEventType.SESSION_DESTROYED.value == "session_destroyed"
        assert SecurityEventType.SESSION_EXPIRED.value == "session_expired"
    
    def test_security_events(self):
        """Test security alert event types."""
        assert SecurityEventType.SECURITY_ALERT.value == "security_alert"
        assert SecurityEventType.INJECTION_ATTEMPT.value == "injection_attempt"
        assert SecurityEventType.SUSPICIOUS_ACTIVITY.value == "suspicious_activity"


class TestEventSeverity:
    """Tests for EventSeverity enum."""
    
    def test_severity_levels(self):
        """Test severity level values."""
        assert EventSeverity.DEBUG.value == "debug"
        assert EventSeverity.INFO.value == "info"
        assert EventSeverity.WARNING.value == "warning"
        assert EventSeverity.ERROR.value == "error"
        assert EventSeverity.CRITICAL.value == "critical"


class TestSecurityEventConfig:
    """Tests for SecurityEventConfig."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = SecurityEventConfig()
        assert config.max_events_in_memory == 10000
        assert config.include_stack_trace is False
        assert config.hash_sensitive_data is True
        assert config.enable_correlation is True
        assert config.retention_hours == 168
        assert config.min_severity == EventSeverity.INFO
    
    def test_custom_values(self):
        """Test custom configuration values."""
        config = SecurityEventConfig(
            max_events_in_memory=5000,
            min_severity=EventSeverity.WARNING
        )
        assert config.max_events_in_memory == 5000
        assert config.min_severity == EventSeverity.WARNING


class TestSecurityEvent:
    """Tests for SecurityEvent dataclass."""
    
    def test_create_event(self):
        """Test creating a security event."""
        event = SecurityEvent(
            event_id="test-123",
            event_type=SecurityEventType.AUTHENTICATION_SUCCESS,
            severity=EventSeverity.INFO,
            timestamp=datetime.now(timezone.utc),
            message="User logged in",
            source="auth_service",
            user_id="user123"
        )
        assert event.event_id == "test-123"
        assert event.event_type == SecurityEventType.AUTHENTICATION_SUCCESS
        assert event.severity == EventSeverity.INFO
        assert event.user_id == "user123"
    
    def test_to_dict(self):
        """Test converting event to dictionary."""
        event = SecurityEvent(
            event_id="test-123",
            event_type=SecurityEventType.AUTHENTICATION_SUCCESS,
            severity=EventSeverity.INFO,
            timestamp=datetime.now(timezone.utc),
            message="Test message",
            source="test"
        )
        d = event.to_dict()
        assert d["event_id"] == "test-123"
        assert d["event_type"] == "auth_success"
        assert d["severity"] == "info"
    
    def test_to_json(self):
        """Test converting event to JSON."""
        event = SecurityEvent(
            event_id="test-123",
            event_type=SecurityEventType.AUTHENTICATION_SUCCESS,
            severity=EventSeverity.INFO,
            timestamp=datetime.now(timezone.utc),
            message="Test message",
            source="test"
        )
        json_str = event.to_json()
        assert "test-123" in json_str
        assert "auth_success" in json_str


class TestEventBuilder:
    """Tests for EventBuilder."""
    
    def test_basic_build(self):
        """Test basic event building."""
        builder = EventBuilder(
            SecurityEventType.AUTHENTICATION_SUCCESS,
            "Login successful",
            "auth_service"
        )
        event = builder.build()
        assert event.event_type == SecurityEventType.AUTHENTICATION_SUCCESS
        assert event.message == "Login successful"
        assert event.source == "auth_service"
    
    def test_with_severity(self):
        """Test setting severity."""
        event = EventBuilder(
            SecurityEventType.SECURITY_ALERT,
            "Alert",
            "security"
        ).severity(EventSeverity.CRITICAL).build()
        assert event.severity == EventSeverity.CRITICAL
    
    def test_with_user(self):
        """Test setting user ID."""
        event = EventBuilder(
            SecurityEventType.AUTHENTICATION_SUCCESS,
            "Login",
            "auth"
        ).user("user123").build()
        assert event.user_id == "user123"
    
    def test_with_session(self):
        """Test setting session ID."""
        event = EventBuilder(
            SecurityEventType.SESSION_CREATED,
            "Session created",
            "session"
        ).session("sess123").build()
        assert event.session_id == "sess123"
    
    def test_with_ip(self):
        """Test setting IP address."""
        event = EventBuilder(
            SecurityEventType.AUTHENTICATION_SUCCESS,
            "Login",
            "auth"
        ).ip("192.168.1.1").build()
        assert event.ip_address == "192.168.1.1"
    
    def test_with_resource(self):
        """Test setting resource."""
        event = EventBuilder(
            SecurityEventType.ACCESS_DENIED,
            "Access denied",
            "authz"
        ).resource("/api/admin").build()
        assert event.resource == "/api/admin"
    
    def test_with_action(self):
        """Test setting action."""
        event = EventBuilder(
            SecurityEventType.ACCESS_DENIED,
            "Access denied",
            "authz"
        ).action("DELETE").build()
        assert event.action == "DELETE"
    
    def test_with_outcome(self):
        """Test setting outcome."""
        event = EventBuilder(
            SecurityEventType.AUTHENTICATION_FAILURE,
            "Login failed",
            "auth"
        ).outcome("invalid_password").build()
        assert event.outcome == "invalid_password"
    
    def test_with_detail(self):
        """Test adding single detail."""
        event = EventBuilder(
            SecurityEventType.AUTHENTICATION_FAILURE,
            "Login failed",
            "auth"
        ).detail("attempts", 3).build()
        assert event.details["attempts"] == 3
    
    def test_with_details(self):
        """Test adding multiple details."""
        event = EventBuilder(
            SecurityEventType.AUTHENTICATION_FAILURE,
            "Login failed",
            "auth"
        ).details({"attempts": 3, "reason": "bad_password"}).build()
        assert event.details["attempts"] == 3
        assert event.details["reason"] == "bad_password"
    
    def test_with_correlation(self):
        """Test setting correlation ID."""
        event = EventBuilder(
            SecurityEventType.AUTHENTICATION_SUCCESS,
            "Login",
            "auth"
        ).correlate("corr-123").build()
        assert event.correlation_id == "corr-123"
    
    def test_fluent_chain(self):
        """Test fluent method chaining."""
        event = EventBuilder(
            SecurityEventType.AUTHENTICATION_SUCCESS,
            "Login successful",
            "auth_service"
        ).severity(EventSeverity.INFO).user("user123").ip("10.0.0.1").session("sess456").build()
        
        assert event.severity == EventSeverity.INFO
        assert event.user_id == "user123"
        assert event.ip_address == "10.0.0.1"
        assert event.session_id == "sess456"


class TestEventHasher:
    """Tests for EventHasher."""
    
    def test_hash_event(self):
        """Test hashing an event."""
        hasher = EventHasher()
        event = EventBuilder(
            SecurityEventType.AUTHENTICATION_SUCCESS,
            "Login",
            "auth"
        ).build()
        
        hash_val = hasher.hash_event(event)
        assert hash_val is not None
        assert len(hash_val) == 64  # SHA256 hex
        assert event.event_hash == hash_val
    
    def test_chain_link(self):
        """Test hash chain linking."""
        hasher = EventHasher()
        
        event1 = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "First", "auth").build()
        event2 = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "Second", "auth").build()
        
        hash1 = hasher.hash_event(event1)
        hash2 = hasher.hash_event(event2)
        
        assert event1.previous_hash is None
        assert event2.previous_hash == hash1
    
    def test_verify_valid_chain(self):
        """Test verification of valid chain."""
        hasher = EventHasher()
        
        events = []
        for i in range(5):
            event = EventBuilder(
                SecurityEventType.AUTHENTICATION_SUCCESS,
                f"Event {i}",
                "auth"
            ).build()
            hasher.hash_event(event)
            events.append(event)
        
        assert hasher.verify_chain(events) is True
    
    def test_verify_tampered_chain(self):
        """Test detection of tampered chain."""
        hasher = EventHasher()
        
        events = []
        for i in range(3):
            event = EventBuilder(
                SecurityEventType.AUTHENTICATION_SUCCESS,
                f"Event {i}",
                "auth"
            ).build()
            hasher.hash_event(event)
            events.append(event)
        
        # Tamper with message
        events[1].message = "Tampered"
        
        assert hasher.verify_chain(events) is False
    
    def test_verify_empty_chain(self):
        """Test verification of empty chain."""
        hasher = EventHasher()
        assert hasher.verify_chain([]) is True
    
    def test_reset(self):
        """Test resetting hash chain."""
        hasher = EventHasher()
        event = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "Test", "auth").build()
        hasher.hash_event(event)
        
        hasher.reset()
        
        event2 = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "Test2", "auth").build()
        hasher.hash_event(event2)
        
        assert event2.previous_hash is None


class TestEventStore:
    """Tests for EventStore."""
    
    def test_add_and_get(self):
        """Test adding and getting events."""
        store = EventStore()
        event = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "Test", "auth").build()
        store.add(event)
        
        events = store.get_all()
        assert len(events) == 1
        assert events[0] == event
    
    def test_max_events(self):
        """Test maximum event limit."""
        store = EventStore(max_events=5)
        
        for i in range(10):
            event = EventBuilder(
                SecurityEventType.AUTHENTICATION_SUCCESS,
                f"Event {i}",
                "auth"
            ).build()
            store.add(event)
        
        assert store.count() == 5
    
    def test_get_by_user(self):
        """Test getting events by user."""
        store = EventStore()
        
        event1 = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "E1", "auth").user("user1").build()
        event2 = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "E2", "auth").user("user2").build()
        event3 = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "E3", "auth").user("user1").build()
        
        store.add(event1)
        store.add(event2)
        store.add(event3)
        
        user1_events = store.get_by_user("user1")
        assert len(user1_events) == 2
    
    def test_get_by_session(self):
        """Test getting events by session."""
        store = EventStore()
        
        event1 = EventBuilder(SecurityEventType.SESSION_CREATED, "E1", "session").session("sess1").build()
        event2 = EventBuilder(SecurityEventType.SESSION_DESTROYED, "E2", "session").session("sess1").build()
        
        store.add(event1)
        store.add(event2)
        
        sess_events = store.get_by_session("sess1")
        assert len(sess_events) == 2
    
    def test_get_by_correlation(self):
        """Test getting events by correlation ID."""
        store = EventStore()
        
        event1 = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "E1", "auth").correlate("corr1").build()
        event2 = EventBuilder(SecurityEventType.SESSION_CREATED, "E2", "session").correlate("corr1").build()
        
        store.add(event1)
        store.add(event2)
        
        corr_events = store.get_by_correlation("corr1")
        assert len(corr_events) == 2
    
    def test_get_by_type(self):
        """Test getting events by type."""
        store = EventStore()
        
        event1 = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "E1", "auth").build()
        event2 = EventBuilder(SecurityEventType.AUTHENTICATION_FAILURE, "E2", "auth").build()
        event3 = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "E3", "auth").build()
        
        store.add(event1)
        store.add(event2)
        store.add(event3)
        
        success_events = store.get_by_type(SecurityEventType.AUTHENTICATION_SUCCESS)
        assert len(success_events) == 2
    
    def test_get_recent(self):
        """Test getting recent events."""
        store = EventStore()
        
        for i in range(10):
            event = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, f"Event {i}", "auth").build()
            store.add(event)
        
        recent = store.get_recent(3)
        assert len(recent) == 3
    
    def test_clear(self):
        """Test clearing events."""
        store = EventStore()
        event = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "Test", "auth").build()
        store.add(event)
        
        store.clear()
        assert store.count() == 0


class TestEventFilter:
    """Tests for EventFilter."""
    
    def test_filter_by_severity(self):
        """Test filtering by minimum severity."""
        events = [
            EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "E1", "auth").severity(EventSeverity.INFO).build(),
            EventBuilder(SecurityEventType.AUTHENTICATION_FAILURE, "E2", "auth").severity(EventSeverity.WARNING).build(),
            EventBuilder(SecurityEventType.SECURITY_ALERT, "E3", "security").severity(EventSeverity.CRITICAL).build(),
        ]
        
        filter = EventFilter().min_severity(EventSeverity.WARNING)
        filtered = filter.apply(events)
        
        assert len(filtered) == 2
    
    def test_filter_by_event_types(self):
        """Test filtering by event types."""
        events = [
            EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "E1", "auth").build(),
            EventBuilder(SecurityEventType.AUTHENTICATION_FAILURE, "E2", "auth").build(),
            EventBuilder(SecurityEventType.SESSION_CREATED, "E3", "session").build(),
        ]
        
        filter = EventFilter().event_types([SecurityEventType.AUTHENTICATION_SUCCESS, SecurityEventType.AUTHENTICATION_FAILURE])
        filtered = filter.apply(events)
        
        assert len(filtered) == 2
    
    def test_filter_by_user(self):
        """Test filtering by user ID."""
        events = [
            EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "E1", "auth").user("user1").build(),
            EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "E2", "auth").user("user2").build(),
        ]
        
        filter = EventFilter().user("user1")
        filtered = filter.apply(events)
        
        assert len(filtered) == 1
    
    def test_filter_by_time_range(self):
        """Test filtering by time range."""
        now = datetime.now(timezone.utc)
        
        event1 = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "E1", "auth").build()
        event1.timestamp = now - timedelta(hours=2)
        
        event2 = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "E2", "auth").build()
        event2.timestamp = now - timedelta(hours=1)
        
        event3 = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "E3", "auth").build()
        event3.timestamp = now
        
        filter = EventFilter().time_range(start=now - timedelta(hours=1, minutes=30))
        filtered = filter.apply([event1, event2, event3])
        
        assert len(filtered) == 2


class TestEventHandlers:
    """Tests for event handlers."""
    
    def test_console_handler(self, capsys):
        """Test console event handler."""
        handler = ConsoleEventHandler(min_severity=EventSeverity.INFO)
        event = EventBuilder(
            SecurityEventType.AUTHENTICATION_SUCCESS,
            "Test message",
            "auth"
        ).severity(EventSeverity.INFO).build()
        
        handler.handle(event)
        
        captured = capsys.readouterr()
        assert "Test message" in captured.out
    
    def test_console_handler_filters_severity(self, capsys):
        """Test console handler filters by severity."""
        handler = ConsoleEventHandler(min_severity=EventSeverity.WARNING)
        event = EventBuilder(
            SecurityEventType.AUTHENTICATION_SUCCESS,
            "Test message",
            "auth"
        ).severity(EventSeverity.INFO).build()
        
        handler.handle(event)
        
        captured = capsys.readouterr()
        assert captured.out == ""
    
    def test_callback_handler(self):
        """Test callback event handler."""
        received_events = []
        
        def callback(event):
            received_events.append(event)
        
        handler = CallbackEventHandler(callback)
        event = EventBuilder(
            SecurityEventType.AUTHENTICATION_SUCCESS,
            "Test",
            "auth"
        ).build()
        
        handler.handle(event)
        
        assert len(received_events) == 1
        assert received_events[0] == event


class TestSecurityEventLogger:
    """Tests for SecurityEventLogger."""
    
    def test_log_event(self):
        """Test logging an event."""
        logger = SecurityEventLogger()
        event = EventBuilder(
            SecurityEventType.AUTHENTICATION_SUCCESS,
            "Login",
            "auth"
        ).build()
        
        logged = logger.log(event)
        
        assert logged.event_hash is not None
        assert logger.get_event_count() == 1
    
    def test_log_auth_success(self):
        """Test logging auth success."""
        logger = SecurityEventLogger()
        event = logger.log_auth_success("user123", "auth_service", ip_address="10.0.0.1")
        
        assert event.event_type == SecurityEventType.AUTHENTICATION_SUCCESS
        assert event.user_id == "user123"
        assert event.ip_address == "10.0.0.1"
    
    def test_log_auth_failure(self):
        """Test logging auth failure."""
        logger = SecurityEventLogger()
        event = logger.log_auth_failure("user123", "auth_service", "invalid_password")
        
        assert event.event_type == SecurityEventType.AUTHENTICATION_FAILURE
        assert event.severity == EventSeverity.WARNING
        assert "invalid_password" in event.message
    
    def test_log_access_denied(self):
        """Test logging access denied."""
        logger = SecurityEventLogger()
        event = logger.log_access_denied("user123", "/api/admin", "DELETE", "authz_service")
        
        assert event.event_type == SecurityEventType.ACCESS_DENIED
        assert event.resource == "/api/admin"
        assert event.action == "DELETE"
    
    def test_log_security_alert(self):
        """Test logging security alert."""
        logger = SecurityEventLogger()
        event = logger.log_security_alert("Brute force detected", "security_monitor")
        
        assert event.event_type == SecurityEventType.SECURITY_ALERT
        assert event.severity == EventSeverity.CRITICAL
    
    def test_handler_notification(self):
        """Test handlers are notified."""
        received = []
        handler = CallbackEventHandler(lambda e: received.append(e))
        
        logger = SecurityEventLogger()
        logger.add_handler(handler)
        
        event = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "Test", "auth").build()
        logger.log(event)
        
        assert len(received) == 1
    
    def test_remove_handler(self):
        """Test removing handler."""
        received = []
        handler = CallbackEventHandler(lambda e: received.append(e))
        
        logger = SecurityEventLogger()
        logger.add_handler(handler)
        logger.remove_handler(handler)
        
        event = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "Test", "auth").build()
        logger.log(event)
        
        assert len(received) == 0
    
    def test_min_severity_filter(self):
        """Test minimum severity filtering."""
        config = SecurityEventConfig(min_severity=EventSeverity.WARNING)
        logger = SecurityEventLogger(config)
        
        event = EventBuilder(
            SecurityEventType.AUTHENTICATION_SUCCESS,
            "Login",
            "auth"
        ).severity(EventSeverity.INFO).build()
        
        logger.log(event)
        
        # Event below min severity should not be stored
        assert logger.get_event_count() == 0
    
    def test_get_user_events(self):
        """Test getting events by user."""
        logger = SecurityEventLogger()
        logger.log_auth_success("user1", "auth")
        logger.log_auth_success("user2", "auth")
        logger.log_auth_success("user1", "auth")
        
        user1_events = logger.get_user_events("user1")
        assert len(user1_events) == 2
    
    def test_query_with_filter(self):
        """Test querying with filter."""
        logger = SecurityEventLogger()
        logger.log_auth_success("user1", "auth")
        logger.log_auth_failure("user2", "auth", "bad_password")
        logger.log_security_alert("Alert", "security")
        
        filter = EventFilter().min_severity(EventSeverity.WARNING)
        results = logger.query(filter)
        
        assert len(results) == 2
    
    def test_verify_integrity(self):
        """Test integrity verification."""
        logger = SecurityEventLogger()
        logger.log_auth_success("user1", "auth")
        logger.log_auth_success("user2", "auth")
        
        assert logger.verify_integrity() is True
    
    def test_clear(self):
        """Test clearing logger."""
        logger = SecurityEventLogger()
        logger.log_auth_success("user1", "auth")
        logger.clear()
        
        assert logger.get_event_count() == 0


class TestSecurityEventLoggingService:
    """Tests for SecurityEventLoggingService."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        SecurityEventLoggingService.reset()
    
    def test_singleton(self):
        """Test singleton pattern."""
        svc1 = SecurityEventLoggingService()
        svc2 = SecurityEventLoggingService()
        assert svc1 is svc2
    
    def test_configure(self):
        """Test configuration update."""
        svc = SecurityEventLoggingService()
        config = SecurityEventConfig(max_events_in_memory=5000)
        svc.configure(config)
        assert svc.get_config().max_events_in_memory == 5000
    
    def test_get_logger(self):
        """Test getting logger."""
        svc = SecurityEventLoggingService()
        logger = svc.get_logger()
        assert isinstance(logger, SecurityEventLogger)
    
    def test_log_event(self):
        """Test logging through service."""
        svc = SecurityEventLoggingService()
        event = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "Test", "auth").build()
        logged = svc.log_event(event)
        assert logged.event_hash is not None
    
    def test_create_event(self):
        """Test creating event builder."""
        svc = SecurityEventLoggingService()
        builder = svc.create_event(SecurityEventType.AUTHENTICATION_SUCCESS, "Test", "auth")
        assert isinstance(builder, EventBuilder)
    
    def test_get_events(self):
        """Test getting events."""
        svc = SecurityEventLoggingService()
        event = EventBuilder(SecurityEventType.AUTHENTICATION_SUCCESS, "Test", "auth").build()
        svc.log_event(event)
        
        events = svc.get_events()
        assert len(events) == 1


class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        SecurityEventLoggingService.reset()
    
    def test_get_security_logger(self):
        """Test getting service singleton."""
        svc = get_security_logger()
        assert isinstance(svc, SecurityEventLoggingService)
    
    def test_log_security_event(self):
        """Test log_security_event function."""
        event = log_security_event(
            SecurityEventType.SECURITY_ALERT,
            "Test alert",
            "test_source",
            severity=EventSeverity.CRITICAL
        )
        assert event.event_type == SecurityEventType.SECURITY_ALERT
        assert event.severity == EventSeverity.CRITICAL
    
    def test_log_auth_success_function(self):
        """Test log_auth_success function."""
        event = log_auth_success("user123", "auth_service")
        assert event.event_type == SecurityEventType.AUTHENTICATION_SUCCESS
        assert event.user_id == "user123"
    
    def test_log_auth_failure_function(self):
        """Test log_auth_failure function."""
        event = log_auth_failure("user123", "auth_service", "bad_password")
        assert event.event_type == SecurityEventType.AUTHENTICATION_FAILURE
