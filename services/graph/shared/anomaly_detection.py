"""
SEC-018: Anomaly Detection.

Comprehensive anomaly detection for security monitoring:
- Behavioral anomaly detection
- Time-based pattern analysis
- Resource access anomalies
- Request pattern anomalies
- Machine learning-ready feature extraction
"""

import asyncio
import hashlib
import logging
import math
import statistics
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

class AnomalyType(str, Enum):
    """Types of anomalies."""
    # Behavioral
    UNUSUAL_TIME = "unusual_time"
    UNUSUAL_LOCATION = "unusual_location"
    UNUSUAL_DEVICE = "unusual_device"
    UNUSUAL_FREQUENCY = "unusual_frequency"
    
    # Access patterns
    UNUSUAL_RESOURCE_ACCESS = "unusual_resource_access"
    EXCESSIVE_DATA_ACCESS = "excessive_data_access"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    
    # Request patterns
    UNUSUAL_API_PATTERN = "unusual_api_pattern"
    REQUEST_VELOCITY = "request_velocity"
    UNUSUAL_PAYLOAD_SIZE = "unusual_payload_size"
    
    # Session
    SESSION_ANOMALY = "session_anomaly"
    CONCURRENT_SESSIONS = "concurrent_sessions"
    
    # Data
    DATA_EXFILTRATION = "data_exfiltration"
    BULK_OPERATION = "bulk_operation"


class AnomalySeverity(str, Enum):
    """Severity of detected anomaly."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DetectionStatus(str, Enum):
    """Status of anomaly detection."""
    DETECTED = "detected"
    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    RESOLVED = "resolved"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DetectedAnomaly:
    """A detected anomaly."""
    anomaly_id: str
    timestamp: datetime
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    confidence: float  # 0.0 to 1.0
    description: str
    user_id: Optional[str] = None
    ip_address: Optional[str] = None
    session_id: Optional[str] = None
    tenant_id: Optional[str] = None
    resource: Optional[str] = None
    baseline_value: Optional[float] = None
    observed_value: Optional[float] = None
    deviation_factor: Optional[float] = None
    status: DetectionStatus = DetectionStatus.DETECTED
    details: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "anomaly_id": self.anomaly_id,
            "timestamp": self.timestamp.isoformat(),
            "anomaly_type": self.anomaly_type.value,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "description": self.description,
            "status": self.status.value,
        }
        
        if self.user_id:
            result["user_id"] = self.user_id
        if self.ip_address:
            result["ip_address"] = self.ip_address
        if self.session_id:
            result["session_id"] = self.session_id
        if self.tenant_id:
            result["tenant_id"] = self.tenant_id
        if self.resource:
            result["resource"] = self.resource
        if self.baseline_value is not None:
            result["baseline_value"] = self.baseline_value
        if self.observed_value is not None:
            result["observed_value"] = self.observed_value
        if self.deviation_factor is not None:
            result["deviation_factor"] = self.deviation_factor
        if self.details:
            result["details"] = self.details
        if self.tags:
            result["tags"] = self.tags
            
        return result


@dataclass
class UserBehaviorProfile:
    """Baseline profile of user behavior."""
    user_id: str
    # Time patterns
    typical_hours: List[int] = field(default_factory=list)  # 0-23
    typical_days: List[int] = field(default_factory=list)  # 0-6 (Mon-Sun)
    
    # Location patterns
    known_ips: Set[str] = field(default_factory=set)
    known_countries: Set[str] = field(default_factory=set)
    
    # Device patterns
    known_devices: Set[str] = field(default_factory=set)
    known_user_agents: Set[str] = field(default_factory=set)
    
    # Activity patterns
    avg_requests_per_day: float = 0.0
    avg_requests_per_hour: float = 0.0
    std_dev_requests: float = 0.0
    
    # Resource access
    typically_accessed_resources: Set[str] = field(default_factory=set)
    avg_data_volume_per_day: float = 0.0
    
    # Session patterns
    avg_session_duration_seconds: float = 0.0
    max_concurrent_sessions: int = 1
    
    # Metadata
    profile_created: Optional[datetime] = None
    profile_updated: Optional[datetime] = None
    total_events_analyzed: int = 0


@dataclass
class AnomalyEvent:
    """Event to analyze for anomalies."""
    event_id: str
    timestamp: datetime
    user_id: str
    event_type: str
    ip_address: Optional[str] = None
    country_code: Optional[str] = None
    device_fingerprint: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    tenant_id: Optional[str] = None
    resource: Optional[str] = None
    data_volume_bytes: int = 0
    endpoint: Optional[str] = None
    http_method: Optional[str] = None
    response_status: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class AnomalyDetectionConfig:
    """Configuration for anomaly detection."""
    # Time anomaly thresholds
    unusual_hour_threshold: float = 2.0  # Standard deviations
    
    # Location anomaly settings
    flag_new_ip: bool = True
    flag_new_country: bool = True
    
    # Device anomaly settings
    flag_new_device: bool = True
    
    # Frequency thresholds
    request_rate_threshold_multiplier: float = 3.0  # 3x normal rate
    min_baseline_events: int = 10  # Minimum events to establish baseline
    
    # Data access thresholds
    data_volume_threshold_multiplier: float = 5.0  # 5x normal volume
    bulk_operation_threshold: int = 100  # More than N items
    
    # Session thresholds
    max_concurrent_sessions: int = 3
    unusual_session_duration_multiplier: float = 5.0
    
    # Confidence thresholds
    min_confidence_to_report: float = 0.5
    high_confidence_threshold: float = 0.8
    
    # Profile settings
    profile_window_days: int = 30
    profile_update_frequency_hours: int = 24


# =============================================================================
# Statistical Helpers
# =============================================================================

class StatisticalAnalyzer:
    """Statistical analysis utilities."""
    
    @staticmethod
    def calculate_z_score(value: float, mean: float, std_dev: float) -> float:
        """Calculate z-score (standard deviations from mean)."""
        if std_dev == 0:
            return 0.0 if value == mean else float('inf')
        return (value - mean) / std_dev
    
    @staticmethod
    def is_outlier(
        value: float,
        data: List[float],
        threshold_std: float = 2.0,
    ) -> Tuple[bool, float]:
        """
        Check if value is an outlier.
        
        Returns (is_outlier, z_score).
        """
        if len(data) < 2:
            return False, 0.0
        
        mean = statistics.mean(data)
        std_dev = statistics.stdev(data)
        
        z_score = StatisticalAnalyzer.calculate_z_score(value, mean, std_dev)
        
        return abs(z_score) > threshold_std, z_score
    
    @staticmethod
    def calculate_iqr_bounds(data: List[float]) -> Tuple[float, float]:
        """
        Calculate IQR bounds for outlier detection.
        
        Returns (lower_bound, upper_bound).
        """
        if len(data) < 4:
            return min(data) if data else 0.0, max(data) if data else 0.0
        
        sorted_data = sorted(data)
        n = len(sorted_data)
        
        q1_idx = n // 4
        q3_idx = (3 * n) // 4
        
        q1 = sorted_data[q1_idx]
        q3 = sorted_data[q3_idx]
        iqr = q3 - q1
        
        return q1 - 1.5 * iqr, q3 + 1.5 * iqr
    
    @staticmethod
    def exponential_moving_average(
        data: List[float],
        alpha: float = 0.3,
    ) -> float:
        """Calculate exponential moving average."""
        if not data:
            return 0.0
        
        ema = data[0]
        for value in data[1:]:
            ema = alpha * value + (1 - alpha) * ema
        
        return ema


# =============================================================================
# Profile Manager
# =============================================================================

class UserProfileManager:
    """Manages user behavior profiles."""
    
    def __init__(self, config: Optional[AnomalyDetectionConfig] = None):
        self._config = config or AnomalyDetectionConfig()
        self._profiles: Dict[str, UserBehaviorProfile] = {}
        self._event_history: Dict[str, List[AnomalyEvent]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def get_profile(self, user_id: str) -> Optional[UserBehaviorProfile]:
        """Get user behavior profile."""
        async with self._lock:
            return self._profiles.get(user_id)
    
    async def record_event(self, event: AnomalyEvent) -> None:
        """Record event for profile building."""
        async with self._lock:
            # Store event
            self._event_history[event.user_id].append(event)
            
            # Trim old events
            cutoff = datetime.now(timezone.utc) - timedelta(
                days=self._config.profile_window_days
            )
            self._event_history[event.user_id] = [
                e for e in self._event_history[event.user_id]
                if e.timestamp > cutoff
            ]
    
    async def update_profile(self, user_id: str) -> UserBehaviorProfile:
        """Update or create user profile from event history."""
        async with self._lock:
            events = self._event_history.get(user_id, [])
            
            if user_id not in self._profiles:
                self._profiles[user_id] = UserBehaviorProfile(
                    user_id=user_id,
                    profile_created=datetime.now(timezone.utc),
                )
            
            profile = self._profiles[user_id]
            
            if not events:
                return profile
            
            # Update time patterns
            hours = [e.timestamp.hour for e in events]
            days = [e.timestamp.weekday() for e in events]
            profile.typical_hours = list(set(hours))
            profile.typical_days = list(set(days))
            
            # Update location patterns
            profile.known_ips = {e.ip_address for e in events if e.ip_address}
            profile.known_countries = {e.country_code for e in events if e.country_code}
            
            # Update device patterns
            profile.known_devices = {e.device_fingerprint for e in events if e.device_fingerprint}
            profile.known_user_agents = {e.user_agent for e in events if e.user_agent}
            
            # Calculate request rates
            if len(events) >= 2:
                time_span = (events[-1].timestamp - events[0].timestamp).total_seconds()
                if time_span > 0:
                    days_span = time_span / 86400
                    profile.avg_requests_per_day = len(events) / max(days_span, 1)
                    profile.avg_requests_per_hour = len(events) / max(time_span / 3600, 1)
                
                # Calculate request rate std dev (per hour)
                hourly_counts: Dict[str, int] = defaultdict(int)
                for e in events:
                    hour_key = e.timestamp.strftime("%Y-%m-%d-%H")
                    hourly_counts[hour_key] += 1
                
                if len(hourly_counts) >= 2:
                    profile.std_dev_requests = statistics.stdev(hourly_counts.values())
            
            # Update resource access patterns
            profile.typically_accessed_resources = {e.resource for e in events if e.resource}
            
            # Calculate data volume
            total_volume = sum(e.data_volume_bytes for e in events)
            time_span_days = (
                (events[-1].timestamp - events[0].timestamp).total_seconds() / 86400
            ) if len(events) >= 2 else 1
            profile.avg_data_volume_per_day = total_volume / max(time_span_days, 1)
            
            # Update session patterns
            sessions = {e.session_id for e in events if e.session_id}
            profile.max_concurrent_sessions = max(profile.max_concurrent_sessions, len(sessions))
            
            # Update metadata
            profile.profile_updated = datetime.now(timezone.utc)
            profile.total_events_analyzed = len(events)
            
            return profile
    
    async def has_sufficient_baseline(self, user_id: str) -> bool:
        """Check if user has sufficient baseline data."""
        async with self._lock:
            events = self._event_history.get(user_id, [])
            return len(events) >= self._config.min_baseline_events


# =============================================================================
# Anomaly Detectors
# =============================================================================

class BaseAnomalyDetector(ABC):
    """Base class for anomaly detectors."""
    
    @abstractmethod
    async def detect(
        self,
        event: AnomalyEvent,
        profile: Optional[UserBehaviorProfile],
    ) -> List[DetectedAnomaly]:
        """Detect anomalies in event."""
        pass
    
    def _generate_id(self) -> str:
        """Generate unique anomaly ID."""
        return f"anomaly-{int(time.time() * 1000000)}"


class TimeAnomalyDetector(BaseAnomalyDetector):
    """Detects unusual access times."""
    
    def __init__(self, config: Optional[AnomalyDetectionConfig] = None):
        self._config = config or AnomalyDetectionConfig()
    
    async def detect(
        self,
        event: AnomalyEvent,
        profile: Optional[UserBehaviorProfile],
    ) -> List[DetectedAnomaly]:
        anomalies = []
        
        if not profile or not profile.typical_hours:
            return anomalies
        
        current_hour = event.timestamp.hour
        current_day = event.timestamp.weekday()
        
        # Check unusual hour
        if current_hour not in profile.typical_hours:
            # Calculate confidence based on how unusual
            typical_hours_set = set(profile.typical_hours)
            
            # Find minimum distance to any typical hour
            min_distance = 24
            for typical_hour in typical_hours_set:
                distance = min(
                    abs(current_hour - typical_hour),
                    24 - abs(current_hour - typical_hour),
                )
                min_distance = min(min_distance, distance)
            
            # Higher distance = higher confidence
            confidence = min(0.95, 0.5 + (min_distance * 0.05))
            
            anomalies.append(DetectedAnomaly(
                anomaly_id=self._generate_id(),
                timestamp=datetime.now(timezone.utc),
                anomaly_type=AnomalyType.UNUSUAL_TIME,
                severity=AnomalySeverity.MEDIUM if min_distance > 4 else AnomalySeverity.LOW,
                confidence=confidence,
                description=f"Access at unusual hour {current_hour}:00",
                user_id=event.user_id,
                ip_address=event.ip_address,
                session_id=event.session_id,
                details={
                    "current_hour": current_hour,
                    "typical_hours": list(profile.typical_hours),
                    "hour_distance": min_distance,
                },
                tags=["time", "behavioral"],
            ))
        
        # Check unusual day
        if profile.typical_days and current_day not in profile.typical_days:
            anomalies.append(DetectedAnomaly(
                anomaly_id=self._generate_id(),
                timestamp=datetime.now(timezone.utc),
                anomaly_type=AnomalyType.UNUSUAL_TIME,
                severity=AnomalySeverity.LOW,
                confidence=0.6,
                description=f"Access on unusual day (weekday {current_day})",
                user_id=event.user_id,
                ip_address=event.ip_address,
                session_id=event.session_id,
                details={
                    "current_day": current_day,
                    "typical_days": list(profile.typical_days),
                },
                tags=["time", "behavioral"],
            ))
        
        return anomalies


class LocationAnomalyDetector(BaseAnomalyDetector):
    """Detects unusual access locations."""
    
    def __init__(self, config: Optional[AnomalyDetectionConfig] = None):
        self._config = config or AnomalyDetectionConfig()
    
    async def detect(
        self,
        event: AnomalyEvent,
        profile: Optional[UserBehaviorProfile],
    ) -> List[DetectedAnomaly]:
        anomalies = []
        
        if not profile:
            return anomalies
        
        # Check new IP
        if (
            self._config.flag_new_ip
            and event.ip_address
            and profile.known_ips
            and event.ip_address not in profile.known_ips
        ):
            anomalies.append(DetectedAnomaly(
                anomaly_id=self._generate_id(),
                timestamp=datetime.now(timezone.utc),
                anomaly_type=AnomalyType.UNUSUAL_LOCATION,
                severity=AnomalySeverity.MEDIUM,
                confidence=0.7,
                description=f"Access from new IP address: {event.ip_address}",
                user_id=event.user_id,
                ip_address=event.ip_address,
                session_id=event.session_id,
                details={
                    "new_ip": event.ip_address,
                    "known_ips_count": len(profile.known_ips),
                },
                tags=["location", "behavioral"],
            ))
        
        # Check new country
        if (
            self._config.flag_new_country
            and event.country_code
            and profile.known_countries
            and event.country_code not in profile.known_countries
        ):
            anomalies.append(DetectedAnomaly(
                anomaly_id=self._generate_id(),
                timestamp=datetime.now(timezone.utc),
                anomaly_type=AnomalyType.UNUSUAL_LOCATION,
                severity=AnomalySeverity.HIGH,
                confidence=0.85,
                description=f"Access from new country: {event.country_code}",
                user_id=event.user_id,
                ip_address=event.ip_address,
                session_id=event.session_id,
                details={
                    "new_country": event.country_code,
                    "known_countries": list(profile.known_countries),
                },
                tags=["location", "behavioral", "geographic"],
            ))
        
        return anomalies


class DeviceAnomalyDetector(BaseAnomalyDetector):
    """Detects unusual device access."""
    
    def __init__(self, config: Optional[AnomalyDetectionConfig] = None):
        self._config = config or AnomalyDetectionConfig()
    
    async def detect(
        self,
        event: AnomalyEvent,
        profile: Optional[UserBehaviorProfile],
    ) -> List[DetectedAnomaly]:
        anomalies = []
        
        if not profile or not self._config.flag_new_device:
            return anomalies
        
        # Check new device fingerprint
        if (
            event.device_fingerprint
            and profile.known_devices
            and event.device_fingerprint not in profile.known_devices
        ):
            anomalies.append(DetectedAnomaly(
                anomaly_id=self._generate_id(),
                timestamp=datetime.now(timezone.utc),
                anomaly_type=AnomalyType.UNUSUAL_DEVICE,
                severity=AnomalySeverity.MEDIUM,
                confidence=0.75,
                description="Access from new device",
                user_id=event.user_id,
                ip_address=event.ip_address,
                session_id=event.session_id,
                details={
                    "known_devices_count": len(profile.known_devices),
                },
                tags=["device", "behavioral"],
            ))
        
        # Check new user agent
        if (
            event.user_agent
            and profile.known_user_agents
            and event.user_agent not in profile.known_user_agents
        ):
            anomalies.append(DetectedAnomaly(
                anomaly_id=self._generate_id(),
                timestamp=datetime.now(timezone.utc),
                anomaly_type=AnomalyType.UNUSUAL_DEVICE,
                severity=AnomalySeverity.LOW,
                confidence=0.6,
                description="Access from new user agent",
                user_id=event.user_id,
                ip_address=event.ip_address,
                session_id=event.session_id,
                details={
                    "user_agent": event.user_agent,
                    "known_user_agents_count": len(profile.known_user_agents),
                },
                tags=["device", "behavioral"],
            ))
        
        return anomalies


class FrequencyAnomalyDetector(BaseAnomalyDetector):
    """Detects unusual request frequency."""
    
    def __init__(self, config: Optional[AnomalyDetectionConfig] = None):
        self._config = config or AnomalyDetectionConfig()
        self._request_counts: Dict[str, List[Tuple[datetime, int]]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def record_request(self, user_id: str) -> None:
        """Record a request for rate tracking."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            hour_key = now.replace(minute=0, second=0, microsecond=0)
            
            # Find or create hour entry
            history = self._request_counts[user_id]
            
            if history and history[-1][0] == hour_key:
                history[-1] = (hour_key, history[-1][1] + 1)
            else:
                history.append((hour_key, 1))
            
            # Keep only last 24 hours
            cutoff = now - timedelta(hours=24)
            self._request_counts[user_id] = [
                (ts, count) for ts, count in history
                if ts > cutoff
            ]
    
    async def detect(
        self,
        event: AnomalyEvent,
        profile: Optional[UserBehaviorProfile],
    ) -> List[DetectedAnomaly]:
        anomalies = []
        
        if not profile or profile.avg_requests_per_hour == 0:
            return anomalies
        
        # Get current hour request count
        async with self._lock:
            history = self._request_counts.get(event.user_id, [])
            
            if not history:
                return anomalies
            
            current_rate = history[-1][1] if history else 0
        
        # Check if rate exceeds threshold
        threshold = (
            profile.avg_requests_per_hour 
            * self._config.request_rate_threshold_multiplier
        )
        
        if current_rate > threshold:
            deviation = current_rate / profile.avg_requests_per_hour
            
            anomalies.append(DetectedAnomaly(
                anomaly_id=self._generate_id(),
                timestamp=datetime.now(timezone.utc),
                anomaly_type=AnomalyType.REQUEST_VELOCITY,
                severity=(
                    AnomalySeverity.HIGH if deviation > 10
                    else AnomalySeverity.MEDIUM if deviation > 5
                    else AnomalySeverity.LOW
                ),
                confidence=min(0.95, 0.5 + (deviation * 0.05)),
                description=f"Request rate {current_rate}/hour exceeds normal ({profile.avg_requests_per_hour:.1f}/hour)",
                user_id=event.user_id,
                ip_address=event.ip_address,
                session_id=event.session_id,
                baseline_value=profile.avg_requests_per_hour,
                observed_value=float(current_rate),
                deviation_factor=deviation,
                details={
                    "threshold_multiplier": self._config.request_rate_threshold_multiplier,
                },
                tags=["frequency", "rate", "velocity"],
            ))
        
        return anomalies


class DataAccessAnomalyDetector(BaseAnomalyDetector):
    """Detects unusual data access patterns."""
    
    def __init__(self, config: Optional[AnomalyDetectionConfig] = None):
        self._config = config or AnomalyDetectionConfig()
        self._daily_volumes: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def record_access(self, user_id: str, volume_bytes: int) -> None:
        """Record data access volume."""
        async with self._lock:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            history = self._daily_volumes[user_id]
            
            if history and history[-1][0] == today:
                history[-1] = (today, history[-1][1] + volume_bytes)
            else:
                history.append((today, volume_bytes))
            
            # Keep only last 30 days
            self._daily_volumes[user_id] = history[-30:]
    
    async def detect(
        self,
        event: AnomalyEvent,
        profile: Optional[UserBehaviorProfile],
    ) -> List[DetectedAnomaly]:
        anomalies = []
        
        if not profile or profile.avg_data_volume_per_day == 0:
            return anomalies
        
        # Get today's volume
        async with self._lock:
            history = self._daily_volumes.get(event.user_id, [])
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            
            today_volume = 0
            for date_str, volume in history:
                if date_str == today:
                    today_volume = volume
                    break
        
        # Check if volume exceeds threshold
        threshold = (
            profile.avg_data_volume_per_day
            * self._config.data_volume_threshold_multiplier
        )
        
        if today_volume > threshold:
            deviation = today_volume / profile.avg_data_volume_per_day
            
            anomalies.append(DetectedAnomaly(
                anomaly_id=self._generate_id(),
                timestamp=datetime.now(timezone.utc),
                anomaly_type=AnomalyType.EXCESSIVE_DATA_ACCESS,
                severity=(
                    AnomalySeverity.CRITICAL if deviation > 20
                    else AnomalySeverity.HIGH if deviation > 10
                    else AnomalySeverity.MEDIUM
                ),
                confidence=min(0.95, 0.6 + (deviation * 0.02)),
                description=f"Data volume {today_volume / 1024 / 1024:.1f}MB exceeds normal ({profile.avg_data_volume_per_day / 1024 / 1024:.1f}MB/day)",
                user_id=event.user_id,
                ip_address=event.ip_address,
                session_id=event.session_id,
                baseline_value=profile.avg_data_volume_per_day,
                observed_value=float(today_volume),
                deviation_factor=deviation,
                details={
                    "threshold_multiplier": self._config.data_volume_threshold_multiplier,
                    "volume_bytes": today_volume,
                },
                tags=["data", "volume", "exfiltration_risk"],
            ))
        
        # Check for unusual resource access
        if (
            event.resource
            and profile.typically_accessed_resources
            and event.resource not in profile.typically_accessed_resources
        ):
            anomalies.append(DetectedAnomaly(
                anomaly_id=self._generate_id(),
                timestamp=datetime.now(timezone.utc),
                anomaly_type=AnomalyType.UNUSUAL_RESOURCE_ACCESS,
                severity=AnomalySeverity.MEDIUM,
                confidence=0.7,
                description=f"Access to unusual resource: {event.resource}",
                user_id=event.user_id,
                ip_address=event.ip_address,
                session_id=event.session_id,
                resource=event.resource,
                details={
                    "typical_resources_count": len(profile.typically_accessed_resources),
                },
                tags=["resource", "access"],
            ))
        
        return anomalies


# =============================================================================
# Anomaly Detection Engine
# =============================================================================

class AnomalyDetectionEngine:
    """
    Main anomaly detection engine.
    
    Coordinates multiple detectors and manages profiles.
    """
    
    _instance: Optional["AnomalyDetectionEngine"] = None
    
    def __init__(
        self,
        config: Optional[AnomalyDetectionConfig] = None,
    ):
        self._config = config or AnomalyDetectionConfig()
        self._profile_manager = UserProfileManager(config)
        
        # Initialize detectors
        self._detectors: List[BaseAnomalyDetector] = [
            TimeAnomalyDetector(config),
            LocationAnomalyDetector(config),
            DeviceAnomalyDetector(config),
            FrequencyAnomalyDetector(config),
            DataAccessAnomalyDetector(config),
        ]
        
        # Hooks
        self._detection_hooks: List[Callable[[DetectedAnomaly], None]] = []
        
        # Storage
        self._detected_anomalies: List[DetectedAnomaly] = []
        self._lock = asyncio.Lock()
    
    @classmethod
    def get_instance(cls) -> "AnomalyDetectionEngine":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(
        cls,
        config: Optional[AnomalyDetectionConfig] = None,
    ) -> "AnomalyDetectionEngine":
        """Configure singleton instance."""
        cls._instance = cls(config=config)
        return cls._instance
    
    def add_detector(self, detector: BaseAnomalyDetector) -> None:
        """Add custom detector."""
        self._detectors.append(detector)
    
    def add_detection_hook(self, hook: Callable[[DetectedAnomaly], None]) -> None:
        """Add hook for detected anomalies."""
        self._detection_hooks.append(hook)
    
    async def analyze_event(
        self,
        event: AnomalyEvent,
        update_profile: bool = True,
    ) -> List[DetectedAnomaly]:
        """
        Analyze event for anomalies.
        
        Args:
            event: Event to analyze
            update_profile: Whether to update user profile
            
        Returns:
            List of detected anomalies
        """
        # Get user profile
        profile = await self._profile_manager.get_profile(event.user_id)
        has_baseline = await self._profile_manager.has_sufficient_baseline(event.user_id)
        
        # Skip detection if no baseline (but still record event)
        if not has_baseline:
            # Record event for profile building
            await self._profile_manager.record_event(event)
            if update_profile:
                await self._profile_manager.update_profile(event.user_id)
            return []
        
        # Run all detectors BEFORE updating profile
        # (so the new event isn't part of the baseline yet)
        all_anomalies: List[DetectedAnomaly] = []
        
        for detector in self._detectors:
            try:
                anomalies = await detector.detect(event, profile)
                all_anomalies.extend(anomalies)
            except Exception as e:
                logger.error("Detector error: %s", e)
        
        # NOW record event and update profile (after detection)
        await self._profile_manager.record_event(event)
        if update_profile:
            await self._profile_manager.update_profile(event.user_id)
        
        # Filter by confidence
        filtered = [
            a for a in all_anomalies
            if a.confidence >= self._config.min_confidence_to_report
        ]
        
        # Store and notify
        async with self._lock:
            self._detected_anomalies.extend(filtered)
            
            # Trim old anomalies
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            self._detected_anomalies = [
                a for a in self._detected_anomalies
                if a.timestamp > cutoff
            ]
        
        # Call hooks
        for anomaly in filtered:
            for hook in self._detection_hooks:
                try:
                    hook(anomaly)
                except Exception as e:
                    logger.error("Hook error: %s", e)
        
        return filtered
    
    async def get_user_profile(self, user_id: str) -> Optional[UserBehaviorProfile]:
        """Get user behavior profile."""
        return await self._profile_manager.get_profile(user_id)
    
    async def get_recent_anomalies(
        self,
        user_id: Optional[str] = None,
        anomaly_type: Optional[AnomalyType] = None,
        min_severity: Optional[AnomalySeverity] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[DetectedAnomaly]:
        """Get recent detected anomalies."""
        severity_order = {
            AnomalySeverity.LOW: 0,
            AnomalySeverity.MEDIUM: 1,
            AnomalySeverity.HIGH: 2,
            AnomalySeverity.CRITICAL: 3,
        }
        
        async with self._lock:
            results = []
            
            for anomaly in reversed(self._detected_anomalies):
                if len(results) >= limit:
                    break
                
                if user_id and anomaly.user_id != user_id:
                    continue
                if anomaly_type and anomaly.anomaly_type != anomaly_type:
                    continue
                if since and anomaly.timestamp < since:
                    continue
                if (
                    min_severity
                    and severity_order.get(anomaly.severity, 0)
                    < severity_order.get(min_severity, 0)
                ):
                    continue
                
                results.append(anomaly)
            
            return results
    
    async def update_anomaly_status(
        self,
        anomaly_id: str,
        status: DetectionStatus,
    ) -> bool:
        """Update anomaly status."""
        async with self._lock:
            for anomaly in self._detected_anomalies:
                if anomaly.anomaly_id == anomaly_id:
                    anomaly.status = status
                    return True
            return False


# =============================================================================
# Helper Functions
# =============================================================================

def get_anomaly_engine() -> AnomalyDetectionEngine:
    """Get singleton anomaly detection engine."""
    return AnomalyDetectionEngine.get_instance()


async def detect_anomalies(
    user_id: str,
    event_type: str,
    ip_address: Optional[str] = None,
    country_code: Optional[str] = None,
    device_fingerprint: Optional[str] = None,
    user_agent: Optional[str] = None,
    resource: Optional[str] = None,
    data_volume_bytes: int = 0,
    **kwargs: Any,
) -> List[DetectedAnomaly]:
    """
    Convenience function to detect anomalies.
    
    Creates an AnomalyEvent and runs detection.
    """
    engine = get_anomaly_engine()
    
    event = AnomalyEvent(
        event_id=f"event-{int(time.time() * 1000000)}",
        timestamp=datetime.now(timezone.utc),
        user_id=user_id,
        event_type=event_type,
        ip_address=ip_address,
        country_code=country_code,
        device_fingerprint=device_fingerprint,
        user_agent=user_agent,
        resource=resource,
        data_volume_bytes=data_volume_bytes,
        metadata=kwargs,
    )
    
    return await engine.analyze_event(event)
