"""Rate limiting utilities for HTTP requests."""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional


@dataclass
class RateLimiter:
    """
    Token bucket rate limiter with exponential backoff support.
    
    Supports per-domain rate limiting with configurable limits.
    """
    
    requests_per_minute: int = 60
    max_retries: int = 3
    exponential_backoff: bool = True
    
    # Internal state
    _buckets: Dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _retry_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _last_request: Dict[str, datetime] = field(default_factory=dict)
    
    def wait_if_needed(self, domain: str) -> None:
        """
        Wait if rate limit would be exceeded for this domain.
        
        Args:
            domain: Domain name to check
        """
        now = time.time()
       
        min_interval = 60.0 / self.requests_per_minute
        
        if domain in self._last_request:
            elapsed = now - self._buckets[domain]
            if elapsed < min_interval:
                sleep_time = min_interval - elapsed
                time.sleep(sleep_time)
        
        self._buckets[domain] = time.time()
        self._last_request[domain] = datetime.now(timezone.utc)
    
    def record_error(self, domain: str) -> Optional[float]:
        """
        Record an error and calculate backoff time.
        
        Args:
            domain: Domain that returned an error
            
        Returns:
            Backoff time in seconds, or None if max retries exceeded
        """
        self._retry_counts[domain] += 1
        
        if self._retry_counts[domain] > self.max_retries:
            return None
        
        if self.exponential_backoff:
            # Exponential: 1, 2, 4, 8, ...
            backoff = 2 ** (self._retry_counts[domain] - 1)
        else:
            # Linear: 1, 2, 3, 4, ...
            backoff = self._retry_counts[domain]
        
        return float(backoff)
    
    def record_success(self, domain: str) -> None:
        """
        Record a successful request and reset retry counter.
        
        Args:
            domain: Domain that succeeded
        """
        self._retry_counts[domain] = 0
    
    def respect_retry_after(self, retry_after: str) -> None:
        """
        Sleep for time specified in Retry-After header.
        
        Args:
            retry_after: Value from Retry-After header (seconds or HTTP date)
        """
        try:
            # Try as integer seconds
            seconds = int(retry_after)
            time.sleep(seconds)
        except ValueError:
            # Try as HTTP date
            try:
                retry_time = datetime.strptime(retry_after, "%a, %d %b %Y %H:%M:%S GMT")
                wait_seconds = (retry_time - datetime.now(timezone.utc)).total_seconds()
                if wait_seconds > 0:
                    time.sleep(wait_seconds)
            except ValueError:
                # Invalid format, ignore
                pass
