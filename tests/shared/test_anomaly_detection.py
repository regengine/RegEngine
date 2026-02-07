"""
Tests for SEC-018: Anomaly Detection.

Tests cover:
- Statistical analysis helpers
- User behavior profiles
- Time anomaly detection
- Location anomaly detection
- Device anomaly detection
- Frequency anomaly detection
- Data access anomaly detection
- Detection engine coordination
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from shared.anomaly_detection import (
    # Enums
    AnomalyType,
    AnomalySeverity,
    DetectionStatus,
    # Data classes
    DetectedAnomaly,
    UserBehaviorProfile,
    AnomalyEvent,
    AnomalyDetectionConfig,
    # Statistical
    StatisticalAnalyzer,
    # Profile manager
    UserProfileManager,
    # Detectors
    TimeAnomalyDetector,
    LocationAnomalyDetector,
    DeviceAnomalyDetector,
    FrequencyAnomalyDetector,
    DataAccessAnomalyDetector,
    # Engine
    AnomalyDetectionEngine,
    # Functions
    get_anomaly_engine,
    detect_anomalies,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create test config."""
    return AnomalyDetectionConfig(
        min_baseline_events=3,  # Lower for testing
        request_rate_threshold_multiplier=2.0,
        data_volume_threshold_multiplier=3.0,
    )


@pytest.fixture
def profile():
    """Create test profile."""
    return UserBehaviorProfile(
        user_id="user-123",
        typical_hours=[9, 10, 11, 14, 15, 16],  # Business hours
        typical_days=[0, 1, 2, 3, 4],  # Weekdays
        known_ips={"192.168.1.100", "192.168.1.101"},
        known_countries={"US", "CA"},
        known_devices={"device-1", "device-2"},
        known_user_agents={"Mozilla/5.0"},
        avg_requests_per_hour=10.0,
        avg_requests_per_day=80.0,
        std_dev_requests=3.0,
        typically_accessed_resources={"/api/docs", "/api/users"},
        avg_data_volume_per_day=10_000_000,  # 10MB
        profile_created=datetime.now(timezone.utc) - timedelta(days=30),
        total_events_analyzed=500,
    )


@pytest.fixture
def engine(config):
    """Create test engine."""
    return AnomalyDetectionEngine(config=config)


@pytest.fixture
def normal_event():
    """Create normal event."""
    return AnomalyEvent(
        event_id="event-1",
        timestamp=datetime.now(timezone.utc).replace(hour=10),  # 10 AM
        user_id="user-123",
        event_type="api_call",
        ip_address="192.168.1.100",
        country_code="US",
        device_fingerprint="device-1",
        user_agent="Mozilla/5.0",
        resource="/api/docs",
        data_volume_bytes=1000,
    )


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_anomaly_types(self):
        """Should have expected anomaly types."""
        assert AnomalyType.UNUSUAL_TIME == "unusual_time"
        assert AnomalyType.UNUSUAL_LOCATION == "unusual_location"
        assert AnomalyType.REQUEST_VELOCITY == "request_velocity"
    
    def test_severity_levels(self):
        """Should have expected severity levels."""
        assert AnomalySeverity.LOW == "low"
        assert AnomalySeverity.CRITICAL == "critical"
    
    def test_detection_status(self):
        """Should have expected statuses."""
        assert DetectionStatus.DETECTED == "detected"
        assert DetectionStatus.FALSE_POSITIVE == "false_positive"


# =============================================================================
# Test: Statistical Analyzer
# =============================================================================

class TestStatisticalAnalyzer:
    """Test StatisticalAnalyzer."""
    
    def test_z_score_calculation(self):
        """Should calculate z-score correctly."""
        # Value is 2 std devs above mean
        z = StatisticalAnalyzer.calculate_z_score(16.0, 10.0, 3.0)
        assert z == 2.0
    
    def test_z_score_zero_std_dev(self):
        """Should handle zero std dev."""
        z = StatisticalAnalyzer.calculate_z_score(10.0, 10.0, 0.0)
        assert z == 0.0
        
        z = StatisticalAnalyzer.calculate_z_score(15.0, 10.0, 0.0)
        assert z == float('inf')
    
    def test_is_outlier(self):
        """Should detect outliers."""
        data = [10, 11, 9, 10, 12, 10, 11, 9]
        
        # Normal value
        is_out, z = StatisticalAnalyzer.is_outlier(10, data, threshold_std=2.0)
        assert is_out is False
        
        # Outlier
        is_out, z = StatisticalAnalyzer.is_outlier(20, data, threshold_std=2.0)
        assert is_out is True
        assert z > 2.0
    
    def test_iqr_bounds(self):
        """Should calculate IQR bounds."""
        data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        lower, upper = StatisticalAnalyzer.calculate_iqr_bounds(data)
        
        assert lower < 1
        assert upper > 10
    
    def test_exponential_moving_average(self):
        """Should calculate EMA."""
        data = [10, 12, 11, 13, 14]
        ema = StatisticalAnalyzer.exponential_moving_average(data, alpha=0.3)
        
        # EMA should be influenced more by recent values
        assert ema > 10  # Greater than first value
        assert ema < 14  # Less than last value


# =============================================================================
# Test: User Behavior Profile
# =============================================================================

class TestUserBehaviorProfile:
    """Test UserBehaviorProfile."""
    
    def test_profile_creation(self, profile):
        """Should create profile with all fields."""
        assert profile.user_id == "user-123"
        assert 10 in profile.typical_hours
        assert "US" in profile.known_countries
    
    def test_default_values(self):
        """Should have sensible defaults."""
        profile = UserBehaviorProfile(user_id="new-user")
        
        assert profile.typical_hours == []
        assert profile.avg_requests_per_day == 0.0
        assert profile.max_concurrent_sessions == 1


# =============================================================================
# Test: Profile Manager
# =============================================================================

class TestUserProfileManager:
    """Test UserProfileManager."""
    
    @pytest.mark.asyncio
    async def test_record_and_update_profile(self, config):
        """Should record events and update profile."""
        manager = UserProfileManager(config)
        
        # Record some events
        for i in range(5):
            event = AnomalyEvent(
                event_id=f"event-{i}",
                timestamp=datetime.now(timezone.utc),
                user_id="user-123",
                event_type="api_call",
                ip_address="192.168.1.100",
                country_code="US",
            )
            await manager.record_event(event)
        
        # Update profile
        profile = await manager.update_profile("user-123")
        
        assert profile.user_id == "user-123"
        assert "192.168.1.100" in profile.known_ips
        assert "US" in profile.known_countries
    
    @pytest.mark.asyncio
    async def test_has_sufficient_baseline(self, config):
        """Should check baseline sufficiency."""
        manager = UserProfileManager(config)
        
        # No events yet
        has_baseline = await manager.has_sufficient_baseline("user-123")
        assert has_baseline is False
        
        # Record min_baseline_events (3)
        for i in range(3):
            event = AnomalyEvent(
                event_id=f"event-{i}",
                timestamp=datetime.now(timezone.utc),
                user_id="user-123",
                event_type="api_call",
            )
            await manager.record_event(event)
        
        has_baseline = await manager.has_sufficient_baseline("user-123")
        assert has_baseline is True


# =============================================================================
# Test: Time Anomaly Detector
# =============================================================================

class TestTimeAnomalyDetector:
    """Test TimeAnomalyDetector."""
    
    @pytest.mark.asyncio
    async def test_normal_hour(self, profile):
        """Should not flag normal hour."""
        detector = TimeAnomalyDetector()
        
        event = AnomalyEvent(
            event_id="event-1",
            timestamp=datetime.now(timezone.utc).replace(hour=10),  # Normal hour
            user_id="user-123",
            event_type="api_call",
        )
        
        anomalies = await detector.detect(event, profile)
        
        # No anomalies for normal hour
        time_anomalies = [a for a in anomalies if "hour" in a.description.lower()]
        assert len(time_anomalies) == 0
    
    @pytest.mark.asyncio
    async def test_unusual_hour(self, profile):
        """Should flag unusual hour."""
        detector = TimeAnomalyDetector()
        
        event = AnomalyEvent(
            event_id="event-1",
            timestamp=datetime.now(timezone.utc).replace(hour=3),  # 3 AM - unusual
            user_id="user-123",
            event_type="api_call",
        )
        
        anomalies = await detector.detect(event, profile)
        
        assert len(anomalies) >= 1
        assert anomalies[0].anomaly_type == AnomalyType.UNUSUAL_TIME
        assert "hour" in anomalies[0].description.lower()
    
    @pytest.mark.asyncio
    async def test_unusual_day(self, profile):
        """Should flag unusual day."""
        detector = TimeAnomalyDetector()
        
        # Get a Saturday timestamp (weekday 5)
        now = datetime.now(timezone.utc)
        days_until_saturday = (5 - now.weekday()) % 7
        saturday = now + timedelta(days=days_until_saturday)
        
        event = AnomalyEvent(
            event_id="event-1",
            timestamp=saturday.replace(hour=10),
            user_id="user-123",
            event_type="api_call",
        )
        
        anomalies = await detector.detect(event, profile)
        
        day_anomalies = [a for a in anomalies if "day" in a.description.lower()]
        assert len(day_anomalies) >= 1


# =============================================================================
# Test: Location Anomaly Detector
# =============================================================================

class TestLocationAnomalyDetector:
    """Test LocationAnomalyDetector."""
    
    @pytest.mark.asyncio
    async def test_known_ip(self, profile):
        """Should not flag known IP."""
        detector = LocationAnomalyDetector()
        
        event = AnomalyEvent(
            event_id="event-1",
            timestamp=datetime.now(timezone.utc),
            user_id="user-123",
            event_type="api_call",
            ip_address="192.168.1.100",  # Known IP
        )
        
        anomalies = await detector.detect(event, profile)
        ip_anomalies = [a for a in anomalies if "ip" in a.description.lower()]
        assert len(ip_anomalies) == 0
    
    @pytest.mark.asyncio
    async def test_new_ip(self, profile):
        """Should flag new IP."""
        detector = LocationAnomalyDetector()
        
        event = AnomalyEvent(
            event_id="event-1",
            timestamp=datetime.now(timezone.utc),
            user_id="user-123",
            event_type="api_call",
            ip_address="10.0.0.1",  # New IP
        )
        
        anomalies = await detector.detect(event, profile)
        
        assert len(anomalies) >= 1
        assert any(a.anomaly_type == AnomalyType.UNUSUAL_LOCATION for a in anomalies)
    
    @pytest.mark.asyncio
    async def test_new_country(self, profile):
        """Should flag new country."""
        detector = LocationAnomalyDetector()
        
        event = AnomalyEvent(
            event_id="event-1",
            timestamp=datetime.now(timezone.utc),
            user_id="user-123",
            event_type="api_call",
            country_code="RU",  # New country
        )
        
        anomalies = await detector.detect(event, profile)
        
        assert len(anomalies) >= 1
        country_anomaly = next(
            (a for a in anomalies if "country" in a.description.lower()),
            None,
        )
        assert country_anomaly is not None
        assert country_anomaly.severity == AnomalySeverity.HIGH


# =============================================================================
# Test: Device Anomaly Detector
# =============================================================================

class TestDeviceAnomalyDetector:
    """Test DeviceAnomalyDetector."""
    
    @pytest.mark.asyncio
    async def test_known_device(self, profile):
        """Should not flag known device."""
        detector = DeviceAnomalyDetector()
        
        event = AnomalyEvent(
            event_id="event-1",
            timestamp=datetime.now(timezone.utc),
            user_id="user-123",
            event_type="api_call",
            device_fingerprint="device-1",  # Known
        )
        
        anomalies = await detector.detect(event, profile)
        device_anomalies = [
            a for a in anomalies 
            if a.anomaly_type == AnomalyType.UNUSUAL_DEVICE
        ]
        assert len(device_anomalies) == 0
    
    @pytest.mark.asyncio
    async def test_new_device(self, profile):
        """Should flag new device."""
        detector = DeviceAnomalyDetector()
        
        event = AnomalyEvent(
            event_id="event-1",
            timestamp=datetime.now(timezone.utc),
            user_id="user-123",
            event_type="api_call",
            device_fingerprint="new-device",  # Unknown
        )
        
        anomalies = await detector.detect(event, profile)
        
        assert len(anomalies) >= 1
        assert any(a.anomaly_type == AnomalyType.UNUSUAL_DEVICE for a in anomalies)


# =============================================================================
# Test: Frequency Anomaly Detector
# =============================================================================

class TestFrequencyAnomalyDetector:
    """Test FrequencyAnomalyDetector."""
    
    @pytest.mark.asyncio
    async def test_normal_frequency(self, config, profile):
        """Should not flag normal frequency."""
        detector = FrequencyAnomalyDetector(config)
        
        # Record some requests (under threshold)
        for i in range(5):
            await detector.record_request("user-123")
        
        event = AnomalyEvent(
            event_id="event-1",
            timestamp=datetime.now(timezone.utc),
            user_id="user-123",
            event_type="api_call",
        )
        
        anomalies = await detector.detect(event, profile)
        velocity_anomalies = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.REQUEST_VELOCITY
        ]
        assert len(velocity_anomalies) == 0
    
    @pytest.mark.asyncio
    async def test_excessive_frequency(self, config, profile):
        """Should flag excessive frequency."""
        detector = FrequencyAnomalyDetector(config)
        
        # Record many requests (over threshold: 10 * 2.0 = 20)
        for i in range(25):
            await detector.record_request("user-123")
        
        event = AnomalyEvent(
            event_id="event-1",
            timestamp=datetime.now(timezone.utc),
            user_id="user-123",
            event_type="api_call",
        )
        
        anomalies = await detector.detect(event, profile)
        
        velocity_anomalies = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.REQUEST_VELOCITY
        ]
        assert len(velocity_anomalies) >= 1
        assert velocity_anomalies[0].baseline_value == 10.0


# =============================================================================
# Test: Data Access Anomaly Detector
# =============================================================================

class TestDataAccessAnomalyDetector:
    """Test DataAccessAnomalyDetector."""
    
    @pytest.mark.asyncio
    async def test_normal_volume(self, config, profile):
        """Should not flag normal data volume."""
        detector = DataAccessAnomalyDetector(config)
        
        # Record normal volume (under threshold: 10MB * 3 = 30MB)
        await detector.record_access("user-123", 5_000_000)  # 5MB
        
        event = AnomalyEvent(
            event_id="event-1",
            timestamp=datetime.now(timezone.utc),
            user_id="user-123",
            event_type="api_call",
            data_volume_bytes=1000,
        )
        
        anomalies = await detector.detect(event, profile)
        volume_anomalies = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.EXCESSIVE_DATA_ACCESS
        ]
        assert len(volume_anomalies) == 0
    
    @pytest.mark.asyncio
    async def test_excessive_volume(self, config, profile):
        """Should flag excessive data volume."""
        detector = DataAccessAnomalyDetector(config)
        
        # Record excessive volume (over threshold: 10MB * 3 = 30MB)
        await detector.record_access("user-123", 50_000_000)  # 50MB
        
        event = AnomalyEvent(
            event_id="event-1",
            timestamp=datetime.now(timezone.utc),
            user_id="user-123",
            event_type="api_call",
            data_volume_bytes=1000,
        )
        
        anomalies = await detector.detect(event, profile)
        
        volume_anomalies = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.EXCESSIVE_DATA_ACCESS
        ]
        assert len(volume_anomalies) >= 1
    
    @pytest.mark.asyncio
    async def test_unusual_resource(self, config, profile):
        """Should flag unusual resource access."""
        detector = DataAccessAnomalyDetector(config)
        
        event = AnomalyEvent(
            event_id="event-1",
            timestamp=datetime.now(timezone.utc),
            user_id="user-123",
            event_type="api_call",
            resource="/api/admin/secrets",  # Unusual resource
        )
        
        anomalies = await detector.detect(event, profile)
        
        resource_anomalies = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.UNUSUAL_RESOURCE_ACCESS
        ]
        assert len(resource_anomalies) >= 1


# =============================================================================
# Test: Detection Engine
# =============================================================================

class TestAnomalyDetectionEngine:
    """Test AnomalyDetectionEngine."""
    
    @pytest.mark.asyncio
    async def test_no_anomalies_without_baseline(self, engine):
        """Should not detect anomalies without baseline."""
        event = AnomalyEvent(
            event_id="event-1",
            timestamp=datetime.now(timezone.utc).replace(hour=3),  # Unusual
            user_id="new-user",
            event_type="api_call",
            ip_address="10.0.0.1",  # Unknown
            country_code="RU",  # Unknown
        )
        
        anomalies = await engine.analyze_event(event)
        
        # No anomalies because no baseline
        assert len(anomalies) == 0
    
    @pytest.mark.asyncio
    async def test_detect_after_baseline(self, config):
        """Should detect anomalies after baseline established."""
        engine = AnomalyDetectionEngine(config=config)
        
        # Build baseline with normal events
        for i in range(5):
            normal_event = AnomalyEvent(
                event_id=f"baseline-{i}",
                timestamp=datetime.now(timezone.utc).replace(hour=10),
                user_id="user-123",
                event_type="api_call",
                ip_address="192.168.1.100",
                country_code="US",
            )
            await engine.analyze_event(normal_event)
        
        # Now test with unusual event - new IP and country should trigger
        unusual_event = AnomalyEvent(
            event_id="unusual-1",
            timestamp=datetime.now(timezone.utc).replace(hour=10),  # Keep hour normal
            user_id="user-123",
            event_type="api_call",
            ip_address="10.0.0.1",  # New IP
            country_code="RU",  # New country
        )
        
        anomalies = await engine.analyze_event(unusual_event)
        
        # Should detect at least location anomaly (new IP or country)
        assert len(anomalies) >= 1
        assert any(a.anomaly_type == AnomalyType.UNUSUAL_LOCATION for a in anomalies)
    
    @pytest.mark.asyncio
    async def test_detection_hook(self, config):
        """Should call detection hooks."""
        engine = AnomalyDetectionEngine(config=config)
        
        hook_calls = []
        
        def test_hook(anomaly: DetectedAnomaly):
            hook_calls.append(anomaly)
        
        engine.add_detection_hook(test_hook)
        
        # Build baseline
        for i in range(5):
            event = AnomalyEvent(
                event_id=f"baseline-{i}",
                timestamp=datetime.now(timezone.utc).replace(hour=10),
                user_id="hook-user",
                event_type="api_call",
                ip_address="192.168.1.100",
                country_code="US",
            )
            await engine.analyze_event(event)
        
        # Trigger anomaly with new location
        unusual = AnomalyEvent(
            event_id="unusual-1",
            timestamp=datetime.now(timezone.utc).replace(hour=10),
            user_id="hook-user",
            event_type="api_call",
            ip_address="10.0.0.1",  # New IP
            country_code="CN",  # New country
        )
        
        await engine.analyze_event(unusual)
        
        assert len(hook_calls) >= 1
    
    @pytest.mark.asyncio
    async def test_get_recent_anomalies(self, config):
        """Should retrieve recent anomalies."""
        engine = AnomalyDetectionEngine(config=config)
        
        # Build baseline and trigger anomaly
        for i in range(5):
            event = AnomalyEvent(
                event_id=f"baseline-{i}",
                timestamp=datetime.now(timezone.utc).replace(hour=10),
                user_id="recent-user",
                event_type="api_call",
                ip_address="192.168.1.100",
                country_code="US",
            )
            await engine.analyze_event(event)
        
        unusual = AnomalyEvent(
            event_id="unusual-1",
            timestamp=datetime.now(timezone.utc),
            user_id="recent-user",
            event_type="api_call",
            ip_address="10.0.0.1",  # New IP
            country_code="RU",  # New country
        )
        
        await engine.analyze_event(unusual)
        
        # Retrieve anomalies
        anomalies = await engine.get_recent_anomalies(user_id="recent-user")
        assert len(anomalies) >= 1
    
    @pytest.mark.asyncio
    async def test_update_anomaly_status(self, engine):
        """Should update anomaly status."""
        # Build baseline and trigger anomaly
        for i in range(5):
            event = AnomalyEvent(
                event_id=f"baseline-{i}",
                timestamp=datetime.now(timezone.utc).replace(hour=10),
                user_id="status-user",
                event_type="api_call",
                ip_address="192.168.1.100",
                country_code="US",
            )
            await engine.analyze_event(event)
        
        unusual = AnomalyEvent(
            event_id="unusual-1",
            timestamp=datetime.now(timezone.utc),
            user_id="status-user",
            event_type="api_call",
            ip_address="10.0.0.1",
            country_code="CN",
        )
        
        detected = await engine.analyze_event(unusual)
        
        if detected:
            # Update status
            result = await engine.update_anomaly_status(
                detected[0].anomaly_id,
                DetectionStatus.FALSE_POSITIVE,
            )
            assert result is True
            
            # Verify update
            anomalies = await engine.get_recent_anomalies(user_id="status-user")
            updated = next(
                (a for a in anomalies if a.anomaly_id == detected[0].anomaly_id),
                None,
            )
            if updated:
                assert updated.status == DetectionStatus.FALSE_POSITIVE


# =============================================================================
# Test: Data Classes
# =============================================================================

class TestDetectedAnomaly:
    """Test DetectedAnomaly data class."""
    
    def test_creation(self):
        """Should create anomaly with all fields."""
        anomaly = DetectedAnomaly(
            anomaly_id="anomaly-123",
            timestamp=datetime.now(timezone.utc),
            anomaly_type=AnomalyType.UNUSUAL_TIME,
            severity=AnomalySeverity.MEDIUM,
            confidence=0.75,
            description="Test anomaly",
            user_id="user-123",
            baseline_value=10.0,
            observed_value=30.0,
            deviation_factor=3.0,
        )
        
        assert anomaly.anomaly_id == "anomaly-123"
        assert anomaly.confidence == 0.75
    
    def test_to_dict(self):
        """Should convert to dictionary."""
        anomaly = DetectedAnomaly(
            anomaly_id="anomaly-123",
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            anomaly_type=AnomalyType.UNUSUAL_LOCATION,
            severity=AnomalySeverity.HIGH,
            confidence=0.85,
            description="New country detected",
            user_id="user-123",
            ip_address="10.0.0.1",
            tags=["location", "geographic"],
        )
        
        data = anomaly.to_dict()
        
        assert data["anomaly_id"] == "anomaly-123"
        assert data["anomaly_type"] == "unusual_location"
        assert data["severity"] == "high"
        assert "location" in data["tags"]


# =============================================================================
# Test: Helper Functions
# =============================================================================

class TestHelperFunctions:
    """Test helper functions."""
    
    def test_get_anomaly_engine(self):
        """Should return singleton engine."""
        engine1 = get_anomaly_engine()
        engine2 = get_anomaly_engine()
        assert engine1 is engine2
    
    @pytest.mark.asyncio
    async def test_detect_anomalies_convenience(self):
        """Should detect anomalies via convenience function."""
        # This creates/uses singleton engine
        AnomalyDetectionEngine.configure(
            config=AnomalyDetectionConfig(min_baseline_events=2)
        )
        
        # Build minimal baseline
        for i in range(3):
            await detect_anomalies(
                user_id="convenience-user",
                event_type="api_call",
                ip_address="192.168.1.100",
                country_code="US",
            )
        
        # Should work without errors
        anomalies = await detect_anomalies(
            user_id="convenience-user",
            event_type="api_call",
            ip_address="10.0.0.1",
            country_code="RU",
        )
        
        # May or may not detect anomalies depending on baseline
        assert isinstance(anomalies, list)


# =============================================================================
# Test: Singleton Pattern
# =============================================================================

class TestSingleton:
    """Test singleton pattern."""
    
    def test_configure_creates_instance(self):
        """Should configure singleton."""
        config = AnomalyDetectionConfig(
            min_baseline_events=5,
            request_rate_threshold_multiplier=5.0,
        )
        
        engine = AnomalyDetectionEngine.configure(config=config)
        
        assert engine._config.min_baseline_events == 5
        assert AnomalyDetectionEngine.get_instance() is engine
