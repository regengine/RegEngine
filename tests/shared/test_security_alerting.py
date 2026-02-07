"""
Tests for SEC-019: Security Event Alerting.

Tests cover:
- Alert creation and sending
- Multi-channel delivery
- Alert deduplication
- Alert status management
- Convenience functions
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from shared.security_alerting import (
    # Enums
    AlertSeverity,
    AlertChannel,
    AlertStatus,
    AlertCategory,
    # Data classes
    SecurityAlert,
    AlertRule,
    AlertConfig,
    # Handlers
    AlertChannelHandler,
    LogChannelHandler,
    ConsoleChannelHandler,
    WebhookChannelHandler,
    SlackChannelHandler,
    EmailChannelHandler,
    # Manager
    AlertManager,
    # Functions
    get_alert_manager,
    send_security_alert,
    alert_login_failure,
    alert_access_denied,
    alert_suspicious_activity,
    alert_data_breach_attempt,
    alert_injection_attempt,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create test config."""
    return AlertConfig(
        enabled=True,
        default_channels=[AlertChannel.LOG],
        deduplication_window_seconds=60,
        # Override severity channels to only use LOG for all severities
        severity_channels={
            AlertSeverity.CRITICAL: [AlertChannel.LOG],
            AlertSeverity.HIGH: [AlertChannel.LOG],
            AlertSeverity.MEDIUM: [AlertChannel.LOG],
            AlertSeverity.LOW: [AlertChannel.LOG],
            AlertSeverity.INFO: [AlertChannel.LOG],
        },
    )


@pytest.fixture
def manager(config):
    """Create test manager."""
    return AlertManager(config=config)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_alert_severity(self):
        """Should have expected severity levels."""
        assert AlertSeverity.INFO == "info"
        assert AlertSeverity.CRITICAL == "critical"
    
    def test_alert_channel(self):
        """Should have expected channels."""
        assert AlertChannel.EMAIL == "email"
        assert AlertChannel.SLACK == "slack"
        assert AlertChannel.WEBHOOK == "webhook"
    
    def test_alert_status(self):
        """Should have expected statuses."""
        assert AlertStatus.PENDING == "pending"
        assert AlertStatus.SENT == "sent"
        assert AlertStatus.ACKNOWLEDGED == "acknowledged"
    
    def test_alert_category(self):
        """Should have expected categories."""
        assert AlertCategory.AUTHENTICATION == "authentication"
        assert AlertCategory.INTRUSION == "intrusion"


# =============================================================================
# Test: Security Alert
# =============================================================================

class TestSecurityAlert:
    """Test SecurityAlert data class."""
    
    def test_creation(self):
        """Should create alert with all fields."""
        alert = SecurityAlert(
            alert_id="alert-123",
            timestamp=datetime.now(timezone.utc),
            severity=AlertSeverity.HIGH,
            category=AlertCategory.AUTHENTICATION,
            title="Test Alert",
            description="Test description",
            source="test",
            user_id="user-123",
            ip_address="192.168.1.100",
        )
        
        assert alert.alert_id == "alert-123"
        assert alert.severity == AlertSeverity.HIGH
        assert alert.status == AlertStatus.PENDING
    
    def test_to_dict(self):
        """Should convert to dictionary."""
        alert = SecurityAlert(
            alert_id="alert-123",
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            severity=AlertSeverity.CRITICAL,
            category=AlertCategory.INTRUSION,
            title="Critical Alert",
            description="Something bad happened",
            source="detector",
            user_id="hacker",
            ip_address="10.0.0.1",
            tags=["intrusion", "critical"],
        )
        
        data = alert.to_dict()
        
        assert data["alert_id"] == "alert-123"
        assert data["severity"] == "critical"
        assert data["category"] == "intrusion"
        assert "intrusion" in data["tags"]
    
    def test_to_json(self):
        """Should convert to JSON."""
        alert = SecurityAlert(
            alert_id="alert-123",
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            severity=AlertSeverity.MEDIUM,
            category=AlertCategory.AUTHORIZATION,
            title="Access Denied",
            description="Unauthorized access attempt",
            source="auth",
        )
        
        json_str = alert.to_json()
        
        assert '"alert_id": "alert-123"' in json_str
        assert '"severity": "medium"' in json_str


# =============================================================================
# Test: Alert Rule
# =============================================================================

class TestAlertRule:
    """Test AlertRule data class."""
    
    def test_creation(self):
        """Should create rule with defaults."""
        rule = AlertRule(
            rule_id="rule-1",
            name="Test Rule",
            description="Test rule description",
        )
        
        assert rule.rule_id == "rule-1"
        assert rule.enabled is True
        assert rule.severity == AlertSeverity.MEDIUM
    
    def test_matches_event_type(self):
        """Should match event type."""
        rule = AlertRule(
            rule_id="rule-1",
            name="Login Rule",
            description="Alert on login failures",
            event_types=["login_failure", "auth_error"],
        )
        
        assert rule.matches_event({"event_type": "login_failure"}) is True
        assert rule.matches_event({"event_type": "auth_error"}) is True
        assert rule.matches_event({"event_type": "data_access"}) is False
    
    def test_matches_severity(self):
        """Should filter by minimum severity."""
        rule = AlertRule(
            rule_id="rule-1",
            name="High Severity Rule",
            description="Alert on high+ severity",
            min_severity=AlertSeverity.HIGH,
        )
        
        assert rule.matches_event({"severity": "critical"}) is True
        assert rule.matches_event({"severity": "high"}) is True
        assert rule.matches_event({"severity": "medium"}) is False
        assert rule.matches_event({"severity": "low"}) is False
    
    def test_disabled_rule_no_match(self):
        """Should not match if disabled."""
        rule = AlertRule(
            rule_id="rule-1",
            name="Disabled Rule",
            description="This rule is disabled",
            enabled=False,
        )
        
        assert rule.matches_event({"event_type": "anything"}) is False


# =============================================================================
# Test: Channel Handlers
# =============================================================================

class TestLogChannelHandler:
    """Test LogChannelHandler."""
    
    @pytest.mark.asyncio
    async def test_send_logs_alert(self, caplog):
        """Should log the alert."""
        handler = LogChannelHandler()
        
        alert = SecurityAlert(
            alert_id="alert-123",
            timestamp=datetime.now(timezone.utc),
            severity=AlertSeverity.HIGH,
            category=AlertCategory.AUTHENTICATION,
            title="Login Failed",
            description="Too many failed attempts",
            source="auth",
            user_id="testuser",
            ip_address="192.168.1.100",
        )
        
        result = await handler.send(alert)
        
        assert result is True
        assert handler.channel_type == AlertChannel.LOG


class TestConsoleChannelHandler:
    """Test ConsoleChannelHandler."""
    
    @pytest.mark.asyncio
    async def test_send_prints_alert(self, capsys):
        """Should print the alert."""
        handler = ConsoleChannelHandler()
        
        alert = SecurityAlert(
            alert_id="alert-123",
            timestamp=datetime.now(timezone.utc),
            severity=AlertSeverity.CRITICAL,
            category=AlertCategory.INTRUSION,
            title="Intrusion Detected",
            description="Malicious activity detected",
            source="ids",
        )
        
        result = await handler.send(alert)
        
        assert result is True
        assert handler.channel_type == AlertChannel.CONSOLE
        
        captured = capsys.readouterr()
        assert "SECURITY ALERT" in captured.out
        assert "CRITICAL" in captured.out


class TestEmailChannelHandler:
    """Test EmailChannelHandler."""
    
    @pytest.mark.asyncio
    async def test_send_email_placeholder(self):
        """Should handle email sending (placeholder)."""
        handler = EmailChannelHandler(
            to_addresses=["security@example.com"],
        )
        
        alert = SecurityAlert(
            alert_id="alert-123",
            timestamp=datetime.now(timezone.utc),
            severity=AlertSeverity.HIGH,
            category=AlertCategory.AUTHENTICATION,
            title="Test Alert",
            description="Test",
            source="test",
        )
        
        result = await handler.send(alert)
        
        assert result is True
        assert handler.channel_type == AlertChannel.EMAIL


# =============================================================================
# Test: Alert Manager
# =============================================================================

class TestAlertManager:
    """Test AlertManager."""
    
    @pytest.mark.asyncio
    async def test_create_alert(self, manager):
        """Should create and send alert."""
        alert = await manager.create_alert(
            severity=AlertSeverity.HIGH,
            category=AlertCategory.AUTHENTICATION,
            title="Test Alert",
            description="Test description",
            source="test",
            user_id="user-123",
            ip_address="192.168.1.100",
        )
        
        assert alert.alert_id is not None
        assert alert.severity == AlertSeverity.HIGH
        assert alert.status == AlertStatus.SENT
        assert AlertChannel.LOG in alert.channels_sent
    
    @pytest.mark.asyncio
    async def test_disabled_config(self):
        """Should suppress alerts when disabled."""
        config = AlertConfig(enabled=False)
        manager = AlertManager(config=config)
        
        alert = await manager.create_alert(
            severity=AlertSeverity.CRITICAL,
            category=AlertCategory.INTRUSION,
            title="Suppressed Alert",
            description="This should be suppressed",
            source="test",
        )
        
        assert alert.status == AlertStatus.SUPPRESSED
    
    @pytest.mark.asyncio
    async def test_deduplication(self, manager):
        """Should deduplicate similar alerts."""
        # First alert
        alert1 = await manager.create_alert(
            severity=AlertSeverity.MEDIUM,
            category=AlertCategory.AUTHENTICATION,
            title="Duplicate Test",
            description="First occurrence",
            source="test",
            user_id="user-123",
        )
        
        # Second similar alert (should be suppressed)
        alert2 = await manager.create_alert(
            severity=AlertSeverity.MEDIUM,
            category=AlertCategory.AUTHENTICATION,
            title="Duplicate Test",
            description="Second occurrence",
            source="test",
            user_id="user-123",
        )
        
        assert alert1.status == AlertStatus.SENT
        assert alert2.status == AlertStatus.SUPPRESSED
    
    @pytest.mark.asyncio
    async def test_get_alerts(self, manager):
        """Should retrieve alerts."""
        # Create some alerts
        await manager.create_alert(
            severity=AlertSeverity.LOW,
            category=AlertCategory.SYSTEM,
            title="Alert 1",
            description="First alert",
            source="test",
        )
        
        await manager.create_alert(
            severity=AlertSeverity.HIGH,
            category=AlertCategory.AUTHENTICATION,
            title="Alert 2",
            description="Second alert",
            source="test",
        )
        
        # Get all
        all_alerts = await manager.get_alerts()
        assert len(all_alerts) >= 2
        
        # Filter by severity
        high_alerts = await manager.get_alerts(severity=AlertSeverity.HIGH)
        assert all(a.severity == AlertSeverity.HIGH for a in high_alerts)
    
    @pytest.mark.asyncio
    async def test_acknowledge_alert(self, manager):
        """Should acknowledge alert."""
        alert = await manager.create_alert(
            severity=AlertSeverity.MEDIUM,
            category=AlertCategory.SYSTEM,
            title="Ack Test",
            description="Test acknowledgment",
            source="test",
        )
        
        result = await manager.acknowledge_alert(alert.alert_id)
        assert result is True
        
        # Verify status changed
        alerts = await manager.get_alerts()
        found = next((a for a in alerts if a.alert_id == alert.alert_id), None)
        assert found is not None
        assert found.status == AlertStatus.ACKNOWLEDGED
    
    @pytest.mark.asyncio
    async def test_resolve_alert(self, manager):
        """Should resolve alert."""
        alert = await manager.create_alert(
            severity=AlertSeverity.HIGH,
            category=AlertCategory.INTRUSION,
            title="Resolve Test",
            description="Test resolution",
            source="test",
        )
        
        result = await manager.resolve_alert(alert.alert_id)
        assert result is True
        
        # Verify status changed
        alerts = await manager.get_alerts()
        found = next((a for a in alerts if a.alert_id == alert.alert_id), None)
        assert found is not None
        assert found.status == AlertStatus.RESOLVED
    
    @pytest.mark.asyncio
    async def test_get_alert_stats(self, manager):
        """Should calculate statistics."""
        # Create some alerts
        await manager.create_alert(
            severity=AlertSeverity.LOW,
            category=AlertCategory.SYSTEM,
            title="Stat Test 1",
            description="Test 1",
            source="test",
        )
        
        await manager.create_alert(
            severity=AlertSeverity.HIGH,
            category=AlertCategory.AUTHENTICATION,
            title="Stat Test 2",
            description="Test 2",
            source="test",
        )
        
        stats = await manager.get_alert_stats()
        
        assert stats["total"] >= 2
        assert "by_severity" in stats
        assert "by_category" in stats
        assert "by_status" in stats
    
    @pytest.mark.asyncio
    async def test_register_channel(self, manager):
        """Should register custom channel."""
        # Create mock handler
        mock_handler = MagicMock(spec=AlertChannelHandler)
        mock_handler.channel_type = AlertChannel.WEBHOOK
        mock_handler.send = AsyncMock(return_value=True)
        
        manager.register_channel(mock_handler)
        
        # Create alert using that channel
        alert = await manager.create_alert(
            severity=AlertSeverity.CRITICAL,
            category=AlertCategory.INTRUSION,
            title="Webhook Test",
            description="Test webhook delivery",
            source="test",
            channels=[AlertChannel.WEBHOOK],
        )
        
        # Verify handler was called
        mock_handler.send.assert_called_once()


# =============================================================================
# Test: Convenience Functions
# =============================================================================

def _get_test_config():
    """Get a test config with LOG-only channels."""
    return AlertConfig(
        enabled=True,
        severity_channels={
            AlertSeverity.CRITICAL: [AlertChannel.LOG],
            AlertSeverity.HIGH: [AlertChannel.LOG],
            AlertSeverity.MEDIUM: [AlertChannel.LOG],
            AlertSeverity.LOW: [AlertChannel.LOG],
            AlertSeverity.INFO: [AlertChannel.LOG],
        },
    )


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_get_alert_manager(self):
        """Should return singleton instance."""
        manager1 = get_alert_manager()
        manager2 = get_alert_manager()
        assert manager1 is manager2
    
    @pytest.mark.asyncio
    async def test_send_security_alert(self):
        """Should send alert via convenience function."""
        AlertManager.configure(config=_get_test_config())
        
        alert = await send_security_alert(
            severity=AlertSeverity.MEDIUM,
            category=AlertCategory.SYSTEM,
            title="Convenience Test",
            description="Testing convenience function",
        )
        
        assert alert.title == "Convenience Test"
        assert alert.status == AlertStatus.SENT
    
    @pytest.mark.asyncio
    async def test_alert_login_failure(self):
        """Should send login failure alert."""
        AlertManager.configure(config=_get_test_config())
        
        alert = await alert_login_failure(
            username="testuser",
            ip_address="192.168.1.100",
            reason="Invalid password",
            attempt_count=3,
        )
        
        assert alert.category == AlertCategory.AUTHENTICATION
        assert "testuser" in alert.title
        assert alert.user_id == "testuser"
        assert alert.severity == AlertSeverity.LOW
    
    @pytest.mark.asyncio
    async def test_alert_login_failure_escalates(self):
        """Should escalate severity with more attempts."""
        AlertManager.configure(config=_get_test_config())
        
        alert = await alert_login_failure(
            username="testuser",
            ip_address="192.168.1.100",
            reason="Invalid password",
            attempt_count=10,
        )
        
        assert alert.severity == AlertSeverity.HIGH
    
    @pytest.mark.asyncio
    async def test_alert_access_denied(self):
        """Should send access denied alert."""
        AlertManager.configure(config=_get_test_config())
        
        alert = await alert_access_denied(
            user_id="user-123",
            resource="/api/admin/secrets",
            required_permission="admin:read",
        )
        
        assert alert.category == AlertCategory.AUTHORIZATION
        assert alert.resource == "/api/admin/secrets"
    
    @pytest.mark.asyncio
    async def test_alert_suspicious_activity(self):
        """Should send suspicious activity alert."""
        AlertManager.configure(config=_get_test_config())
        
        alert = await alert_suspicious_activity(
            activity_type="credential_stuffing",
            description="Multiple failed logins from same IP",
            ip_address="10.0.0.1",
        )
        
        assert alert.category == AlertCategory.INTRUSION
        assert alert.severity == AlertSeverity.HIGH
    
    @pytest.mark.asyncio
    async def test_alert_data_breach_attempt(self):
        """Should send data breach alert."""
        AlertManager.configure(config=_get_test_config())
        
        alert = await alert_data_breach_attempt(
            user_id="user-123",
            resource="customer_database",
            data_volume_bytes=100_000_000,  # 100MB
        )
        
        assert alert.category == AlertCategory.DATA_ACCESS
        assert alert.severity == AlertSeverity.CRITICAL
        assert "exfiltration" in alert.title.lower()
    
    @pytest.mark.asyncio
    async def test_alert_injection_attempt(self):
        """Should send injection attempt alert."""
        AlertManager.configure(config=_get_test_config())
        
        alert = await alert_injection_attempt(
            attack_type="SQL",
            payload="'; DROP TABLE users; --",
            ip_address="10.0.0.1",
            endpoint="/api/search",
        )
        
        assert alert.category == AlertCategory.INTRUSION
        assert alert.severity == AlertSeverity.CRITICAL
        assert "SQL" in alert.title


# =============================================================================
# Test: Singleton Pattern
# =============================================================================

class TestSingleton:
    """Test singleton pattern."""
    
    def test_configure_creates_instance(self):
        """Should configure singleton."""
        config = _get_test_config()
        
        manager = AlertManager.configure(config=config)
        
        assert AlertChannel.LOG in manager._config.severity_channels[AlertSeverity.CRITICAL]
        assert AlertManager.get_instance() is manager
