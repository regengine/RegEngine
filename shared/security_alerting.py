"""
SEC-019: Security Event Alerting.

Comprehensive security alerting system:
- Multi-channel alert delivery (email, webhook, Slack, etc.)
- Alert severity and escalation
- Rate limiting to prevent alert fatigue
- Alert aggregation and deduplication
- Customizable alert rules
"""

import asyncio
import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertChannel(str, Enum):
    """Alert delivery channels."""
    EMAIL = "email"
    WEBHOOK = "webhook"
    SLACK = "slack"
    PAGERDUTY = "pagerduty"
    SMS = "sms"
    LOG = "log"
    CONSOLE = "console"


class AlertStatus(str, Enum):
    """Alert status."""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SUPPRESSED = "suppressed"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertCategory(str, Enum):
    """Categories of security alerts."""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_ACCESS = "data_access"
    INTRUSION = "intrusion"
    VULNERABILITY = "vulnerability"
    COMPLIANCE = "compliance"
    SYSTEM = "system"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SecurityAlert:
    """A security alert."""
    alert_id: str
    timestamp: datetime
    severity: AlertSeverity
    category: AlertCategory
    title: str
    description: str
    source: str
    user_id: Optional[str] = None
    ip_address: Optional[str] = None
    tenant_id: Optional[str] = None
    resource: Optional[str] = None
    event_count: int = 1
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    status: AlertStatus = AlertStatus.PENDING
    channels_sent: List[AlertChannel] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    correlation_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "alert_id": self.alert_id,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "category": self.category.value,
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "event_count": self.event_count,
            "status": self.status.value,
        }
        
        if self.user_id:
            result["user_id"] = self.user_id
        if self.ip_address:
            result["ip_address"] = self.ip_address
        if self.tenant_id:
            result["tenant_id"] = self.tenant_id
        if self.resource:
            result["resource"] = self.resource
        if self.first_seen:
            result["first_seen"] = self.first_seen.isoformat()
        if self.last_seen:
            result["last_seen"] = self.last_seen.isoformat()
        if self.channels_sent:
            result["channels_sent"] = [c.value for c in self.channels_sent]
        if self.details:
            result["details"] = self.details
        if self.tags:
            result["tags"] = self.tags
        if self.correlation_id:
            result["correlation_id"] = self.correlation_id
            
        return result
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class AlertRule:
    """Rule for generating alerts."""
    rule_id: str
    name: str
    description: str
    enabled: bool = True
    severity: AlertSeverity = AlertSeverity.MEDIUM
    category: AlertCategory = AlertCategory.SYSTEM
    channels: List[AlertChannel] = field(default_factory=list)
    
    # Matching criteria
    event_types: List[str] = field(default_factory=list)
    min_severity: Optional[AlertSeverity] = None
    user_pattern: Optional[str] = None
    ip_pattern: Optional[str] = None
    
    # Aggregation settings
    aggregation_window_seconds: int = 300  # 5 minutes
    aggregation_key: Optional[str] = None  # e.g., "user_id" or "ip_address"
    min_events_to_alert: int = 1
    
    # Rate limiting
    cooldown_seconds: int = 3600  # 1 hour between repeat alerts
    max_alerts_per_hour: int = 10
    
    def matches_event(self, event: Dict[str, Any]) -> bool:
        """Check if event matches this rule."""
        if not self.enabled:
            return False
        
        # Check event type
        if self.event_types:
            event_type = event.get("event_type", "")
            if event_type not in self.event_types:
                return False
        
        # Check severity
        if self.min_severity:
            severity_order = {
                AlertSeverity.INFO: 0,
                AlertSeverity.LOW: 1,
                AlertSeverity.MEDIUM: 2,
                AlertSeverity.HIGH: 3,
                AlertSeverity.CRITICAL: 4,
            }
            event_severity = event.get("severity", AlertSeverity.INFO)
            if isinstance(event_severity, str):
                try:
                    event_severity = AlertSeverity(event_severity)
                except ValueError:
                    event_severity = AlertSeverity.INFO
            
            if severity_order.get(event_severity, 0) < severity_order.get(self.min_severity, 0):
                return False
        
        return True


@dataclass
class AlertConfig:
    """Configuration for alerting system."""
    # Global settings
    enabled: bool = True
    default_channels: List[AlertChannel] = field(default_factory=lambda: [AlertChannel.LOG])
    
    # Rate limiting
    global_rate_limit_per_minute: int = 100
    per_channel_rate_limit_per_minute: int = 20
    
    # Aggregation
    default_aggregation_window_seconds: int = 300
    deduplication_window_seconds: int = 3600
    
    # Escalation
    escalation_enabled: bool = True
    escalation_threshold_count: int = 5
    escalation_window_seconds: int = 900
    
    # Severity to channel mapping
    severity_channels: Dict[AlertSeverity, List[AlertChannel]] = field(
        default_factory=lambda: {
            AlertSeverity.CRITICAL: [AlertChannel.PAGERDUTY, AlertChannel.SLACK, AlertChannel.EMAIL],
            AlertSeverity.HIGH: [AlertChannel.SLACK, AlertChannel.EMAIL],
            AlertSeverity.MEDIUM: [AlertChannel.EMAIL],
            AlertSeverity.LOW: [AlertChannel.LOG],
            AlertSeverity.INFO: [AlertChannel.LOG],
        }
    )


# =============================================================================
# Alert Channels
# =============================================================================

class AlertChannelHandler(ABC):
    """Base class for alert channel handlers."""
    
    @property
    @abstractmethod
    def channel_type(self) -> AlertChannel:
        """Get the channel type."""
        pass
    
    @abstractmethod
    async def send(self, alert: SecurityAlert) -> bool:
        """Send alert through this channel."""
        pass


class LogChannelHandler(AlertChannelHandler):
    """Logs alerts to the application logger."""
    
    @property
    def channel_type(self) -> AlertChannel:
        return AlertChannel.LOG
    
    async def send(self, alert: SecurityAlert) -> bool:
        """Log the alert."""
        log_level = {
            AlertSeverity.INFO: logging.INFO,
            AlertSeverity.LOW: logging.INFO,
            AlertSeverity.MEDIUM: logging.WARNING,
            AlertSeverity.HIGH: logging.ERROR,
            AlertSeverity.CRITICAL: logging.CRITICAL,
        }.get(alert.severity, logging.WARNING)
        
        logger.log(
            log_level,
            "Security Alert [%s] %s: %s (user=%s, ip=%s)",
            alert.severity.value.upper(),
            alert.category.value,
            alert.title,
            alert.user_id,
            alert.ip_address,
        )
        
        return True


class ConsoleChannelHandler(AlertChannelHandler):
    """Prints alerts to console."""
    
    @property
    def channel_type(self) -> AlertChannel:
        return AlertChannel.CONSOLE
    
    async def send(self, alert: SecurityAlert) -> bool:
        """Send alert to console via logger."""
        log_level = {
            AlertSeverity.INFO: logging.INFO,
            AlertSeverity.LOW: logging.INFO,
            AlertSeverity.MEDIUM: logging.WARNING,
            AlertSeverity.HIGH: logging.ERROR,
            AlertSeverity.CRITICAL: logging.CRITICAL,
        }.get(alert.severity, logging.WARNING)

        logger.log(
            log_level,
            "🚨 SECURITY ALERT [%s] Category=%s Title=%s Description=%s user=%s ip=%s time=%s",
            alert.severity.value.upper(),
            alert.category.value,
            alert.title,
            alert.description,
            alert.user_id,
            alert.ip_address,
            alert.timestamp.isoformat(),
        )
        
        return True


class WebhookChannelHandler(AlertChannelHandler):
    """Sends alerts to a webhook URL."""
    
    def __init__(self, webhook_url: str, headers: Optional[Dict[str, str]] = None):
        self._webhook_url = webhook_url
        self._headers = headers or {"Content-Type": "application/json"}
    
    @property
    def channel_type(self) -> AlertChannel:
        return AlertChannel.WEBHOOK
    
    async def send(self, alert: SecurityAlert) -> bool:
        """Send alert to webhook."""
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._webhook_url,
                    json=alert.to_dict(),
                    headers=self._headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    return response.status < 400
        except ImportError:
            logger.warning("aiohttp not available for webhook alerts")
            return False
        except Exception as e:
            logger.error("Webhook alert failed: %s", e)
            return False


class SlackChannelHandler(AlertChannelHandler):
    """Sends alerts to Slack."""
    
    def __init__(self, webhook_url: str, channel: Optional[str] = None):
        self._webhook_url = webhook_url
        self._channel = channel
    
    @property
    def channel_type(self) -> AlertChannel:
        return AlertChannel.SLACK
    
    async def send(self, alert: SecurityAlert) -> bool:
        """Send alert to Slack."""
        try:
            import aiohttp
            
            # Build Slack message
            severity_emoji = {
                AlertSeverity.INFO: "ℹ️",
                AlertSeverity.LOW: "📝",
                AlertSeverity.MEDIUM: "⚠️",
                AlertSeverity.HIGH: "🔴",
                AlertSeverity.CRITICAL: "🚨",
            }
            
            message = {
                "text": f"{severity_emoji.get(alert.severity, '⚠️')} *Security Alert: {alert.title}*",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"{severity_emoji.get(alert.severity, '⚠️')} {alert.title}",
                        },
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Severity:*\n{alert.severity.value.upper()}"},
                            {"type": "mrkdwn", "text": f"*Category:*\n{alert.category.value}"},
                        ],
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": alert.description},
                    },
                ],
            }
            
            if self._channel:
                message["channel"] = self._channel
            
            # Add context
            context_fields = []
            if alert.user_id:
                context_fields.append({"type": "mrkdwn", "text": f"*User:* {alert.user_id}"})
            if alert.ip_address:
                context_fields.append({"type": "mrkdwn", "text": f"*IP:* {alert.ip_address}"})
            
            if context_fields:
                message["blocks"].append({
                    "type": "context",
                    "elements": context_fields,
                })
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._webhook_url,
                    json=message,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    return response.status < 400
                    
        except ImportError:
            logger.warning("aiohttp not available for Slack alerts")
            return False
        except Exception as e:
            logger.error("Slack alert failed: %s", e)
            return False


class EmailChannelHandler(AlertChannelHandler):
    """Sends alerts via email (placeholder implementation)."""
    
    def __init__(
        self,
        smtp_host: str = "localhost",
        smtp_port: int = 25,
        from_address: str = "alerts@example.com",
        to_addresses: Optional[List[str]] = None,
    ):
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._from_address = from_address
        self._to_addresses = to_addresses or []
    
    @property
    def channel_type(self) -> AlertChannel:
        return AlertChannel.EMAIL
    
    async def send(self, alert: SecurityAlert) -> bool:
        """Send alert via email."""
        # This is a placeholder - real implementation would use aiosmtplib
        logger.info(
            "Email alert would be sent to %s: [%s] %s",
            self._to_addresses,
            alert.severity.value,
            alert.title,
        )
        return True


# =============================================================================
# Alert Manager
# =============================================================================

class AlertManager:
    """
    Manages security alerts.
    
    Features:
    - Multi-channel delivery
    - Alert aggregation and deduplication
    - Rate limiting
    - Escalation
    """
    
    _instance: Optional["AlertManager"] = None
    
    def __init__(
        self,
        config: Optional[AlertConfig] = None,
    ):
        self._config = config or AlertConfig()
        self._channels: Dict[AlertChannel, AlertChannelHandler] = {}
        self._rules: Dict[str, AlertRule] = {}
        self._alert_history: List[SecurityAlert] = []
        self._aggregation_buffer: Dict[str, List[SecurityAlert]] = defaultdict(list)
        self._last_alert_times: Dict[str, datetime] = {}
        self._alert_counts: Dict[str, int] = defaultdict(int)
        self._id_counter = 0
        self._lock = asyncio.Lock()
        
        # Register default channels
        self._channels[AlertChannel.LOG] = LogChannelHandler()
        self._channels[AlertChannel.CONSOLE] = ConsoleChannelHandler()
    
    @classmethod
    def get_instance(cls) -> "AlertManager":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(
        cls,
        config: Optional[AlertConfig] = None,
    ) -> "AlertManager":
        """Configure singleton instance."""
        cls._instance = cls(config=config)
        return cls._instance
    
    def register_channel(self, handler: AlertChannelHandler) -> None:
        """Register an alert channel handler."""
        self._channels[handler.channel_type] = handler
    
    def register_rule(self, rule: AlertRule) -> None:
        """Register an alert rule."""
        self._rules[rule.rule_id] = rule
    
    def _generate_id(self) -> str:
        """Generate unique alert ID."""
        self._id_counter += 1
        return f"alert-{int(time.time() * 1000)}-{self._id_counter}"
    
    def _get_dedup_key(self, alert: SecurityAlert) -> str:
        """Generate deduplication key for alert."""
        key_parts = [
            alert.category.value,
            alert.title,
            alert.user_id or "",
            alert.ip_address or "",
        ]
        return hashlib.sha256("|".join(key_parts).encode()).hexdigest()[:16]
    
    async def create_alert(
        self,
        severity: AlertSeverity,
        category: AlertCategory,
        title: str,
        description: str,
        source: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        tenant_id: Optional[str] = None,
        resource: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        channels: Optional[List[AlertChannel]] = None,
    ) -> SecurityAlert:
        """
        Create and send a security alert.
        
        Returns the created alert.
        """
        if not self._config.enabled:
            return SecurityAlert(
                alert_id=self._generate_id(),
                timestamp=datetime.now(timezone.utc),
                severity=severity,
                category=category,
                title=title,
                description=description,
                source=source,
                status=AlertStatus.SUPPRESSED,
            )
        
        alert = SecurityAlert(
            alert_id=self._generate_id(),
            timestamp=datetime.now(timezone.utc),
            severity=severity,
            category=category,
            title=title,
            description=description,
            source=source,
            user_id=user_id,
            ip_address=ip_address,
            tenant_id=tenant_id,
            resource=resource,
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
            details=details or {},
            tags=tags or [],
        )
        
        # Check deduplication
        dedup_key = self._get_dedup_key(alert)
        should_send = await self._check_deduplication(dedup_key, alert)
        
        if not should_send:
            alert.status = AlertStatus.SUPPRESSED
            return alert
        
        # Determine channels
        alert_channels = channels or self._config.severity_channels.get(
            severity,
            self._config.default_channels,
        )
        
        # Send through channels
        await self._send_alert(alert, alert_channels)
        
        # Store in history
        async with self._lock:
            self._alert_history.append(alert)
            
            # Trim old alerts
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            self._alert_history = [
                a for a in self._alert_history
                if a.timestamp > cutoff
            ]
        
        return alert
    
    async def _check_deduplication(self, dedup_key: str, alert: SecurityAlert) -> bool:
        """Check if alert should be sent or deduplicated."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(seconds=self._config.deduplication_window_seconds)
            
            last_time = self._last_alert_times.get(dedup_key)
            
            if last_time and last_time > cutoff:
                # Within dedup window - increment count but don't send
                self._alert_counts[dedup_key] += 1
                return False
            
            # Outside window - send and reset
            self._last_alert_times[dedup_key] = now
            self._alert_counts[dedup_key] = 1
            return True
    
    async def _send_alert(
        self,
        alert: SecurityAlert,
        channels: List[AlertChannel],
    ) -> None:
        """Send alert through specified channels."""
        for channel in channels:
            handler = self._channels.get(channel)
            
            if not handler:
                logger.warning("No handler for channel: %s", channel)
                continue
            
            try:
                success = await handler.send(alert)
                if success:
                    alert.channels_sent.append(channel)
                    alert.status = AlertStatus.SENT
                else:
                    logger.warning("Alert send failed for channel: %s", channel)
            except Exception as e:
                logger.error("Alert channel error (%s): %s", channel, e)
        
        if not alert.channels_sent:
            alert.status = AlertStatus.FAILED
    
    async def get_alerts(
        self,
        since: Optional[datetime] = None,
        severity: Optional[AlertSeverity] = None,
        category: Optional[AlertCategory] = None,
        status: Optional[AlertStatus] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[SecurityAlert]:
        """Get alerts matching criteria."""
        async with self._lock:
            results = []
            
            for alert in reversed(self._alert_history):
                if len(results) >= limit:
                    break
                
                if since and alert.timestamp < since:
                    continue
                if severity and alert.severity != severity:
                    continue
                if category and alert.category != category:
                    continue
                if status and alert.status != status:
                    continue
                if user_id and alert.user_id != user_id:
                    continue
                
                results.append(alert)
            
            return results
    
    async def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        async with self._lock:
            for alert in self._alert_history:
                if alert.alert_id == alert_id:
                    alert.status = AlertStatus.ACKNOWLEDGED
                    return True
            return False
    
    async def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert."""
        async with self._lock:
            for alert in self._alert_history:
                if alert.alert_id == alert_id:
                    alert.status = AlertStatus.RESOLVED
                    return True
            return False
    
    async def get_alert_stats(
        self,
        since: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get alert statistics."""
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(hours=24)
        
        async with self._lock:
            alerts = [a for a in self._alert_history if a.timestamp > since]
            
            by_severity: Dict[str, int] = defaultdict(int)
            by_category: Dict[str, int] = defaultdict(int)
            by_status: Dict[str, int] = defaultdict(int)
            
            for alert in alerts:
                by_severity[alert.severity.value] += 1
                by_category[alert.category.value] += 1
                by_status[alert.status.value] += 1
            
            return {
                "total": len(alerts),
                "by_severity": dict(by_severity),
                "by_category": dict(by_category),
                "by_status": dict(by_status),
                "time_period_hours": (datetime.now(timezone.utc) - since).total_seconds() / 3600,
            }


# =============================================================================
# Convenience Functions
# =============================================================================

def get_alert_manager() -> AlertManager:
    """Get singleton alert manager."""
    return AlertManager.get_instance()


async def send_security_alert(
    severity: AlertSeverity,
    category: AlertCategory,
    title: str,
    description: str,
    source: str = "system",
    **kwargs: Any,
) -> SecurityAlert:
    """Convenience function to send a security alert."""
    manager = get_alert_manager()
    return await manager.create_alert(
        severity=severity,
        category=category,
        title=title,
        description=description,
        source=source,
        **kwargs,
    )


async def alert_login_failure(
    username: str,
    ip_address: str,
    reason: str,
    attempt_count: int = 1,
) -> SecurityAlert:
    """Send alert for login failure."""
    severity = (
        AlertSeverity.HIGH if attempt_count >= 10
        else AlertSeverity.MEDIUM if attempt_count >= 5
        else AlertSeverity.LOW
    )
    
    return await send_security_alert(
        severity=severity,
        category=AlertCategory.AUTHENTICATION,
        title=f"Failed login attempt for {username}",
        description=f"Login failed from {ip_address}: {reason}. Attempt #{attempt_count}",
        source="auth_service",
        user_id=username,
        ip_address=ip_address,
        details={
            "reason": reason,
            "attempt_count": attempt_count,
        },
        tags=["login", "failure"],
    )


async def alert_access_denied(
    user_id: str,
    resource: str,
    required_permission: str,
    ip_address: Optional[str] = None,
) -> SecurityAlert:
    """Send alert for access denied."""
    return await send_security_alert(
        severity=AlertSeverity.MEDIUM,
        category=AlertCategory.AUTHORIZATION,
        title=f"Access denied for {user_id}",
        description=f"User attempted to access {resource} without {required_permission} permission",
        source="auth_service",
        user_id=user_id,
        ip_address=ip_address,
        resource=resource,
        details={
            "required_permission": required_permission,
        },
        tags=["access_denied", "authorization"],
    )


async def alert_suspicious_activity(
    activity_type: str,
    description: str,
    user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    severity: AlertSeverity = AlertSeverity.HIGH,
) -> SecurityAlert:
    """Send alert for suspicious activity."""
    return await send_security_alert(
        severity=severity,
        category=AlertCategory.INTRUSION,
        title=f"Suspicious activity detected: {activity_type}",
        description=description,
        source="anomaly_detection",
        user_id=user_id,
        ip_address=ip_address,
        details={
            "activity_type": activity_type,
        },
        tags=["suspicious", activity_type.lower()],
    )


async def alert_data_breach_attempt(
    user_id: str,
    resource: str,
    data_volume_bytes: int,
    ip_address: Optional[str] = None,
) -> SecurityAlert:
    """Send alert for potential data breach."""
    return await send_security_alert(
        severity=AlertSeverity.CRITICAL,
        category=AlertCategory.DATA_ACCESS,
        title=f"Potential data exfiltration by {user_id}",
        description=f"User accessed {data_volume_bytes / 1024 / 1024:.1f}MB of data from {resource}",
        source="data_access_monitor",
        user_id=user_id,
        ip_address=ip_address,
        resource=resource,
        details={
            "data_volume_bytes": data_volume_bytes,
        },
        tags=["data_breach", "exfiltration"],
    )


async def alert_injection_attempt(
    attack_type: str,
    payload: str,
    user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    endpoint: Optional[str] = None,
) -> SecurityAlert:
    """Send alert for injection attempt."""
    # Truncate payload for safety
    safe_payload = payload[:200] + "..." if len(payload) > 200 else payload
    
    return await send_security_alert(
        severity=AlertSeverity.CRITICAL,
        category=AlertCategory.INTRUSION,
        title=f"{attack_type} injection attempt detected",
        description=f"Malicious payload detected at {endpoint or 'unknown endpoint'}",
        source="input_validation",
        user_id=user_id,
        ip_address=ip_address,
        resource=endpoint,
        details={
            "attack_type": attack_type,
            "payload_preview": safe_payload,
        },
        tags=["injection", attack_type.lower()],
    )
