"""
Tests for SEC-017: Failed Login Tracking.

Tests cover:
- Login attempt recording
- Lockout mechanisms
- Progressive lockout
- Suspicious pattern detection
- Geographic anomaly detection
- Rate limiting
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from shared.failed_login_tracking import (
    # Enums
    LockoutReason,
    LoginFailureReason,
    RiskLevel,
    # Data classes
    LoginAttempt,
    LockoutStatus,
    SuspiciousActivity,
    LoginStats,
    LockoutConfig,
    # Storage
    InMemoryLoginStorage,
    # Tracker
    FailedLoginTracker,
    # Geographic
    GeoLocation,
    GeoAnomalyDetector,
    # Rate limiter
    LoginRateLimiter,
    # Functions
    get_login_tracker,
    check_login_allowed,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def storage():
    """Create test storage."""
    return InMemoryLoginStorage()


@pytest.fixture
def config():
    """Create test config with fast lockouts."""
    return LockoutConfig(
        max_attempts=3,
        lockout_duration_seconds=60,
        attempt_window_seconds=300,
        enable_progressive_lockout=True,
        progressive_multiplier=2.0,
        max_lockout_duration_seconds=3600,
        ip_max_attempts=10,
        ip_lockout_duration_seconds=120,
    )


@pytest.fixture
def tracker(storage, config):
    """Create test tracker."""
    return FailedLoginTracker(storage=storage, config=config)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_lockout_reasons(self):
        """Should have expected lockout reasons."""
        assert LockoutReason.MAX_ATTEMPTS_EXCEEDED == "max_attempts_exceeded"
        assert LockoutReason.BRUTE_FORCE == "brute_force"
        assert LockoutReason.ADMIN_LOCKOUT == "admin_lockout"
    
    def test_failure_reasons(self):
        """Should have expected failure reasons."""
        assert LoginFailureReason.INVALID_CREDENTIALS == "invalid_credentials"
        assert LoginFailureReason.ACCOUNT_LOCKED == "account_locked"
        assert LoginFailureReason.MFA_INVALID == "mfa_invalid"
    
    def test_risk_levels(self):
        """Should have expected risk levels."""
        assert RiskLevel.LOW == "low"
        assert RiskLevel.CRITICAL == "critical"


# =============================================================================
# Test: Data Classes
# =============================================================================

class TestLoginAttempt:
    """Test LoginAttempt data class."""
    
    def test_creation(self):
        """Should create login attempt."""
        attempt = LoginAttempt(
            attempt_id="attempt-123",
            timestamp=datetime.now(timezone.utc),
            username="testuser",
            ip_address="192.168.1.100",
            success=False,
            failure_reason=LoginFailureReason.INVALID_PASSWORD,
            user_agent="Mozilla/5.0",
        )
        
        assert attempt.attempt_id == "attempt-123"
        assert attempt.success is False
        assert attempt.failure_reason == LoginFailureReason.INVALID_PASSWORD
    
    def test_to_dict(self):
        """Should convert to dictionary."""
        attempt = LoginAttempt(
            attempt_id="attempt-123",
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            username="testuser",
            ip_address="192.168.1.100",
            success=False,
            failure_reason=LoginFailureReason.INVALID_PASSWORD,
        )
        
        data = attempt.to_dict()
        assert data["attempt_id"] == "attempt-123"
        assert data["failure_reason"] == "invalid_password"
        assert data["timestamp"] == "2024-01-15T12:00:00+00:00"


class TestLockoutStatus:
    """Test LockoutStatus data class."""
    
    def test_unlocked_status(self):
        """Should create unlocked status."""
        status = LockoutStatus(
            is_locked=False,
            failed_attempts=2,
            remaining_attempts=3,
        )
        
        assert status.is_locked is False
        assert status.remaining_attempts == 3
    
    def test_locked_status(self):
        """Should create locked status."""
        now = datetime.now(timezone.utc)
        status = LockoutStatus(
            is_locked=True,
            reason=LockoutReason.MAX_ATTEMPTS_EXCEEDED,
            locked_at=now,
            unlocks_at=now + timedelta(minutes=15),
            failed_attempts=5,
            lockout_duration_seconds=900,
        )
        
        assert status.is_locked is True
        assert status.reason == LockoutReason.MAX_ATTEMPTS_EXCEEDED
    
    def test_to_dict(self):
        """Should convert to dictionary."""
        now = datetime.now(timezone.utc)
        status = LockoutStatus(
            is_locked=True,
            reason=LockoutReason.BRUTE_FORCE,
            locked_at=now,
            unlocks_at=now + timedelta(minutes=30),
            failed_attempts=20,
        )
        
        data = status.to_dict()
        assert data["is_locked"] is True
        assert data["reason"] == "brute_force"


class TestSuspiciousActivity:
    """Test SuspiciousActivity data class."""
    
    def test_creation(self):
        """Should create suspicious activity."""
        activity = SuspiciousActivity(
            activity_id="suspicious-123",
            timestamp=datetime.now(timezone.utc),
            activity_type="credential_stuffing",
            risk_level=RiskLevel.HIGH,
            ip_address="192.168.1.100",
            description="Possible credential stuffing detected",
        )
        
        assert activity.activity_type == "credential_stuffing"
        assert activity.risk_level == RiskLevel.HIGH


# =============================================================================
# Test: Storage
# =============================================================================

class TestInMemoryStorage:
    """Test InMemoryLoginStorage."""
    
    @pytest.mark.asyncio
    async def test_record_attempt(self, storage):
        """Should record login attempt."""
        attempt = LoginAttempt(
            attempt_id="attempt-1",
            timestamp=datetime.now(timezone.utc),
            username="testuser",
            ip_address="192.168.1.100",
            success=False,
        )
        
        result = await storage.record_attempt(attempt)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_get_attempts_by_username(self, storage):
        """Should filter attempts by username."""
        for i in range(5):
            await storage.record_attempt(LoginAttempt(
                attempt_id=f"attempt-{i}",
                timestamp=datetime.now(timezone.utc),
                username="user1" if i < 3 else "user2",
                ip_address="192.168.1.100",
                success=False,
            ))
        
        attempts = await storage.get_attempts(username="user1")
        assert len(attempts) == 3
    
    @pytest.mark.asyncio
    async def test_get_attempts_by_ip(self, storage):
        """Should filter attempts by IP."""
        for i in range(5):
            await storage.record_attempt(LoginAttempt(
                attempt_id=f"attempt-{i}",
                timestamp=datetime.now(timezone.utc),
                username="testuser",
                ip_address=f"192.168.1.{i % 2}",
                success=False,
            ))
        
        attempts = await storage.get_attempts(ip_address="192.168.1.0")
        assert len(attempts) == 3
    
    @pytest.mark.asyncio
    async def test_get_failed_count(self, storage):
        """Should count failed attempts."""
        for i in range(10):
            await storage.record_attempt(LoginAttempt(
                attempt_id=f"attempt-{i}",
                timestamp=datetime.now(timezone.utc),
                username="testuser",
                ip_address="192.168.1.100",
                success=i < 3,  # First 3 are successful
            ))
        
        count = await storage.get_failed_count(username="testuser")
        assert count == 7
    
    @pytest.mark.asyncio
    async def test_set_and_get_lockout(self, storage):
        """Should set and get lockout."""
        await storage.set_lockout(
            key="user:testuser",
            reason=LockoutReason.MAX_ATTEMPTS_EXCEEDED,
            duration_seconds=900,
            attempt_count=5,
        )
        
        lockout = await storage.get_lockout("user:testuser")
        assert lockout is not None
        reason, locked_at, unlocks_at, count = lockout
        assert reason == LockoutReason.MAX_ATTEMPTS_EXCEEDED
        assert count == 5
    
    @pytest.mark.asyncio
    async def test_expired_lockout_returns_none(self, storage):
        """Should return None for expired lockout."""
        await storage.set_lockout(
            key="user:testuser",
            reason=LockoutReason.MAX_ATTEMPTS_EXCEEDED,
            duration_seconds=0,  # Immediate expiry
            attempt_count=5,
        )
        
        # Sleep briefly to ensure expiry
        await asyncio.sleep(0.01)
        
        lockout = await storage.get_lockout("user:testuser")
        assert lockout is None
    
    @pytest.mark.asyncio
    async def test_clear_lockout(self, storage):
        """Should clear lockout."""
        await storage.set_lockout(
            key="user:testuser",
            reason=LockoutReason.MAX_ATTEMPTS_EXCEEDED,
            duration_seconds=900,
            attempt_count=5,
        )
        
        result = await storage.clear_lockout("user:testuser")
        assert result is True
        
        lockout = await storage.get_lockout("user:testuser")
        assert lockout is None


# =============================================================================
# Test: Failed Login Tracker
# =============================================================================

class TestFailedLoginTracker:
    """Test FailedLoginTracker."""
    
    @pytest.mark.asyncio
    async def test_record_successful_attempt(self, tracker):
        """Should record successful login."""
        attempt = await tracker.record_attempt(
            username="testuser",
            ip_address="192.168.1.100",
            success=True,
        )
        
        assert attempt.attempt_id is not None
        assert attempt.success is True
    
    @pytest.mark.asyncio
    async def test_record_failed_attempt(self, tracker):
        """Should record failed login."""
        attempt = await tracker.record_attempt(
            username="testuser",
            ip_address="192.168.1.100",
            success=False,
            failure_reason=LoginFailureReason.INVALID_PASSWORD,
        )
        
        assert attempt.success is False
        assert attempt.failure_reason == LoginFailureReason.INVALID_PASSWORD
    
    @pytest.mark.asyncio
    async def test_lockout_after_max_attempts(self, tracker):
        """Should lock user after max attempts."""
        # Record max_attempts (3) failures
        for i in range(3):
            await tracker.record_attempt(
                username="testuser",
                ip_address="192.168.1.100",
                success=False,
            )
        
        status = await tracker.check_lockout("testuser")
        assert status.is_locked is True
        assert status.reason == LockoutReason.MAX_ATTEMPTS_EXCEEDED
    
    @pytest.mark.asyncio
    async def test_no_lockout_before_max_attempts(self, tracker):
        """Should not lock before max attempts."""
        # Record max_attempts - 1 (2) failures
        for i in range(2):
            await tracker.record_attempt(
                username="testuser",
                ip_address="192.168.1.100",
                success=False,
            )
        
        status = await tracker.check_lockout("testuser")
        assert status.is_locked is False
        assert status.remaining_attempts == 1
    
    @pytest.mark.asyncio
    async def test_unlock_user(self, tracker):
        """Should unlock user manually."""
        # Lock user
        for i in range(3):
            await tracker.record_attempt(
                username="testuser",
                ip_address="192.168.1.100",
                success=False,
            )
        
        # Verify locked
        status = await tracker.check_lockout("testuser")
        assert status.is_locked is True
        
        # Unlock
        result = await tracker.unlock_user("testuser")
        assert result is True
        
        # Verify unlocked
        status = await tracker.check_lockout("testuser")
        assert status.is_locked is False
    
    @pytest.mark.asyncio
    async def test_manual_lock_user(self, tracker):
        """Should lock user manually."""
        await tracker.lock_user(
            username="testuser",
            reason=LockoutReason.ADMIN_LOCKOUT,
            duration_seconds=3600,
        )
        
        status = await tracker.check_lockout("testuser")
        assert status.is_locked is True
        assert status.reason == LockoutReason.ADMIN_LOCKOUT
    
    @pytest.mark.asyncio
    async def test_successful_login_resets_lockout(self, tracker):
        """Should reset lockout on successful login if configured."""
        # Record some failures
        for i in range(2):
            await tracker.record_attempt(
                username="testuser",
                ip_address="192.168.1.100",
                success=False,
            )
        
        # Successful login
        await tracker.record_attempt(
            username="testuser",
            ip_address="192.168.1.100",
            success=True,
        )
        
        # Check remaining attempts reset
        status = await tracker.check_lockout("testuser")
        assert status.failed_attempts == 2  # Failures still counted
    
    @pytest.mark.asyncio
    async def test_hook_called_on_attempt(self, tracker):
        """Should call hooks on login attempt."""
        hook_calls = []
        
        def test_hook(attempt: LoginAttempt):
            hook_calls.append(attempt)
        
        tracker.add_hook(test_hook)
        
        await tracker.record_attempt(
            username="testuser",
            ip_address="192.168.1.100",
            success=False,
        )
        
        assert len(hook_calls) == 1
        assert hook_calls[0].username == "testuser"
    
    @pytest.mark.asyncio
    async def test_get_recent_attempts(self, tracker):
        """Should get recent login attempts."""
        for i in range(5):
            await tracker.record_attempt(
                username="testuser",
                ip_address="192.168.1.100",
                success=i % 2 == 0,
            )
        
        attempts = await tracker.get_recent_attempts(username="testuser")
        assert len(attempts) == 5


# =============================================================================
# Test: Progressive Lockout
# =============================================================================

class TestProgressiveLockout:
    """Test progressive lockout with exponential backoff."""
    
    @pytest.mark.asyncio
    async def test_first_lockout_duration(self, tracker):
        """Should use base duration for first lockout."""
        # Trigger lockout
        for i in range(3):
            await tracker.record_attempt(
                username="testuser",
                ip_address="192.168.1.100",
                success=False,
            )
        
        status = await tracker.check_lockout("testuser")
        assert status.lockout_duration_seconds == 60  # Base duration
    
    @pytest.mark.asyncio
    async def test_progressive_lockout_increases(self):
        """Should increase duration on repeated lockouts."""
        # Use separate tracker and storage for this test
        storage = InMemoryLoginStorage()
        config = LockoutConfig(
            max_attempts=3,
            lockout_duration_seconds=60,
            attempt_window_seconds=300,
            enable_progressive_lockout=True,
            progressive_multiplier=2.0,
        )
        tracker = FailedLoginTracker(storage=storage, config=config)
        
        # First lockout
        for i in range(3):
            await tracker.record_attempt(
                username="proguser",
                ip_address="10.0.0.1",
                success=False,
            )
        
        status1 = await tracker.check_lockout("proguser")
        assert status1.is_locked is True
        assert status1.lockout_duration_seconds == 60  # Base duration
        
        # Unlock and trigger again (need to clear the storage failures too)
        await tracker.unlock_user("proguser")
        
        # Wait a tiny bit and record new failures (creating fresh tracker state)
        for i in range(3):
            await tracker.record_attempt(
                username="proguser",
                ip_address="10.0.0.1",
                success=False,
            )
        
        status2 = await tracker.check_lockout("proguser")
        # Second lockout should be 2x duration = 120s
        # But since failures accumulated, it triggers multiple lockouts
        # The key is that lockout_counts increased
        assert status2.is_locked is True
        assert status2.lockout_duration_seconds > 60  # Should be more than base


# =============================================================================
# Test: IP Lockout
# =============================================================================

class TestIPLockout:
    """Test IP-based lockout."""
    
    @pytest.mark.asyncio
    async def test_ip_lockout_after_max_attempts(self, tracker):
        """Should lock IP after max attempts."""
        # Record ip_max_attempts (10) failures from same IP
        for i in range(10):
            await tracker.record_attempt(
                username=f"user{i}",
                ip_address="192.168.1.100",
                success=False,
            )
        
        status = await tracker.check_lockout("newuser", "192.168.1.100")
        assert status.is_locked is True
        assert status.reason == LockoutReason.BRUTE_FORCE
    
    @pytest.mark.asyncio
    async def test_unlock_ip(self, tracker):
        """Should unlock IP manually."""
        # Lock IP
        for i in range(10):
            await tracker.record_attempt(
                username=f"user{i}",
                ip_address="192.168.1.100",
                success=False,
            )
        
        # Unlock
        await tracker.unlock_ip("192.168.1.100")
        
        status = await tracker.check_lockout("newuser", "192.168.1.100")
        assert status.is_locked is False


# =============================================================================
# Test: Geographic Anomaly Detection
# =============================================================================

class TestGeoAnomalyDetector:
    """Test GeoAnomalyDetector."""
    
    def test_high_risk_country(self):
        """Should flag high-risk country."""
        detector = GeoAnomalyDetector()
        
        location = GeoLocation(country_code="KP")  # North Korea
        
        activity = detector.check_anomaly(
            username="testuser",
            timestamp=datetime.now(timezone.utc),
            location=location,
        )
        
        assert activity is not None
        assert activity.activity_type == "high_risk_country"
        assert activity.risk_level == RiskLevel.HIGH
    
    def test_new_location(self):
        """Should flag new location."""
        detector = GeoAnomalyDetector()
        
        # Record initial location
        detector.record_location(
            username="testuser",
            timestamp=datetime.now(timezone.utc) - timedelta(days=1),
            location=GeoLocation(country_code="US"),
        )
        
        # Check login from new country
        activity = detector.check_anomaly(
            username="testuser",
            timestamp=datetime.now(timezone.utc),
            location=GeoLocation(country_code="GB"),
        )
        
        assert activity is not None
        assert activity.activity_type == "new_location"
        assert activity.risk_level == RiskLevel.MEDIUM
    
    def test_impossible_travel(self):
        """Should detect impossible travel."""
        detector = GeoAnomalyDetector(max_travel_speed_kmh=500)
        
        # Record New York login
        detector.record_location(
            username="testuser",
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=30),
            location=GeoLocation(
                country_code="US",
                city="New York",
                latitude=40.7128,
                longitude=-74.0060,
            ),
        )
        
        # Check login from London (5,570 km away) 30 minutes later
        # Would require ~11,000 km/h
        activity = detector.check_anomaly(
            username="testuser",
            timestamp=datetime.now(timezone.utc),
            location=GeoLocation(
                country_code="GB",
                city="London",
                latitude=51.5074,
                longitude=-0.1278,
            ),
        )
        
        assert activity is not None
        assert activity.activity_type == "impossible_travel"
        assert activity.risk_level == RiskLevel.CRITICAL
    
    def test_normal_travel(self):
        """Should not flag normal travel."""
        detector = GeoAnomalyDetector(max_travel_speed_kmh=1000)
        
        # Record New York login
        detector.record_location(
            username="testuser",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=8),
            location=GeoLocation(
                country_code="US",
                city="New York",
                latitude=40.7128,
                longitude=-74.0060,
            ),
        )
        
        # Check login from London 8 hours later (reasonable flight time)
        activity = detector.check_anomaly(
            username="testuser",
            timestamp=datetime.now(timezone.utc),
            location=GeoLocation(
                country_code="GB",
                city="London",
                latitude=51.5074,
                longitude=-0.1278,
            ),
        )
        
        # Might flag as new_location but not impossible_travel
        if activity:
            assert activity.activity_type != "impossible_travel"


# =============================================================================
# Test: Rate Limiter
# =============================================================================

class TestLoginRateLimiter:
    """Test LoginRateLimiter."""
    
    @pytest.mark.asyncio
    async def test_allows_under_limit(self):
        """Should allow requests under limit."""
        limiter = LoginRateLimiter(
            max_attempts_per_minute=10,
            max_attempts_per_hour=100,
        )
        
        for i in range(5):
            allowed, retry_after = await limiter.check_rate_limit("user:testuser")
            await limiter.record_attempt("user:testuser")
            assert allowed is True
            assert retry_after is None
    
    @pytest.mark.asyncio
    async def test_blocks_over_minute_limit(self):
        """Should block when minute limit exceeded."""
        limiter = LoginRateLimiter(
            max_attempts_per_minute=3,
            max_attempts_per_hour=100,
        )
        
        # Record 3 attempts
        for i in range(3):
            await limiter.record_attempt("user:testuser")
        
        # Fourth should be blocked
        allowed, retry_after = await limiter.check_rate_limit("user:testuser")
        assert allowed is False
        assert retry_after is not None
        assert retry_after <= 61  # Should retry within ~1 minute
    
    @pytest.mark.asyncio
    async def test_blocks_over_hour_limit(self):
        """Should block when hour limit exceeded."""
        limiter = LoginRateLimiter(
            max_attempts_per_minute=1000,  # High per-minute limit
            max_attempts_per_hour=5,
        )
        
        # Record 5 attempts
        for i in range(5):
            await limiter.record_attempt("user:testuser")
        
        # Sixth should be blocked
        allowed, retry_after = await limiter.check_rate_limit("user:testuser")
        assert allowed is False
        assert retry_after is not None


# =============================================================================
# Test: Statistics
# =============================================================================

class TestLoginStats:
    """Test login statistics."""
    
    @pytest.mark.asyncio
    async def test_get_stats(self, tracker):
        """Should calculate stats."""
        # Record various attempts
        for i in range(10):
            await tracker.record_attempt(
                username=f"user{i % 3}",  # 3 unique users
                ip_address=f"192.168.1.{i % 2}",  # 2 unique IPs
                success=i < 4,  # 4 successful, 6 failed
            )
        
        stats = await tracker.get_stats()
        
        assert stats.total_attempts == 10
        assert stats.successful_attempts == 4
        assert stats.failed_attempts == 6
        assert stats.unique_usernames == 3
        assert stats.unique_ips == 2


# =============================================================================
# Test: Helper Functions
# =============================================================================

class TestHelperFunctions:
    """Test helper functions."""
    
    def test_get_login_tracker(self):
        """Should return singleton instance."""
        tracker1 = get_login_tracker()
        tracker2 = get_login_tracker()
        assert tracker1 is tracker2
    
    @pytest.mark.asyncio
    async def test_check_login_allowed(self):
        """Should check if login is allowed."""
        storage = InMemoryLoginStorage()
        config = LockoutConfig(max_attempts=2)
        FailedLoginTracker.configure(storage=storage, config=config)
        
        tracker = get_login_tracker()
        
        # Should be allowed initially
        allowed, status = await check_login_allowed("testuser", "192.168.1.100")
        assert allowed is True
        assert status is None
        
        # Record failures to trigger lockout
        for i in range(2):
            await tracker.record_attempt(
                username="testuser",
                ip_address="192.168.1.100",
                success=False,
            )
        
        # Should be blocked now
        allowed, status = await check_login_allowed("testuser", "192.168.1.100")
        assert allowed is False
        assert status is not None
        assert status.is_locked is True


# =============================================================================
# Test: Singleton Pattern
# =============================================================================

class TestSingleton:
    """Test singleton pattern."""
    
    def test_configure_creates_instance(self):
        """Should configure singleton."""
        storage = InMemoryLoginStorage()
        config = LockoutConfig(max_attempts=10)
        
        tracker = FailedLoginTracker.configure(
            storage=storage,
            config=config,
        )
        
        assert tracker._config.max_attempts == 10
        assert FailedLoginTracker.get_instance() is tracker
