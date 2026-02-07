"""
SEC-026: API Rate Limiting.

Provides comprehensive rate limiting for API protection:
- Token bucket algorithm
- Sliding window algorithm
- Fixed window algorithm
- Per-user/IP/endpoint limits
- Adaptive rate limiting
- Rate limit headers
"""

import asyncio
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Callable

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class RateLimitError(Exception):
    """Base exception for rate limiting."""
    pass


class RateLimitExceeded(RateLimitError):
    """Raised when rate limit is exceeded."""
    
    def __init__(
        self,
        message: str,
        limit: int,
        remaining: int,
        reset_at: float,
        retry_after: float,
    ):
        super().__init__(message)
        self.limit = limit
        self.remaining = remaining
        self.reset_at = reset_at
        self.retry_after = retry_after


# =============================================================================
# Enums
# =============================================================================

class RateLimitAlgorithm(str, Enum):
    """Rate limiting algorithms."""
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"
    LEAKY_BUCKET = "leaky_bucket"


class RateLimitScope(str, Enum):
    """Scope for rate limiting."""
    GLOBAL = "global"
    USER = "user"
    IP = "ip"
    ENDPOINT = "endpoint"
    API_KEY = "api_key"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    requests_per_second: float = 10.0
    requests_per_minute: float = 100.0
    requests_per_hour: float = 1000.0
    burst_size: int = 20
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.TOKEN_BUCKET
    scope: RateLimitScope = RateLimitScope.USER
    enabled: bool = True


@dataclass
class RateLimitResult:
    """Result of rate limit check."""
    allowed: bool
    limit: int
    remaining: int
    reset_at: float  # Unix timestamp
    retry_after: float = 0.0  # Seconds until retry allowed
    
    def to_headers(self) -> Dict[str, str]:
        """Convert to HTTP headers."""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(int(self.reset_at)),
        }
        if not self.allowed:
            headers["Retry-After"] = str(int(self.retry_after) + 1)
        return headers


@dataclass
class RateLimitState:
    """State for a rate limiter."""
    tokens: float = 0.0
    last_update: float = 0.0
    request_count: int = 0
    window_start: float = 0.0
    requests: List[float] = field(default_factory=list)


# =============================================================================
# Rate Limiter Interface
# =============================================================================

class RateLimiter(ABC):
    """Abstract base class for rate limiters."""
    
    @abstractmethod
    def check(self, key: str) -> RateLimitResult:
        """Check if request is allowed."""
        pass
    
    @abstractmethod
    def consume(self, key: str, tokens: int = 1) -> RateLimitResult:
        """Consume tokens and return result."""
        pass
    
    @abstractmethod
    def reset(self, key: str) -> None:
        """Reset rate limit for key."""
        pass


# =============================================================================
# Token Bucket Rate Limiter
# =============================================================================

class TokenBucketLimiter(RateLimiter):
    """
    Token bucket rate limiter.
    
    Tokens are added at a constant rate up to a maximum (bucket size).
    Each request consumes one token.
    """
    
    def __init__(
        self,
        rate: float = 10.0,  # Tokens per second
        capacity: int = 20,  # Maximum tokens
    ):
        """
        Initialize token bucket.
        
        Args:
            rate: Token refill rate per second
            capacity: Maximum bucket capacity
        """
        self.rate = rate
        self.capacity = capacity
        self._buckets: Dict[str, RateLimitState] = {}
        self._lock = asyncio.Lock() if asyncio.get_event_loop().is_running() else None
    
    def _get_state(self, key: str) -> RateLimitState:
        """Get or create state for key."""
        if key not in self._buckets:
            self._buckets[key] = RateLimitState(
                tokens=float(self.capacity),
                last_update=time.time(),
            )
        return self._buckets[key]
    
    def _refill(self, state: RateLimitState) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - state.last_update
        
        # Add tokens based on elapsed time
        tokens_to_add = elapsed * self.rate
        state.tokens = min(self.capacity, state.tokens + tokens_to_add)
        state.last_update = now
    
    def check(self, key: str) -> RateLimitResult:
        """Check if request would be allowed."""
        state = self._get_state(key)
        self._refill(state)
        
        allowed = state.tokens >= 1.0
        remaining = int(state.tokens)
        
        # Calculate reset time (when bucket would be full)
        tokens_needed = self.capacity - state.tokens
        reset_at = time.time() + (tokens_needed / self.rate if self.rate > 0 else 0)
        
        # Calculate retry after (when at least 1 token available)
        retry_after = 0.0
        if not allowed:
            retry_after = (1.0 - state.tokens) / self.rate if self.rate > 0 else 1.0
        
        return RateLimitResult(
            allowed=allowed,
            limit=self.capacity,
            remaining=remaining,
            reset_at=reset_at,
            retry_after=retry_after,
        )
    
    def consume(self, key: str, tokens: int = 1) -> RateLimitResult:
        """Consume tokens and return result."""
        state = self._get_state(key)
        self._refill(state)
        
        if state.tokens >= tokens:
            state.tokens -= tokens
            allowed = True
        else:
            allowed = False
        
        remaining = int(state.tokens)
        tokens_needed = self.capacity - state.tokens
        reset_at = time.time() + (tokens_needed / self.rate if self.rate > 0 else 0)
        
        retry_after = 0.0
        if not allowed:
            retry_after = (tokens - state.tokens) / self.rate if self.rate > 0 else 1.0
        
        return RateLimitResult(
            allowed=allowed,
            limit=self.capacity,
            remaining=remaining,
            reset_at=reset_at,
            retry_after=retry_after,
        )
    
    def reset(self, key: str) -> None:
        """Reset bucket for key."""
        if key in self._buckets:
            del self._buckets[key]


# =============================================================================
# Sliding Window Rate Limiter
# =============================================================================

class SlidingWindowLimiter(RateLimiter):
    """
    Sliding window rate limiter.
    
    Tracks individual request timestamps and counts requests
    within a sliding time window.
    """
    
    def __init__(
        self,
        limit: int = 100,
        window_seconds: float = 60.0,
    ):
        """
        Initialize sliding window.
        
        Args:
            limit: Maximum requests per window
            window_seconds: Window duration in seconds
        """
        self.limit = limit
        self.window_seconds = window_seconds
        self._windows: Dict[str, RateLimitState] = {}
    
    def _get_state(self, key: str) -> RateLimitState:
        """Get or create state for key."""
        if key not in self._windows:
            self._windows[key] = RateLimitState(requests=[])
        return self._windows[key]
    
    def _cleanup(self, state: RateLimitState) -> None:
        """Remove expired requests from window."""
        now = time.time()
        cutoff = now - self.window_seconds
        state.requests = [ts for ts in state.requests if ts > cutoff]
    
    def check(self, key: str) -> RateLimitResult:
        """Check if request would be allowed."""
        state = self._get_state(key)
        self._cleanup(state)
        
        current_count = len(state.requests)
        allowed = current_count < self.limit
        remaining = self.limit - current_count
        
        # Reset is when oldest request expires
        if state.requests:
            reset_at = state.requests[0] + self.window_seconds
        else:
            reset_at = time.time() + self.window_seconds
        
        retry_after = 0.0
        if not allowed and state.requests:
            retry_after = state.requests[0] + self.window_seconds - time.time()
        
        return RateLimitResult(
            allowed=allowed,
            limit=self.limit,
            remaining=max(0, remaining),
            reset_at=reset_at,
            retry_after=max(0, retry_after),
        )
    
    def consume(self, key: str, tokens: int = 1) -> RateLimitResult:
        """Record request and return result."""
        state = self._get_state(key)
        self._cleanup(state)
        
        current_count = len(state.requests)
        
        if current_count < self.limit:
            state.requests.append(time.time())
            allowed = True
            remaining = self.limit - current_count - 1
        else:
            allowed = False
            remaining = 0
        
        if state.requests:
            reset_at = state.requests[0] + self.window_seconds
        else:
            reset_at = time.time() + self.window_seconds
        
        retry_after = 0.0
        if not allowed and state.requests:
            retry_after = state.requests[0] + self.window_seconds - time.time()
        
        return RateLimitResult(
            allowed=allowed,
            limit=self.limit,
            remaining=max(0, remaining),
            reset_at=reset_at,
            retry_after=max(0, retry_after),
        )
    
    def reset(self, key: str) -> None:
        """Reset window for key."""
        if key in self._windows:
            del self._windows[key]


# =============================================================================
# Fixed Window Rate Limiter
# =============================================================================

class FixedWindowLimiter(RateLimiter):
    """
    Fixed window rate limiter.
    
    Counts requests within fixed time windows (e.g., per minute).
    Simple but can allow burst at window boundaries.
    """
    
    def __init__(
        self,
        limit: int = 100,
        window_seconds: float = 60.0,
    ):
        """
        Initialize fixed window.
        
        Args:
            limit: Maximum requests per window
            window_seconds: Window duration in seconds
        """
        self.limit = limit
        self.window_seconds = window_seconds
        self._windows: Dict[str, RateLimitState] = {}
    
    def _get_window_start(self) -> float:
        """Get start of current window."""
        now = time.time()
        return now - (now % self.window_seconds)
    
    def _get_state(self, key: str) -> RateLimitState:
        """Get or create state for key."""
        window_start = self._get_window_start()
        
        if key not in self._windows:
            self._windows[key] = RateLimitState(
                request_count=0,
                window_start=window_start,
            )
        
        state = self._windows[key]
        
        # Reset if we're in a new window
        if state.window_start != window_start:
            state.request_count = 0
            state.window_start = window_start
        
        return state
    
    def check(self, key: str) -> RateLimitResult:
        """Check if request would be allowed."""
        state = self._get_state(key)
        
        allowed = state.request_count < self.limit
        remaining = self.limit - state.request_count
        reset_at = state.window_start + self.window_seconds
        
        retry_after = 0.0
        if not allowed:
            retry_after = reset_at - time.time()
        
        return RateLimitResult(
            allowed=allowed,
            limit=self.limit,
            remaining=max(0, remaining),
            reset_at=reset_at,
            retry_after=max(0, retry_after),
        )
    
    def consume(self, key: str, tokens: int = 1) -> RateLimitResult:
        """Record request and return result."""
        state = self._get_state(key)
        
        if state.request_count < self.limit:
            state.request_count += 1
            allowed = True
            remaining = self.limit - state.request_count
        else:
            allowed = False
            remaining = 0
        
        reset_at = state.window_start + self.window_seconds
        
        retry_after = 0.0
        if not allowed:
            retry_after = reset_at - time.time()
        
        return RateLimitResult(
            allowed=allowed,
            limit=self.limit,
            remaining=max(0, remaining),
            reset_at=reset_at,
            retry_after=max(0, retry_after),
        )
    
    def reset(self, key: str) -> None:
        """Reset window for key."""
        if key in self._windows:
            del self._windows[key]


# =============================================================================
# Adaptive Rate Limiter
# =============================================================================

class AdaptiveRateLimiter(RateLimiter):
    """
    Adaptive rate limiter that adjusts limits based on behavior.
    
    Features:
    - Increases limits for well-behaved clients
    - Decreases limits for abusive clients
    - Tracks violation history
    """
    
    def __init__(
        self,
        base_limit: int = 100,
        window_seconds: float = 60.0,
        min_limit: int = 10,
        max_limit: int = 500,
        adjustment_factor: float = 0.1,
    ):
        """
        Initialize adaptive limiter.
        
        Args:
            base_limit: Starting limit
            window_seconds: Window duration
            min_limit: Minimum allowed limit
            max_limit: Maximum allowed limit
            adjustment_factor: Rate of adjustment
        """
        self.base_limit = base_limit
        self.window_seconds = window_seconds
        self.min_limit = min_limit
        self.max_limit = max_limit
        self.adjustment_factor = adjustment_factor
        
        self._client_limits: Dict[str, int] = {}
        self._violation_counts: Dict[str, int] = {}
        self._inner_limiter = SlidingWindowLimiter(base_limit, window_seconds)
    
    def _get_limit(self, key: str) -> int:
        """Get current limit for key."""
        return self._client_limits.get(key, self.base_limit)
    
    def _adjust_limit(self, key: str, violated: bool) -> None:
        """Adjust limit based on behavior."""
        current = self._get_limit(key)
        
        if violated:
            # Decrease limit on violation
            self._violation_counts[key] = self._violation_counts.get(key, 0) + 1
            violations = self._violation_counts[key]
            
            # More aggressive decrease with more violations
            decrease = int(current * self.adjustment_factor * min(violations, 5))
            new_limit = max(self.min_limit, current - decrease)
        else:
            # Slowly increase limit for good behavior
            increase = int(current * self.adjustment_factor * 0.1)
            new_limit = min(self.max_limit, current + max(1, increase))
            
            # Reset violation count on sustained good behavior
            if new_limit > current:
                self._violation_counts[key] = max(
                    0, 
                    self._violation_counts.get(key, 0) - 1
                )
        
        self._client_limits[key] = new_limit
    
    def check(self, key: str) -> RateLimitResult:
        """Check if request would be allowed."""
        limit = self._get_limit(key)
        
        # Create limiter with current limit
        limiter = SlidingWindowLimiter(limit, self.window_seconds)
        limiter._windows = self._inner_limiter._windows
        
        return limiter.check(key)
    
    def consume(self, key: str, tokens: int = 1) -> RateLimitResult:
        """Record request and return result."""
        limit = self._get_limit(key)
        
        # Create limiter with current limit
        limiter = SlidingWindowLimiter(limit, self.window_seconds)
        limiter._windows = self._inner_limiter._windows
        
        result = limiter.consume(key, tokens)
        
        # Update shared state
        self._inner_limiter._windows = limiter._windows
        
        # Adjust limit based on result
        self._adjust_limit(key, not result.allowed)
        
        # Update result with adjusted limit
        result.limit = self._get_limit(key)
        
        return result
    
    def reset(self, key: str) -> None:
        """Reset limiter for key."""
        self._inner_limiter.reset(key)
        if key in self._client_limits:
            del self._client_limits[key]
        if key in self._violation_counts:
            del self._violation_counts[key]
    
    def get_client_stats(self, key: str) -> Dict[str, Any]:
        """Get statistics for a client."""
        return {
            "current_limit": self._get_limit(key),
            "violations": self._violation_counts.get(key, 0),
            "base_limit": self.base_limit,
        }


# =============================================================================
# Rate Limit Service
# =============================================================================

class RateLimitService:
    """
    High-level rate limiting service.
    
    Provides:
    - Multiple rate limit tiers
    - Composite key generation
    - Endpoint-specific limits
    """
    
    _instance: Optional["RateLimitService"] = None
    
    def __init__(
        self,
        default_config: Optional[RateLimitConfig] = None,
    ):
        """Initialize service."""
        self.default_config = default_config or RateLimitConfig()
        self._limiters: Dict[str, RateLimiter] = {}
        self._endpoint_configs: Dict[str, RateLimitConfig] = {}
    
    @classmethod
    def get_instance(cls) -> "RateLimitService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(
        cls,
        default_config: Optional[RateLimitConfig] = None,
    ) -> "RateLimitService":
        """Configure the service."""
        cls._instance = cls(default_config)
        return cls._instance
    
    def _create_limiter(self, config: RateLimitConfig) -> RateLimiter:
        """Create rate limiter from config."""
        if config.algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
            return TokenBucketLimiter(
                rate=config.requests_per_second,
                capacity=config.burst_size,
            )
        elif config.algorithm == RateLimitAlgorithm.SLIDING_WINDOW:
            return SlidingWindowLimiter(
                limit=int(config.requests_per_minute),
                window_seconds=60.0,
            )
        elif config.algorithm == RateLimitAlgorithm.FIXED_WINDOW:
            return FixedWindowLimiter(
                limit=int(config.requests_per_minute),
                window_seconds=60.0,
            )
        else:
            return TokenBucketLimiter(
                rate=config.requests_per_second,
                capacity=config.burst_size,
            )
    
    def _get_key(
        self,
        scope: RateLimitScope,
        identifier: str,
        endpoint: Optional[str] = None,
    ) -> str:
        """Generate rate limit key."""
        parts = [scope.value, identifier]
        if endpoint:
            parts.append(endpoint)
        return ":".join(parts)
    
    def set_endpoint_config(
        self,
        endpoint: str,
        config: RateLimitConfig,
    ) -> None:
        """Set rate limit config for endpoint."""
        self._endpoint_configs[endpoint] = config
    
    def check(
        self,
        identifier: str,
        scope: RateLimitScope = RateLimitScope.USER,
        endpoint: Optional[str] = None,
    ) -> RateLimitResult:
        """Check rate limit."""
        # Get config
        config = self._endpoint_configs.get(endpoint, self.default_config)
        
        if not config.enabled:
            return RateLimitResult(
                allowed=True,
                limit=0,
                remaining=0,
                reset_at=0,
            )
        
        # Get or create limiter
        key = self._get_key(scope, identifier, endpoint)
        
        if key not in self._limiters:
            self._limiters[key] = self._create_limiter(config)
        
        return self._limiters[key].check(key)
    
    def consume(
        self,
        identifier: str,
        scope: RateLimitScope = RateLimitScope.USER,
        endpoint: Optional[str] = None,
        tokens: int = 1,
    ) -> RateLimitResult:
        """Consume rate limit tokens."""
        # Get config
        config = self._endpoint_configs.get(endpoint, self.default_config)
        
        if not config.enabled:
            return RateLimitResult(
                allowed=True,
                limit=0,
                remaining=0,
                reset_at=0,
            )
        
        # Get or create limiter
        key = self._get_key(scope, identifier, endpoint)
        
        if key not in self._limiters:
            self._limiters[key] = self._create_limiter(config)
        
        result = self._limiters[key].consume(key, tokens)
        
        if not result.allowed:
            logger.warning(
                f"Rate limit exceeded for {scope.value}:{identifier}",
                extra={
                    "scope": scope.value,
                    "identifier": identifier,
                    "endpoint": endpoint,
                    "limit": result.limit,
                    "remaining": result.remaining,
                },
            )
        
        return result
    
    def reset(
        self,
        identifier: str,
        scope: RateLimitScope = RateLimitScope.USER,
        endpoint: Optional[str] = None,
    ) -> None:
        """Reset rate limit."""
        key = self._get_key(scope, identifier, endpoint)
        
        if key in self._limiters:
            self._limiters[key].reset(key)


# =============================================================================
# Convenience Functions
# =============================================================================

def get_rate_limit_service() -> RateLimitService:
    """Get the global rate limit service."""
    return RateLimitService.get_instance()


def check_rate_limit(
    identifier: str,
    scope: RateLimitScope = RateLimitScope.USER,
    endpoint: Optional[str] = None,
) -> RateLimitResult:
    """Check rate limit."""
    return get_rate_limit_service().check(identifier, scope, endpoint)


def consume_rate_limit(
    identifier: str,
    scope: RateLimitScope = RateLimitScope.USER,
    endpoint: Optional[str] = None,
) -> RateLimitResult:
    """Consume rate limit."""
    return get_rate_limit_service().consume(identifier, scope, endpoint)
