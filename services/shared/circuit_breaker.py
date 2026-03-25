"""Circuit breaker pattern implementation for RegEngine services.

Prevents cascading failures by failing fast when downstream services are unhealthy.
Supports pluggable storage backends (in-memory or Redis) for distributed state.

Usage:
    from shared.circuit_breaker import CircuitBreaker, CircuitOpenError

    neo4j_breaker = CircuitBreaker(
        name="neo4j",
        failure_threshold=5,
        recovery_timeout=30,
        half_open_max_calls=3,
    )

    @neo4j_breaker
    async def query_neo4j(query: str):
        # If circuit is open, raises CircuitOpenError immediately
        return await neo4j_client.run(query)

Set CIRCUIT_BREAKER_BACKEND=redis to share state across instances.
"""

from __future__ import annotations

import asyncio
import functools
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, TypeVar

import structlog

from shared.circuit_breaker_store import CircuitStore, get_store

logger = structlog.get_logger("circuit_breaker")

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "CLOSED"      # Normal operation, requests flow through
    OPEN = "OPEN"          # Failing fast, no requests allowed
    HALF_OPEN = "HALF_OPEN"  # Testing if service recovered


class CircuitOpenError(Exception):
    """Raised when circuit is open and request is rejected."""

    def __init__(self, name: str, retry_after: float):
        self.name = name
        self.retry_after = retry_after
        super().__init__(f"Circuit '{name}' is OPEN. Retry after {retry_after:.1f}s")


@dataclass
class CircuitBreaker:
    """Circuit breaker for protecting against cascading failures.

    State is stored in a pluggable backend (memory or Redis) so it can
    be shared across multiple service instances.

    Attributes:
        name: Identifier for this circuit (e.g., "neo4j", "redis")
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Seconds to wait before testing recovery
        half_open_max_calls: Max calls to attempt in half-open state
        exceptions: Exception types that trigger failure count
    """
    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3
    exceptions: tuple = (Exception,)

    # Local counters (not persisted — metrics only)
    _half_open_calls: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _total_calls: int = field(default=0, init=False)
    _store: Optional[CircuitStore] = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._store = get_store()

    @property
    def _state(self) -> CircuitState:
        return CircuitState(self._store.get_state(self.name))

    @_state.setter
    def _state(self, value: CircuitState) -> None:
        self._store.set_state(self.name, value.value)

    @property
    def _failure_count(self) -> int:
        return self._store.get_failure_count(self.name)

    @_failure_count.setter
    def _failure_count(self, value: int) -> None:
        if value == 0:
            self._store.reset_failures(self.name)
        # Non-zero values set via incr_failure in _record_failure

    @property
    def _last_failure_time(self) -> float:
        return self._store.get_last_failure_time(self.name)

    @_last_failure_time.setter
    def _last_failure_time(self, value: float) -> None:
        self._store.set_last_failure_time(self.name, value)

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, transitioning if needed."""
        current = self._state
        if current == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                self._transition_to(CircuitState.HALF_OPEN)
                return CircuitState.HALF_OPEN
        return current

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state with logging."""
        old_state = self._state
        self._state = new_state
        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0
        logger.info(
            "circuit_state_changed",
            circuit=self.name,
            old_state=old_state.value,
            new_state=new_state.value,
        )

    def _record_success(self) -> None:
        """Record a successful call."""
        self._success_count += 1
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self.half_open_max_calls:
                self._transition_to(CircuitState.CLOSED)
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def _record_failure(self, exc: Exception) -> None:
        """Record a failed call."""
        count = self._store.incr_failure(self.name)
        self._last_failure_time = time.monotonic()

        logger.warning(
            "circuit_failure_recorded",
            circuit=self.name,
            failure_count=count,
            threshold=self.failure_threshold,
            error=str(exc),
        )

        if self._state == CircuitState.HALF_OPEN:
            self._transition_to(CircuitState.OPEN)
        elif count >= self.failure_threshold:
            self._transition_to(CircuitState.OPEN)

    def _check_state(self) -> None:
        """Check if requests are allowed, raise if circuit is open."""
        state = self.state  # Triggers state check
        if state == CircuitState.OPEN:
            retry_after = self.recovery_timeout - (time.monotonic() - self._last_failure_time)
            raise CircuitOpenError(self.name, max(0, retry_after))

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorator for protecting a function with circuit breaker."""
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> T:
                self._total_calls += 1
                self._check_state()
                try:
                    result = await func(*args, **kwargs)
                    self._record_success()
                    return result
                except self.exceptions as exc:
                    self._record_failure(exc)
                    raise
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> T:
                self._total_calls += 1
                self._check_state()
                try:
                    result = func(*args, **kwargs)
                    self._record_success()
                    return result
                except self.exceptions as exc:
                    self._record_failure(exc)
                    raise
            return sync_wrapper

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute a function with circuit breaker protection (supports sync and async)."""
        self._total_calls += 1
        self._check_state()
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    result = await result

            self._record_success()
            return result
        except self.exceptions as exc:
            self._record_failure(exc)
            raise

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        self._transition_to(CircuitState.CLOSED)
        self._failure_count = 0
        self._last_failure_time = 0
        logger.info("circuit_manually_reset", circuit=self.name)

    def get_metrics(self) -> dict:
        """Get circuit breaker metrics for monitoring."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "total_calls": self._total_calls,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }


# Pre-configured circuit breakers for common services
neo4j_circuit = CircuitBreaker(
    name="neo4j",
    failure_threshold=5,
    recovery_timeout=30.0,
    exceptions=(Exception,),
)

redis_circuit = CircuitBreaker(
    name="redis",
    failure_threshold=10,
    recovery_timeout=15.0,
    exceptions=(Exception,),
)

postgres_circuit = CircuitBreaker(
    name="postgres",
    failure_threshold=5,
    recovery_timeout=30.0,
    exceptions=(Exception,),
)

kafka_circuit = CircuitBreaker(
    name="kafka",
    failure_threshold=5,
    recovery_timeout=60.0,
    exceptions=(Exception,),
)


def get_all_circuit_metrics() -> list[dict]:
    """Get metrics for all pre-configured circuit breakers."""
    return [
        neo4j_circuit.get_metrics(),
        redis_circuit.get_metrics(),
        postgres_circuit.get_metrics(),
        kafka_circuit.get_metrics(),
    ]
