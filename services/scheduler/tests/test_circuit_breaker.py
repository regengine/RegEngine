"""
Tests for the circuit breaker module.

Validates state transitions, failure thresholds, recovery timeouts,
protect decorator, and the circuit breaker registry.
"""

import time
import pytest

from app.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitOpenError,
    CircuitState,
    CircuitStats,
)


class TestCircuitBreakerInit:
    """Test initial state of a circuit breaker."""

    def test_default_state_is_closed(self):
        cb = CircuitBreaker(name="test")
        assert cb.state == CircuitState.CLOSED

    def test_default_failure_threshold(self):
        cb = CircuitBreaker(name="test")
        assert cb.failure_threshold == 5

    def test_default_recovery_timeout(self):
        cb = CircuitBreaker(name="test")
        assert cb.recovery_timeout == 300

    def test_custom_thresholds(self):
        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout=60)
        assert cb.failure_threshold == 3
        assert cb.recovery_timeout == 60

    def test_initial_stats_are_zero(self):
        cb = CircuitBreaker(name="test")
        assert cb.stats.failures == 0
        assert cb.stats.successes == 0
        assert cb.stats.total_calls == 0
        assert cb.stats.rejected_calls == 0


class TestCircuitBreakerTransitions:
    """Test state machine transitions."""

    def test_closed_allows_execution(self):
        cb = CircuitBreaker(name="test")
        assert cb.can_execute() is True

    def test_failures_below_threshold_stay_closed(self):
        cb = CircuitBreaker(name="test", failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_failures_at_threshold_open_circuit(self):
        cb = CircuitBreaker(name="test", failure_threshold=5)
        for _ in range(5):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_open_circuit_rejects_execution(self):
        cb = CircuitBreaker(name="test", failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_open_circuit_increments_rejected(self):
        cb = CircuitBreaker(name="test", failure_threshold=1)
        cb.record_failure()
        cb.can_execute()
        assert cb.stats.rejected_calls == 1

    def test_open_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        # With 0 timeout, next can_execute should transition
        time.sleep(0.01)
        assert cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_closes_after_enough_successes(self):
        cb = CircuitBreaker(
            name="test", failure_threshold=1, recovery_timeout=0, half_open_max_calls=2
        )
        cb.record_failure()
        time.sleep(0.01)
        cb.can_execute()  # transitions to half-open
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_reopens_on_failure(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0)
        cb.record_failure()
        time.sleep(0.01)
        cb.can_execute()  # transitions to half-open
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count_after_close(self):
        cb = CircuitBreaker(
            name="test", failure_threshold=1, recovery_timeout=0, half_open_max_calls=1
        )
        cb.record_failure()
        time.sleep(0.01)
        cb.can_execute()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.stats.failures == 0


class TestCircuitBreakerReset:
    """Test reset functionality."""

    def test_reset_returns_to_closed(self):
        cb = CircuitBreaker(name="test", failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED

    def test_reset_clears_stats(self):
        cb = CircuitBreaker(name="test")
        cb.record_failure()
        cb.record_success()
        cb.reset()
        assert cb.stats.failures == 0
        assert cb.stats.successes == 0
        assert cb.stats.total_calls == 0


class TestCircuitBreakerProtect:
    """Test the protect decorator."""

    def test_protect_passes_through_on_closed(self):
        cb = CircuitBreaker(name="test")

        @cb.protect
        def add(a, b):
            return a + b

        assert add(2, 3) == 5
        assert cb.stats.successes == 1

    def test_protect_records_failure_on_exception(self):
        cb = CircuitBreaker(name="test")

        @cb.protect
        def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            fail()
        assert cb.stats.failures == 1

    def test_protect_raises_circuit_open_error(self):
        cb = CircuitBreaker(name="test", failure_threshold=1)
        cb.record_failure()

        @cb.protect
        def noop():
            return 42

        with pytest.raises(CircuitOpenError):
            noop()


class TestCircuitBreakerGetStatus:
    """Test status reporting."""

    def test_status_dict_has_expected_keys(self):
        cb = CircuitBreaker(name="fda_scraper")
        status = cb.get_status()
        assert status["name"] == "fda_scraper"
        assert status["state"] == "closed"
        assert "failures" in status
        assert "failure_threshold" in status


class TestCircuitBreakerRegistry:
    """Test the circuit breaker registry."""

    def test_get_or_create_creates_new(self):
        registry = CircuitBreakerRegistry()
        cb = registry.get_or_create("test_scraper")
        assert cb.name == "test_scraper"

    def test_get_or_create_returns_same_instance(self):
        registry = CircuitBreakerRegistry()
        cb1 = registry.get_or_create("test")
        cb2 = registry.get_or_create("test")
        assert cb1 is cb2

    def test_get_all_status(self):
        registry = CircuitBreakerRegistry()
        registry.get_or_create("a")
        registry.get_or_create("b")
        statuses = registry.get_all_status()
        assert "a" in statuses
        assert "b" in statuses

    def test_reset_all(self):
        registry = CircuitBreakerRegistry()
        cb = registry.get_or_create("test", failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        registry.reset_all()
        assert cb.state == CircuitState.CLOSED
