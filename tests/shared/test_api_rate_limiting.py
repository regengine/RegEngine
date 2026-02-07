"""
Tests for SEC-026: API Rate Limiting.

Tests cover:
- Token bucket algorithm
- Sliding window algorithm
- Fixed window algorithm
- Adaptive rate limiting
- Rate limit headers
- Rate limit service
"""

import pytest
import time

from shared.api_rate_limiting import (
    # Enums
    RateLimitAlgorithm,
    RateLimitScope,
    # Exceptions
    RateLimitError,
    RateLimitExceeded,
    # Data classes
    RateLimitConfig,
    RateLimitResult,
    # Classes
    TokenBucketLimiter,
    SlidingWindowLimiter,
    FixedWindowLimiter,
    AdaptiveRateLimiter,
    RateLimitService,
    # Convenience functions
    get_rate_limit_service,
    check_rate_limit,
    consume_rate_limit,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def token_bucket():
    """Create token bucket limiter."""
    return TokenBucketLimiter(rate=10.0, capacity=20)


@pytest.fixture
def sliding_window():
    """Create sliding window limiter."""
    return SlidingWindowLimiter(limit=10, window_seconds=1.0)


@pytest.fixture
def fixed_window():
    """Create fixed window limiter."""
    return FixedWindowLimiter(limit=10, window_seconds=1.0)


@pytest.fixture
def service():
    """Create rate limit service."""
    return RateLimitService()


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_algorithms(self):
        """Should have expected algorithms."""
        assert RateLimitAlgorithm.TOKEN_BUCKET == "token_bucket"
        assert RateLimitAlgorithm.SLIDING_WINDOW == "sliding_window"
        assert RateLimitAlgorithm.FIXED_WINDOW == "fixed_window"
    
    def test_scopes(self):
        """Should have expected scopes."""
        assert RateLimitScope.GLOBAL == "global"
        assert RateLimitScope.USER == "user"
        assert RateLimitScope.IP == "ip"
        assert RateLimitScope.ENDPOINT == "endpoint"


# =============================================================================
# Test: Data Classes
# =============================================================================

class TestDataClasses:
    """Test data class functionality."""
    
    def test_config_defaults(self):
        """Should have secure defaults."""
        config = RateLimitConfig()
        
        assert config.requests_per_second > 0
        assert config.burst_size > 0
        assert config.enabled is True
    
    def test_result_to_headers(self):
        """Should convert to HTTP headers."""
        result = RateLimitResult(
            allowed=True,
            limit=100,
            remaining=50,
            reset_at=time.time() + 60,
        )
        
        headers = result.to_headers()
        
        assert "X-RateLimit-Limit" in headers
        assert "X-RateLimit-Remaining" in headers
        assert "X-RateLimit-Reset" in headers
    
    def test_result_headers_retry_after(self):
        """Should include Retry-After when blocked."""
        result = RateLimitResult(
            allowed=False,
            limit=100,
            remaining=0,
            reset_at=time.time() + 60,
            retry_after=30.0,
        )
        
        headers = result.to_headers()
        
        assert "Retry-After" in headers


# =============================================================================
# Test: Token Bucket Limiter
# =============================================================================

class TestTokenBucketLimiter:
    """Test TokenBucketLimiter."""
    
    def test_allows_initial_requests(self, token_bucket):
        """Should allow initial requests up to capacity."""
        key = "user1"
        
        for i in range(20):
            result = token_bucket.consume(key)
            assert result.allowed is True
    
    def test_blocks_after_capacity(self, token_bucket):
        """Should block after capacity exhausted."""
        key = "user1"
        
        # Exhaust capacity
        for _ in range(20):
            token_bucket.consume(key)
        
        # Next request should be blocked
        result = token_bucket.consume(key)
        assert result.allowed is False
    
    def test_refills_over_time(self, token_bucket):
        """Should refill tokens over time."""
        key = "user1"
        
        # Exhaust some capacity
        for _ in range(15):
            token_bucket.consume(key)
        
        # Wait for refill (0.5s at 10/s = 5 tokens)
        time.sleep(0.5)
        
        result = token_bucket.check(key)
        assert result.remaining >= 5
    
    def test_check_doesnt_consume(self, token_bucket):
        """Check should not consume tokens."""
        key = "user1"
        
        result1 = token_bucket.check(key)
        result2 = token_bucket.check(key)
        
        assert result1.remaining == result2.remaining
    
    def test_reset(self, token_bucket):
        """Should reset bucket."""
        key = "user1"
        
        # Exhaust capacity
        for _ in range(20):
            token_bucket.consume(key)
        
        # Reset
        token_bucket.reset(key)
        
        # Should be allowed again
        result = token_bucket.consume(key)
        assert result.allowed is True
    
    def test_different_keys_independent(self, token_bucket):
        """Different keys should be independent."""
        key1 = "user1"
        key2 = "user2"
        
        # Exhaust key1
        for _ in range(20):
            token_bucket.consume(key1)
        
        # key2 should still work
        result = token_bucket.consume(key2)
        assert result.allowed is True


# =============================================================================
# Test: Sliding Window Limiter
# =============================================================================

class TestSlidingWindowLimiter:
    """Test SlidingWindowLimiter."""
    
    def test_allows_within_limit(self, sliding_window):
        """Should allow requests within limit."""
        key = "user1"
        
        for i in range(10):
            result = sliding_window.consume(key)
            assert result.allowed is True
    
    def test_blocks_over_limit(self, sliding_window):
        """Should block over limit."""
        key = "user1"
        
        # Hit limit
        for _ in range(10):
            sliding_window.consume(key)
        
        result = sliding_window.consume(key)
        assert result.allowed is False
    
    def test_window_slides(self, sliding_window):
        """Should allow after window slides."""
        key = "user1"
        
        # Hit limit
        for _ in range(10):
            sliding_window.consume(key)
        
        # Wait for window to slide
        time.sleep(1.1)
        
        result = sliding_window.consume(key)
        assert result.allowed is True
    
    def test_remaining_count(self, sliding_window):
        """Should track remaining count."""
        key = "user1"
        
        for i in range(5):
            result = sliding_window.consume(key)
            assert result.remaining == 10 - (i + 1)


# =============================================================================
# Test: Fixed Window Limiter
# =============================================================================

class TestFixedWindowLimiter:
    """Test FixedWindowLimiter."""
    
    def test_allows_within_limit(self, fixed_window):
        """Should allow requests within limit."""
        key = "user1"
        
        for _ in range(10):
            result = fixed_window.consume(key)
            assert result.allowed is True
    
    def test_blocks_over_limit(self, fixed_window):
        """Should block over limit."""
        key = "user1"
        
        # Hit limit
        for _ in range(10):
            fixed_window.consume(key)
        
        result = fixed_window.consume(key)
        assert result.allowed is False
    
    def test_resets_in_new_window(self, fixed_window):
        """Should reset in new window."""
        key = "user1"
        
        # Hit limit
        for _ in range(10):
            fixed_window.consume(key)
        
        # Wait for new window
        time.sleep(1.1)
        
        result = fixed_window.consume(key)
        assert result.allowed is True


# =============================================================================
# Test: Adaptive Rate Limiter
# =============================================================================

class TestAdaptiveRateLimiter:
    """Test AdaptiveRateLimiter."""
    
    def test_initial_limit(self):
        """Should use base limit initially."""
        limiter = AdaptiveRateLimiter(base_limit=100)
        
        stats = limiter.get_client_stats("user1")
        assert stats["current_limit"] == 100
    
    def test_tracks_violations(self):
        """Should track violations when requests are denied."""
        # Create with small limit that won't auto-increase
        limiter = AdaptiveRateLimiter(
            base_limit=5,
            window_seconds=60.0,
            min_limit=1,
            max_limit=5,  # Prevent increase
            adjustment_factor=0.5,
        )
        
        key = "user1"
        
        # Consume all allowed requests (5)
        allowed_count = 0
        denied_count = 0
        
        for _ in range(10):
            result = limiter.consume(key)
            if result.allowed:
                allowed_count += 1
            else:
                denied_count += 1
        
        # Should have allowed 5 and denied at least some
        assert allowed_count == 5
        assert denied_count >= 1
        
        stats = limiter.get_client_stats(key)
        assert stats["violations"] >= 1
    
    def test_respects_min_limit(self):
        """Should not go below min limit."""
        limiter = AdaptiveRateLimiter(
            base_limit=10,
            window_seconds=0.1,
            min_limit=5,
        )
        
        key = "user1"
        
        # Many violations
        for _ in range(100):
            limiter.consume(key)
        
        stats = limiter.get_client_stats(key)
        assert stats["current_limit"] >= 5


# =============================================================================
# Test: Rate Limit Service
# =============================================================================

class TestRateLimitService:
    """Test RateLimitService."""
    
    def test_check_rate_limit(self, service):
        """Should check rate limit."""
        result = service.check("user1")
        
        assert result.allowed is True
    
    def test_consume_rate_limit(self, service):
        """Should consume rate limit."""
        result = service.consume("user1")
        
        assert result.allowed is True
    
    def test_different_scopes(self, service):
        """Should handle different scopes."""
        result1 = service.consume("user1", scope=RateLimitScope.USER)
        result2 = service.consume("192.168.1.1", scope=RateLimitScope.IP)
        
        assert result1.allowed is True
        assert result2.allowed is True
    
    def test_endpoint_config(self, service):
        """Should support endpoint-specific config."""
        # Strict limit for sensitive endpoint
        config = RateLimitConfig(
            requests_per_second=1.0,
            burst_size=2,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
        )
        
        service.set_endpoint_config("/api/admin", config)
        
        # Should allow 2 requests
        for _ in range(2):
            result = service.consume("user1", endpoint="/api/admin")
            assert result.allowed is True
        
        # Third should be blocked
        result = service.consume("user1", endpoint="/api/admin")
        assert result.allowed is False
    
    def test_reset(self, service):
        """Should reset rate limit."""
        # Hit limit
        config = RateLimitConfig(burst_size=2)
        service._limiters = {}  # Clear
        service.default_config = config
        
        service.consume("user1")
        service.consume("user1")
        
        result = service.consume("user1")
        assert result.allowed is False
        
        # Reset
        service.reset("user1")
        
        # Should allow again
        result = service.consume("user1")
        assert result.allowed is True
    
    def test_disabled_config(self, service):
        """Should allow all when disabled."""
        config = RateLimitConfig(enabled=False)
        service.default_config = config
        service._limiters = {}
        
        for _ in range(1000):
            result = service.consume("user1")
            assert result.allowed is True


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_get_rate_limit_service(self):
        """Should return service instance."""
        service = get_rate_limit_service()
        assert service is not None
    
    def test_check_rate_limit_function(self):
        """Should check via convenience function."""
        result = check_rate_limit("test_user")
        assert isinstance(result, RateLimitResult)
    
    def test_consume_rate_limit_function(self):
        """Should consume via convenience function."""
        result = consume_rate_limit("test_user")
        assert isinstance(result, RateLimitResult)
