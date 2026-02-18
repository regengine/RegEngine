"""
Retry and Circuit Breaker Logic

Handles transient failures with exponential backoff.
"""
import time
import logging
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Any

from sqlalchemy.exc import OperationalError, IntegrityError


logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for database operations.
    
    Prevents cascade failures by stopping requests
    when error rate exceeds threshold.
    """
    failure_threshold: int = 5
    timeout_seconds: int = 30
    
    def __post_init__(self):
        self.failure_count = 0
        self.last_failure_time: datetime | None = None
        self.state = CircuitState.CLOSED
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Raises CircuitBreakerOpen if circuit is open.
        """
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitBreakerOpen(
                    f"Circuit breaker open. Retry after {self.timeout_seconds}s"
                )
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        
        except (OperationalError, IntegrityError) as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        """Reset failure count on success."""
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
    
    def _on_failure(self):
        """Increment failure count and open circuit if threshold exceeded."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.error(
                "circuit_breaker_opened",
                extra={
                    "failure_count": self.failure_count,
                    "timeout_seconds": self.timeout_seconds
                }
            )
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if not self.last_failure_time:
            return True
        
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        return elapsed >= self.timeout_seconds


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""
    pass


def retry_with_backoff(
    func: Callable,
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (OperationalError,)
) -> Any:
    """
    Retry function with exponential backoff.
    
    Args:
        func: Function to retry
        max_attempts: Maximum retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for each retry
        exceptions: Tuple of exceptions to catch
        
    Returns:
        Function result if successful
        
    Raises:
        Last exception if all retries exhausted
    """
    last_exception = None
    delay = initial_delay
    
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        
        except exceptions as e:
            last_exception = e
            
            if attempt == max_attempts:
                logger.error(
                    "retry_exhausted",
                    extra={
                        "attempts": max_attempts,
                        "error": str(e)
                    }
                )
                raise
            
            logger.warning(
                "retry_attempt",
                extra={
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "delay_seconds": delay,
                    "error": str(e)
                }
            )
            
            time.sleep(delay)
            delay *= backoff_factor
    
    # Should never reach here
    raise last_exception
