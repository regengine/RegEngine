"""Circuit breaker pattern for resilient scraping.

Implements the circuit breaker pattern to prevent cascading failures
when external services (FDA, etc.) become unavailable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, Optional

import structlog

logger = structlog.get_logger("circuit_breaker")


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitStats:
    """Statistics for a circuit breaker."""

    failures: int = 0
    successes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    total_calls: int = 0
    rejected_calls: int = 0


@dataclass
class CircuitBreaker:
    """Circuit breaker implementation.

    Usage:
        breaker = CircuitBreaker(name="fda_scraper")

        @breaker.protect
        def scrape_fda():
            ...

        # Or manually:
        if breaker.can_execute():
            try:
                result = scrape_fda()
                breaker.record_success()
            except Exception as e:
                breaker.record_failure()
                raise
    """

    name: str
    failure_threshold: int = 5
    recovery_timeout: int = 300  # seconds
    half_open_max_calls: int = 3

    state: CircuitState = field(default=CircuitState.CLOSED)
    stats: CircuitStats = field(default_factory=CircuitStats)
    _opened_at: Optional[float] = field(default=None, repr=False)
    _half_open_calls: int = field(default=0, repr=False)

    def can_execute(self) -> bool:
        """Check if a request can be executed."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if self._opened_at and (time.time() - self._opened_at) >= self.recovery_timeout:
                self._transition_to_half_open()
                return True
            self.stats.rejected_calls += 1
            return False

        if self.state == CircuitState.HALF_OPEN:
            # Allow limited calls in half-open state
            if self._half_open_calls < self.half_open_max_calls:
                return True
            return False

        return False

    def record_success(self) -> None:
        """Record a successful call."""
        self.stats.successes += 1
        self.stats.total_calls += 1
        self.stats.last_success_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self.half_open_max_calls:
                self._transition_to_closed()
                logger.info(
                    "circuit_closed",
                    name=self.name,
                    message="Circuit recovered after successful half-open calls",
                )

    def record_failure(self, error: Optional[Exception] = None) -> None:
        """Record a failed call."""
        self.stats.failures += 1
        self.stats.total_calls += 1
        self.stats.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            # Immediate transition back to open on any failure
            self._transition_to_open()
            logger.warning(
                "circuit_reopened",
                name=self.name,
                error=str(error) if error else "Unknown",
            )
        elif self.state == CircuitState.CLOSED:
            if self.stats.failures >= self.failure_threshold:
                self._transition_to_open()
                logger.warning(
                    "circuit_opened",
                    name=self.name,
                    failures=self.stats.failures,
                    threshold=self.failure_threshold,
                )

    def _transition_to_open(self) -> None:
        """Transition to open state."""
        self.state = CircuitState.OPEN
        self._opened_at = time.time()
        self._half_open_calls = 0

    def _transition_to_half_open(self) -> None:
        """Transition to half-open state."""
        self.state = CircuitState.HALF_OPEN
        self._half_open_calls = 0
        logger.info("circuit_half_open", name=self.name)

    def _transition_to_closed(self) -> None:
        """Transition to closed state."""
        self.state = CircuitState.CLOSED
        self.stats.failures = 0
        self._opened_at = None
        self._half_open_calls = 0

    def reset(self) -> None:
        """Reset the circuit breaker to initial state."""
        self.state = CircuitState.CLOSED
        self.stats = CircuitStats()
        self._opened_at = None
        self._half_open_calls = 0

    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failures": self.stats.failures,
            "successes": self.stats.successes,
            "total_calls": self.stats.total_calls,
            "rejected_calls": self.stats.rejected_calls,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_seconds": self.recovery_timeout,
        }

    def protect(self, func: Callable) -> Callable:
        """Decorator to protect a function with this circuit breaker."""

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not self.can_execute():
                raise CircuitOpenError(
                    f"Circuit breaker '{self.name}' is open. "
                    f"Retry after {self.recovery_timeout} seconds."
                )

            try:
                result = func(*args, **kwargs)
                self.record_success()
                return result
            except Exception as e:
                self.record_failure(e)
                raise

        return wrapper

    def protect_async(self, func: Callable) -> Callable:
        """Decorator to protect an async function with this circuit breaker."""

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not self.can_execute():
                raise CircuitOpenError(
                    f"Circuit breaker '{self.name}' is open. "
                    f"Retry after {self.recovery_timeout} seconds."
                )

            try:
                result = await func(*args, **kwargs)
                self.record_success()
                return result
            except Exception as e:
                self.record_failure(e)
                raise

        return wrapper


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is open."""

    pass


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""

    def __init__(self) -> None:
        self._breakers: Dict[str, CircuitBreaker] = {}

    def get_or_create(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 300,
    ) -> CircuitBreaker:
        """Get existing breaker or create a new one."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
        return self._breakers[name]

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all circuit breakers."""
        return {name: breaker.get_status() for name, breaker in self._breakers.items()}

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()


# Global registry
circuit_registry = CircuitBreakerRegistry()
