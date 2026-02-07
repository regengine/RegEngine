"""
SEC-017: Failed Login Tracking.

Comprehensive failed login tracking with:
- Configurable attempt tracking per user/IP
- Progressive lockout with exponential backoff
- Suspicious pattern detection
- Geolocation anomaly detection
- Notification hooks for security alerts
"""

import asyncio
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class LockoutReason(str, Enum):
    """Reasons for account lockout."""
    MAX_ATTEMPTS_EXCEEDED = "max_attempts_exceeded"
    SUSPICIOUS_PATTERN = "suspicious_pattern"
    GEOGRAPHIC_ANOMALY = "geographic_anomaly"
    CREDENTIAL_STUFFING = "credential_stuffing"
    BRUTE_FORCE = "brute_force"
    ADMIN_LOCKOUT = "admin_lockout"


class LoginFailureReason(str, Enum):
    """Reasons for login failure."""
    INVALID_CREDENTIALS = "invalid_credentials"
    INVALID_USERNAME = "invalid_username"
    INVALID_PASSWORD = "invalid_password"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_DISABLED = "account_disabled"
    MFA_REQUIRED = "mfa_required"
    MFA_INVALID = "mfa_invalid"
    EXPIRED_PASSWORD = "expired_password"
    RATE_LIMITED = "rate_limited"
    IP_BLOCKED = "ip_blocked"


class RiskLevel(str, Enum):
    """Risk level of login attempt."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class LoginAttempt:
    """Record of a login attempt."""
    attempt_id: str
    timestamp: datetime
    username: str
    ip_address: str
    success: bool
    failure_reason: Optional[LoginFailureReason] = None
    user_agent: Optional[str] = None
    country_code: Optional[str] = None
    city: Optional[str] = None
    device_fingerprint: Optional[str] = None
    session_id: Optional[str] = None
    tenant_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "attempt_id": self.attempt_id,
            "timestamp": self.timestamp.isoformat(),
            "username": self.username,
            "ip_address": self.ip_address,
            "success": self.success,
        }
        
        if self.failure_reason:
            result["failure_reason"] = self.failure_reason.value
        if self.user_agent:
            result["user_agent"] = self.user_agent
        if self.country_code:
            result["country_code"] = self.country_code
        if self.city:
            result["city"] = self.city
        if self.device_fingerprint:
            result["device_fingerprint"] = self.device_fingerprint
        if self.session_id:
            result["session_id"] = self.session_id
        if self.tenant_id:
            result["tenant_id"] = self.tenant_id
        if self.metadata:
            result["metadata"] = self.metadata
            
        return result


@dataclass
class LockoutStatus:
    """Status of an account lockout."""
    is_locked: bool
    reason: Optional[LockoutReason] = None
    locked_at: Optional[datetime] = None
    unlocks_at: Optional[datetime] = None
    failed_attempts: int = 0
    remaining_attempts: int = 0
    lockout_duration_seconds: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "is_locked": self.is_locked,
            "failed_attempts": self.failed_attempts,
            "remaining_attempts": self.remaining_attempts,
        }
        
        if self.reason:
            result["reason"] = self.reason.value
        if self.locked_at:
            result["locked_at"] = self.locked_at.isoformat()
        if self.unlocks_at:
            result["unlocks_at"] = self.unlocks_at.isoformat()
        if self.lockout_duration_seconds:
            result["lockout_duration_seconds"] = self.lockout_duration_seconds
            
        return result


@dataclass
class SuspiciousActivity:
    """Detected suspicious login activity."""
    activity_id: str
    timestamp: datetime
    activity_type: str
    risk_level: RiskLevel
    username: Optional[str] = None
    ip_address: Optional[str] = None
    description: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "activity_id": self.activity_id,
            "timestamp": self.timestamp.isoformat(),
            "activity_type": self.activity_type,
            "risk_level": self.risk_level.value,
            "username": self.username,
            "ip_address": self.ip_address,
            "description": self.description,
            "details": self.details,
        }


@dataclass
class LoginStats:
    """Statistics for login attempts."""
    total_attempts: int = 0
    successful_attempts: int = 0
    failed_attempts: int = 0
    unique_usernames: int = 0
    unique_ips: int = 0
    locked_accounts: int = 0
    blocked_ips: int = 0
    time_period_seconds: int = 0


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class LockoutConfig:
    """Configuration for lockout behavior."""
    # Basic lockout settings
    max_attempts: int = 5
    lockout_duration_seconds: int = 900  # 15 minutes
    
    # Progressive lockout (exponential backoff)
    enable_progressive_lockout: bool = True
    progressive_multiplier: float = 2.0
    max_lockout_duration_seconds: int = 86400  # 24 hours
    
    # Attempt window
    attempt_window_seconds: int = 3600  # 1 hour
    
    # IP-based settings
    enable_ip_lockout: bool = True
    ip_max_attempts: int = 20
    ip_lockout_duration_seconds: int = 1800  # 30 minutes
    
    # Suspicious activity thresholds
    credential_stuffing_threshold: int = 10  # failures per minute
    brute_force_threshold: int = 50  # attempts per IP per hour
    
    # Auto-unlock
    auto_unlock_on_success: bool = True
    
    # Reset settings
    reset_on_success: bool = True


# =============================================================================
# Storage Backend
# =============================================================================

class LoginTrackingStorage(ABC):
    """Abstract base for login tracking storage."""
    
    @abstractmethod
    async def record_attempt(self, attempt: LoginAttempt) -> bool:
        """Record a login attempt."""
        pass
    
    @abstractmethod
    async def get_attempts(
        self,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[LoginAttempt]:
        """Get login attempts matching criteria."""
        pass
    
    @abstractmethod
    async def get_failed_count(
        self,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> int:
        """Get count of failed attempts."""
        pass
    
    @abstractmethod
    async def set_lockout(
        self,
        key: str,
        reason: LockoutReason,
        duration_seconds: int,
        attempt_count: int,
    ) -> bool:
        """Set a lockout."""
        pass
    
    @abstractmethod
    async def get_lockout(self, key: str) -> Optional[Tuple[LockoutReason, datetime, datetime, int]]:
        """Get lockout info: (reason, locked_at, unlocks_at, attempt_count)."""
        pass
    
    @abstractmethod
    async def clear_lockout(self, key: str) -> bool:
        """Clear a lockout."""
        pass
    
    @abstractmethod
    async def record_suspicious_activity(self, activity: SuspiciousActivity) -> bool:
        """Record suspicious activity."""
        pass


class InMemoryLoginStorage(LoginTrackingStorage):
    """In-memory implementation for testing."""
    
    def __init__(self, max_attempts: int = 10000):
        self._attempts: List[LoginAttempt] = []
        self._lockouts: Dict[str, Tuple[LockoutReason, datetime, datetime, int]] = {}
        self._suspicious: List[SuspiciousActivity] = []
        self._max_attempts = max_attempts
        self._lock = asyncio.Lock()
    
    async def record_attempt(self, attempt: LoginAttempt) -> bool:
        async with self._lock:
            self._attempts.append(attempt)
            
            # Trim old attempts if needed
            if len(self._attempts) > self._max_attempts:
                self._attempts = self._attempts[-self._max_attempts:]
            
            return True
    
    async def get_attempts(
        self,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[LoginAttempt]:
        async with self._lock:
            results = []
            
            for attempt in reversed(self._attempts):
                if len(results) >= limit:
                    break
                
                if username and attempt.username != username:
                    continue
                if ip_address and attempt.ip_address != ip_address:
                    continue
                if since and attempt.timestamp < since:
                    continue
                
                results.append(attempt)
            
            return results
    
    async def get_failed_count(
        self,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> int:
        async with self._lock:
            count = 0
            
            for attempt in self._attempts:
                if attempt.success:
                    continue
                if username and attempt.username != username:
                    continue
                if ip_address and attempt.ip_address != ip_address:
                    continue
                if since and attempt.timestamp < since:
                    continue
                
                count += 1
            
            return count
    
    async def set_lockout(
        self,
        key: str,
        reason: LockoutReason,
        duration_seconds: int,
        attempt_count: int,
    ) -> bool:
        async with self._lock:
            now = datetime.now(timezone.utc)
            unlocks_at = now + timedelta(seconds=duration_seconds)
            self._lockouts[key] = (reason, now, unlocks_at, attempt_count)
            return True
    
    async def get_lockout(self, key: str) -> Optional[Tuple[LockoutReason, datetime, datetime, int]]:
        async with self._lock:
            lockout = self._lockouts.get(key)
            
            if lockout is None:
                return None
            
            reason, locked_at, unlocks_at, count = lockout
            
            # Check if expired
            if datetime.now(timezone.utc) >= unlocks_at:
                del self._lockouts[key]
                return None
            
            return lockout
    
    async def clear_lockout(self, key: str) -> bool:
        async with self._lock:
            if key in self._lockouts:
                del self._lockouts[key]
                return True
            return False
    
    async def record_suspicious_activity(self, activity: SuspiciousActivity) -> bool:
        async with self._lock:
            self._suspicious.append(activity)
            return True
    
    async def get_suspicious_activities(
        self,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[SuspiciousActivity]:
        """Get suspicious activities."""
        async with self._lock:
            results = []
            
            for activity in reversed(self._suspicious):
                if len(results) >= limit:
                    break
                if since and activity.timestamp < since:
                    continue
                results.append(activity)
            
            return results


# =============================================================================
# Failed Login Tracker
# =============================================================================

class FailedLoginTracker:
    """
    Tracks failed login attempts and manages account lockouts.
    
    Features:
    - Per-user and per-IP tracking
    - Progressive lockout with exponential backoff
    - Suspicious pattern detection
    - Notification hooks
    """
    
    _instance: Optional["FailedLoginTracker"] = None
    
    def __init__(
        self,
        storage: Optional[LoginTrackingStorage] = None,
        config: Optional[LockoutConfig] = None,
    ):
        self._storage = storage or InMemoryLoginStorage()
        self._config = config or LockoutConfig()
        self._hooks: List[Callable[[LoginAttempt], None]] = []
        self._alert_hooks: List[Callable[[SuspiciousActivity], None]] = []
        self._id_counter = 0
        self._lockout_counts: Dict[str, int] = defaultdict(int)  # Track consecutive lockouts
    
    @classmethod
    def get_instance(cls) -> "FailedLoginTracker":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(
        cls,
        storage: Optional[LoginTrackingStorage] = None,
        config: Optional[LockoutConfig] = None,
    ) -> "FailedLoginTracker":
        """Configure singleton instance."""
        cls._instance = cls(storage=storage, config=config)
        return cls._instance
    
    def add_hook(self, hook: Callable[[LoginAttempt], None]) -> None:
        """Add a hook for login attempts."""
        self._hooks.append(hook)
    
    def add_alert_hook(self, hook: Callable[[SuspiciousActivity], None]) -> None:
        """Add a hook for suspicious activity alerts."""
        self._alert_hooks.append(hook)
    
    def _generate_id(self) -> str:
        """Generate unique ID."""
        self._id_counter += 1
        return f"attempt-{int(time.time() * 1000)}-{self._id_counter}"
    
    def _user_key(self, username: str, tenant_id: Optional[str] = None) -> str:
        """Generate user lockout key."""
        if tenant_id:
            return f"user:{tenant_id}:{username}"
        return f"user:{username}"
    
    def _ip_key(self, ip_address: str) -> str:
        """Generate IP lockout key."""
        return f"ip:{ip_address}"
    
    async def record_attempt(
        self,
        username: str,
        ip_address: str,
        success: bool,
        failure_reason: Optional[LoginFailureReason] = None,
        user_agent: Optional[str] = None,
        country_code: Optional[str] = None,
        city: Optional[str] = None,
        device_fingerprint: Optional[str] = None,
        tenant_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LoginAttempt:
        """
        Record a login attempt.
        
        Returns the recorded attempt with ID and timestamp.
        """
        attempt = LoginAttempt(
            attempt_id=self._generate_id(),
            timestamp=datetime.now(timezone.utc),
            username=username,
            ip_address=ip_address,
            success=success,
            failure_reason=failure_reason,
            user_agent=user_agent,
            country_code=country_code,
            city=city,
            device_fingerprint=device_fingerprint,
            tenant_id=tenant_id,
            metadata=metadata or {},
        )
        
        await self._storage.record_attempt(attempt)
        
        # Call hooks
        for hook in self._hooks:
            try:
                hook(attempt)
            except Exception as e:
                logger.error("Hook error: %s", e)
        
        # Handle success/failure
        if success:
            await self._handle_success(attempt)
        else:
            await self._handle_failure(attempt)
        
        return attempt
    
    async def _handle_success(self, attempt: LoginAttempt) -> None:
        """Handle successful login."""
        if self._config.reset_on_success:
            # Reset lockout count for user
            user_key = self._user_key(attempt.username, attempt.tenant_id)
            self._lockout_counts[user_key] = 0
        
        if self._config.auto_unlock_on_success:
            # Clear any lockout
            user_key = self._user_key(attempt.username, attempt.tenant_id)
            await self._storage.clear_lockout(user_key)
    
    async def _handle_failure(self, attempt: LoginAttempt) -> None:
        """Handle failed login."""
        user_key = self._user_key(attempt.username, attempt.tenant_id)
        ip_key = self._ip_key(attempt.ip_address)
        
        # Get failure counts
        since = datetime.now(timezone.utc) - timedelta(
            seconds=self._config.attempt_window_seconds
        )
        
        user_failures = await self._storage.get_failed_count(
            username=attempt.username,
            since=since,
        )
        
        ip_failures = await self._storage.get_failed_count(
            ip_address=attempt.ip_address,
            since=since,
        )
        
        # Check for user lockout
        if user_failures >= self._config.max_attempts:
            await self._lock_user(user_key, user_failures)
        
        # Check for IP lockout
        if self._config.enable_ip_lockout and ip_failures >= self._config.ip_max_attempts:
            await self._lock_ip(ip_key, ip_failures)
        
        # Check for suspicious patterns
        await self._check_suspicious_patterns(attempt, user_failures, ip_failures)
    
    async def _lock_user(self, user_key: str, attempt_count: int) -> None:
        """Lock user account."""
        duration = self._calculate_lockout_duration(user_key)
        
        await self._storage.set_lockout(
            key=user_key,
            reason=LockoutReason.MAX_ATTEMPTS_EXCEEDED,
            duration_seconds=duration,
            attempt_count=attempt_count,
        )
        
        # Increment lockout count for progressive lockout
        self._lockout_counts[user_key] += 1
        
        logger.warning(
            "User locked: %s (duration: %ds, attempts: %d)",
            user_key,
            duration,
            attempt_count,
        )
    
    async def _lock_ip(self, ip_key: str, attempt_count: int) -> None:
        """Lock IP address."""
        await self._storage.set_lockout(
            key=ip_key,
            reason=LockoutReason.BRUTE_FORCE,
            duration_seconds=self._config.ip_lockout_duration_seconds,
            attempt_count=attempt_count,
        )
        
        logger.warning(
            "IP locked: %s (attempts: %d)",
            ip_key,
            attempt_count,
        )
    
    def _calculate_lockout_duration(self, key: str) -> int:
        """Calculate lockout duration with exponential backoff."""
        if not self._config.enable_progressive_lockout:
            return self._config.lockout_duration_seconds
        
        lockout_count = self._lockout_counts.get(key, 0)
        multiplier = self._config.progressive_multiplier ** lockout_count
        duration = int(self._config.lockout_duration_seconds * multiplier)
        
        return min(duration, self._config.max_lockout_duration_seconds)
    
    async def _check_suspicious_patterns(
        self,
        attempt: LoginAttempt,
        user_failures: int,
        ip_failures: int,
    ) -> None:
        """Check for suspicious login patterns."""
        # Check for credential stuffing (many failures across different users from same IP)
        recent_since = datetime.now(timezone.utc) - timedelta(minutes=1)
        recent_ip_failures = await self._storage.get_failed_count(
            ip_address=attempt.ip_address,
            since=recent_since,
        )
        
        if recent_ip_failures >= self._config.credential_stuffing_threshold:
            activity = SuspiciousActivity(
                activity_id=f"suspicious-{int(time.time() * 1000)}",
                timestamp=datetime.now(timezone.utc),
                activity_type="credential_stuffing",
                risk_level=RiskLevel.HIGH,
                ip_address=attempt.ip_address,
                description=f"Possible credential stuffing: {recent_ip_failures} failures in 1 minute",
                details={
                    "failures_per_minute": recent_ip_failures,
                    "threshold": self._config.credential_stuffing_threshold,
                },
            )
            
            await self._storage.record_suspicious_activity(activity)
            await self._trigger_alert(activity)
        
        # Check for brute force (many attempts on single user)
        if user_failures >= self._config.max_attempts * 2:
            activity = SuspiciousActivity(
                activity_id=f"suspicious-{int(time.time() * 1000)}",
                timestamp=datetime.now(timezone.utc),
                activity_type="brute_force",
                risk_level=RiskLevel.HIGH,
                username=attempt.username,
                ip_address=attempt.ip_address,
                description=f"Possible brute force attack: {user_failures} failures for user",
                details={
                    "user_failures": user_failures,
                    "max_attempts": self._config.max_attempts,
                },
            )
            
            await self._storage.record_suspicious_activity(activity)
            await self._trigger_alert(activity)
    
    async def _trigger_alert(self, activity: SuspiciousActivity) -> None:
        """Trigger alert hooks."""
        for hook in self._alert_hooks:
            try:
                hook(activity)
            except Exception as e:
                logger.error("Alert hook error: %s", e)
    
    async def check_lockout(
        self,
        username: str,
        ip_address: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> LockoutStatus:
        """
        Check if user or IP is locked out.
        
        Returns LockoutStatus with details.
        """
        user_key = self._user_key(username, tenant_id)
        
        # Check user lockout
        user_lockout = await self._storage.get_lockout(user_key)
        if user_lockout:
            reason, locked_at, unlocks_at, attempt_count = user_lockout
            return LockoutStatus(
                is_locked=True,
                reason=reason,
                locked_at=locked_at,
                unlocks_at=unlocks_at,
                failed_attempts=attempt_count,
                remaining_attempts=0,
                lockout_duration_seconds=int((unlocks_at - locked_at).total_seconds()),
            )
        
        # Check IP lockout
        if ip_address and self._config.enable_ip_lockout:
            ip_key = self._ip_key(ip_address)
            ip_lockout = await self._storage.get_lockout(ip_key)
            if ip_lockout:
                reason, locked_at, unlocks_at, attempt_count = ip_lockout
                return LockoutStatus(
                    is_locked=True,
                    reason=reason,
                    locked_at=locked_at,
                    unlocks_at=unlocks_at,
                    failed_attempts=attempt_count,
                    remaining_attempts=0,
                    lockout_duration_seconds=int((unlocks_at - locked_at).total_seconds()),
                )
        
        # Get current failure count
        since = datetime.now(timezone.utc) - timedelta(
            seconds=self._config.attempt_window_seconds
        )
        failed_count = await self._storage.get_failed_count(username=username, since=since)
        
        return LockoutStatus(
            is_locked=False,
            failed_attempts=failed_count,
            remaining_attempts=max(0, self._config.max_attempts - failed_count),
        )
    
    async def unlock_user(
        self,
        username: str,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """Manually unlock a user."""
        user_key = self._user_key(username, tenant_id)
        self._lockout_counts[user_key] = 0  # Reset progressive lockout
        return await self._storage.clear_lockout(user_key)
    
    async def unlock_ip(self, ip_address: str) -> bool:
        """Manually unlock an IP address."""
        ip_key = self._ip_key(ip_address)
        return await self._storage.clear_lockout(ip_key)
    
    async def lock_user(
        self,
        username: str,
        reason: LockoutReason = LockoutReason.ADMIN_LOCKOUT,
        duration_seconds: Optional[int] = None,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """Manually lock a user."""
        user_key = self._user_key(username, tenant_id)
        duration = duration_seconds or self._config.lockout_duration_seconds
        
        return await self._storage.set_lockout(
            key=user_key,
            reason=reason,
            duration_seconds=duration,
            attempt_count=0,
        )
    
    async def get_recent_attempts(
        self,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[LoginAttempt]:
        """Get recent login attempts."""
        return await self._storage.get_attempts(
            username=username,
            ip_address=ip_address,
            since=since,
            limit=limit,
        )
    
    async def get_stats(
        self,
        since: Optional[datetime] = None,
    ) -> LoginStats:
        """Get login statistics."""
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(hours=24)
        
        attempts = await self._storage.get_attempts(since=since, limit=10000)
        
        usernames: Set[str] = set()
        ips: Set[str] = set()
        successful = 0
        failed = 0
        
        for attempt in attempts:
            usernames.add(attempt.username)
            ips.add(attempt.ip_address)
            if attempt.success:
                successful += 1
            else:
                failed += 1
        
        return LoginStats(
            total_attempts=len(attempts),
            successful_attempts=successful,
            failed_attempts=failed,
            unique_usernames=len(usernames),
            unique_ips=len(ips),
            time_period_seconds=int((datetime.now(timezone.utc) - since).total_seconds()),
        )


# =============================================================================
# Geographic Anomaly Detection
# =============================================================================

@dataclass
class GeoLocation:
    """Geographic location."""
    country_code: str
    city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class GeoAnomalyDetector:
    """
    Detects geographic anomalies in login attempts.
    
    Flags suspicious logins based on:
    - Impossible travel (login from far location in short time)
    - New location for user
    - High-risk countries
    """
    
    # High-risk countries (example list - customize based on needs)
    HIGH_RISK_COUNTRIES: Set[str] = {
        "KP",  # North Korea
        "IR",  # Iran (for US companies under sanctions)
        "RU",  # Russia (depending on business)
    }
    
    def __init__(
        self,
        max_travel_speed_kmh: float = 1000.0,  # Max speed (km/h) between logins
        suspicious_time_threshold_seconds: int = 3600,  # 1 hour
    ):
        self._max_speed = max_travel_speed_kmh
        self._time_threshold = suspicious_time_threshold_seconds
        self._user_locations: Dict[str, List[Tuple[datetime, GeoLocation]]] = defaultdict(list)
    
    def record_location(
        self,
        username: str,
        timestamp: datetime,
        location: GeoLocation,
    ) -> None:
        """Record user's login location."""
        self._user_locations[username].append((timestamp, location))
        
        # Keep only recent locations
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        self._user_locations[username] = [
            (ts, loc) for ts, loc in self._user_locations[username]
            if ts > cutoff
        ]
    
    def check_anomaly(
        self,
        username: str,
        timestamp: datetime,
        location: GeoLocation,
    ) -> Optional[SuspiciousActivity]:
        """
        Check for geographic anomalies.
        
        Returns SuspiciousActivity if anomaly detected, None otherwise.
        """
        # Check high-risk country
        if location.country_code in self.HIGH_RISK_COUNTRIES:
            return SuspiciousActivity(
                activity_id=f"geo-{int(time.time() * 1000)}",
                timestamp=timestamp,
                activity_type="high_risk_country",
                risk_level=RiskLevel.HIGH,
                username=username,
                description=f"Login from high-risk country: {location.country_code}",
                details={
                    "country_code": location.country_code,
                    "city": location.city,
                },
            )
        
        # Check impossible travel
        recent_locations = self._user_locations.get(username, [])
        
        for prev_time, prev_loc in reversed(recent_locations):
            time_diff = (timestamp - prev_time).total_seconds()
            
            if time_diff > self._time_threshold:
                break
            
            if prev_loc.latitude and prev_loc.longitude and location.latitude and location.longitude:
                distance = self._haversine_distance(
                    prev_loc.latitude, prev_loc.longitude,
                    location.latitude, location.longitude,
                )
                
                speed = distance / (time_diff / 3600)  # km/h
                
                if speed > self._max_speed:
                    return SuspiciousActivity(
                        activity_id=f"geo-{int(time.time() * 1000)}",
                        timestamp=timestamp,
                        activity_type="impossible_travel",
                        risk_level=RiskLevel.CRITICAL,
                        username=username,
                        description=f"Impossible travel: {distance:.0f}km in {time_diff/60:.0f} minutes",
                        details={
                            "distance_km": distance,
                            "time_seconds": time_diff,
                            "calculated_speed_kmh": speed,
                            "max_speed_kmh": self._max_speed,
                            "from_country": prev_loc.country_code,
                            "to_country": location.country_code,
                        },
                    )
        
        # Check new location
        known_countries = {loc.country_code for _, loc in recent_locations}
        if recent_locations and location.country_code not in known_countries:
            return SuspiciousActivity(
                activity_id=f"geo-{int(time.time() * 1000)}",
                timestamp=timestamp,
                activity_type="new_location",
                risk_level=RiskLevel.MEDIUM,
                username=username,
                description=f"Login from new country: {location.country_code}",
                details={
                    "new_country": location.country_code,
                    "known_countries": list(known_countries),
                },
            )
        
        return None
    
    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two coordinates in kilometers."""
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371  # Earth's radius in km
        
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        
        return R * c


# =============================================================================
# Rate Limiter Integration
# =============================================================================

class LoginRateLimiter:
    """
    Rate limiter specifically for login attempts.
    
    Uses sliding window for accurate rate limiting.
    """
    
    def __init__(
        self,
        max_attempts_per_minute: int = 10,
        max_attempts_per_hour: int = 100,
    ):
        self._per_minute = max_attempts_per_minute
        self._per_hour = max_attempts_per_hour
        self._windows: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def check_rate_limit(
        self,
        key: str,
    ) -> Tuple[bool, Optional[int]]:
        """
        Check if request is rate limited.
        
        Returns (is_allowed, retry_after_seconds).
        """
        async with self._lock:
            now = time.time()
            
            # Clean old entries
            minute_ago = now - 60
            hour_ago = now - 3600
            
            self._windows[key] = [t for t in self._windows[key] if t > hour_ago]
            
            # Count requests
            minute_count = sum(1 for t in self._windows[key] if t > minute_ago)
            hour_count = len(self._windows[key])
            
            # Check limits
            if minute_count >= self._per_minute:
                oldest_in_minute = min(t for t in self._windows[key] if t > minute_ago)
                retry_after = int(60 - (now - oldest_in_minute)) + 1
                return False, retry_after
            
            if hour_count >= self._per_hour:
                oldest = min(self._windows[key])
                retry_after = int(3600 - (now - oldest)) + 1
                return False, retry_after
            
            return True, None
    
    async def record_attempt(self, key: str) -> None:
        """Record a login attempt."""
        async with self._lock:
            self._windows[key].append(time.time())


# =============================================================================
# Helper Functions
# =============================================================================

def get_login_tracker() -> FailedLoginTracker:
    """Get the singleton login tracker instance."""
    return FailedLoginTracker.get_instance()


async def check_login_allowed(
    username: str,
    ip_address: str,
    tenant_id: Optional[str] = None,
) -> Tuple[bool, Optional[LockoutStatus]]:
    """
    Quick check if login is allowed.
    
    Returns (is_allowed, lockout_status if locked).
    """
    tracker = get_login_tracker()
    status = await tracker.check_lockout(username, ip_address, tenant_id)
    
    return not status.is_locked, status if status.is_locked else None
