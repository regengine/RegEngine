"""Redis-backed rate limiter for distributed deployments.

Replaces in-memory rate limiting to support multi-instance deployments.
Addresses Gap Analysis finding on rate limiter storage.
"""

from __future__ import annotations

import time
from typing import Optional

import structlog

logger = structlog.get_logger("rate_limit")


class RedisRateLimiter:
    """Distributed rate limiter using Redis sliding window.
    
    Usage:
        limiter = RedisRateLimiter(redis_url="redis://localhost:6379/0")
        
        # In request handler:
        allowed, remaining, reset_at = await limiter.check("api_key_123", limit=100)
        if not allowed:
            raise HTTPException(429, "Rate limit exceeded")
    """
    
    def __init__(self, redis_url: str):
        """Initialize Redis rate limiter.
        
        Args:
            redis_url: Redis connection URL
        """
        self.redis_url = redis_url
        self._client = None
    
    async def _get_client(self):
        """Lazy initialize Redis client."""
        if self._client is None:
            import redis.asyncio as redis
            self._client = redis.from_url(self.redis_url)
        return self._client
    
    async def check(
        self,
        key: str,
        limit: int = 60,
        window_seconds: int = 60,
    ) -> tuple[bool, int, int]:
        """Check if request is within rate limit.
        
        Uses sliding window counter algorithm for accurate limiting.
        
        Args:
            key: Unique identifier (e.g., API key ID)
            limit: Maximum requests per window
            window_seconds: Window size in seconds
            
        Returns:
            Tuple of (allowed, remaining, reset_timestamp)
        """
        client = await self._get_client()
        
        now = time.time()
        window_start = now - window_seconds
        redis_key = f"rate_limit:{key}"
        
        pipe = client.pipeline()
        
        # Remove old entries outside the window
        pipe.zremrangebyscore(redis_key, 0, window_start)
        
        # Count current requests in window
        pipe.zcard(redis_key)
        
        # Add current request with timestamp as score
        pipe.zadd(redis_key, {str(now): now})
        
        # Set expiry on the key
        pipe.expire(redis_key, window_seconds)
        
        results = await pipe.execute()
        current_count = results[1]
        
        # Check if over limit (count BEFORE adding this request)
        allowed = current_count < limit
        remaining = max(0, limit - current_count - 1) if allowed else 0
        reset_at = int(now + window_seconds)
        
        if not allowed:
            # Remove the request we just added since it's denied
            await client.zrem(redis_key, str(now))
            logger.warning(
                "rate_limit_exceeded",
                key=key[:16] + "...",  # Truncate for logs
                limit=limit,
                current=current_count,
            )
        
        return allowed, remaining, reset_at
    
    async def get_usage(self, key: str, window_seconds: int = 60) -> int:
        """Get current usage count for a key.
        
        Args:
            key: Unique identifier
            window_seconds: Window size in seconds
            
        Returns:
            Current request count in window
        """
        client = await self._get_client()
        
        now = time.time()
        window_start = now - window_seconds
        redis_key = f"rate_limit:{key}"
        
        # Remove old entries and count
        await client.zremrangebyscore(redis_key, 0, window_start)
        return await client.zcard(redis_key)
    
    async def reset(self, key: str) -> None:
        """Reset rate limit counter for a key.
        
        Args:
            key: Unique identifier to reset
        """
        client = await self._get_client()
        redis_key = f"rate_limit:{key}"
        await client.delete(redis_key)
        logger.info("rate_limit_reset", key=key[:16] + "...")
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None


# Singleton for easy import
_limiter: Optional[RedisRateLimiter] = None


def get_rate_limiter(redis_url: str = "redis://localhost:6379/0") -> RedisRateLimiter:
    """Get or create the global rate limiter instance.
    
    Args:
        redis_url: Redis connection URL
        
    Returns:
        RedisRateLimiter instance
    """
    global _limiter
    if _limiter is None:
        _limiter = RedisRateLimiter(redis_url)
    return _limiter
