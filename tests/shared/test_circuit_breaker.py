"""Tests for circuit breaker module."""

import pytest
import asyncio
from unittest.mock import MagicMock

from shared.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitOpenError,
    neo4j_circuit,
    redis_circuit,
    get_all_circuit_metrics,
)


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_initial_state_is_closed(self):
        """Circuit should start in CLOSED state."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)
        assert breaker.state == CircuitState.CLOSED

    def test_opens_after_failure_threshold(self):
        """Circuit should open after reaching failure threshold."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)
        
        @breaker
        def failing_func():
            raise ValueError("Test error")
        
        # Fail 3 times
        for _ in range(3):
            with pytest.raises(ValueError):
                failing_func()
        
        # Should now be open
        assert breaker.state == CircuitState.OPEN

    def test_rejects_when_open(self):
        """Circuit should reject calls when open."""
        breaker = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=60)
        
        @breaker
        def failing_func():
            raise ValueError("Test error")
        
        # Trigger open state
        with pytest.raises(ValueError):
            failing_func()
        
        # Should reject with CircuitOpenError
        with pytest.raises(CircuitOpenError) as exc_info:
            failing_func()
        
        assert exc_info.value.name == "test"
        assert exc_info.value.retry_after > 0

    def test_success_resets_failure_count(self):
        """Successful calls should reset failure count."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)
        call_count = 0
        
        @breaker
        def sometimes_fails():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("First call fails")
            return "success"
        
        # First call fails
        with pytest.raises(ValueError):
            sometimes_fails()
        
        # Second call succeeds - should reset
        result = sometimes_fails()
        assert result == "success"
        assert breaker._failure_count == 0

    def test_metrics(self):
        """Should return metrics dict."""
        breaker = CircuitBreaker(name="test-metrics", failure_threshold=5)
        metrics = breaker.get_metrics()
        
        assert metrics["name"] == "test-metrics"
        assert metrics["state"] == "CLOSED"
        assert metrics["failure_threshold"] == 5
        assert "total_calls" in metrics

    def test_reset(self):
        """Manual reset should close circuit."""
        breaker = CircuitBreaker(name="test", failure_threshold=1)
        
        @breaker
        def failing_func():
            raise ValueError("Error")
        
        # Open the circuit
        with pytest.raises(ValueError):
            failing_func()
        
        assert breaker.state == CircuitState.OPEN
        
        # Reset
        breaker.reset()
        assert breaker.state == CircuitState.CLOSED


class TestAsyncCircuitBreaker:
    """Test async circuit breaker functionality."""

    @pytest.mark.asyncio
    async def test_async_function_works(self):
        """Circuit breaker should work with async functions."""
        breaker = CircuitBreaker(name="async-test", failure_threshold=3)
        
        @breaker
        async def async_func():
            return "async success"
        
        result = await async_func()
        assert result == "async success"

    @pytest.mark.asyncio
    async def test_async_opens_after_failures(self):
        """Async circuit should open after failures."""
        breaker = CircuitBreaker(name="async-fail", failure_threshold=2)
        
        @breaker
        async def async_failing():
            raise RuntimeError("Async error")
        
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await async_failing()
        
        assert breaker.state == CircuitState.OPEN


class TestPreConfiguredCircuits:
    """Test pre-configured circuit breakers."""

    def test_neo4j_circuit_exists(self):
        """Neo4j circuit should be pre-configured."""
        assert neo4j_circuit.name == "neo4j"
        assert neo4j_circuit.failure_threshold == 5

    def test_redis_circuit_exists(self):
        """Redis circuit should be pre-configured."""
        assert redis_circuit.name == "redis"
        assert redis_circuit.failure_threshold == 10

    def test_get_all_metrics(self):
        """Should return metrics for all pre-configured circuits."""
        metrics = get_all_circuit_metrics()
        
        assert len(metrics) == 4
        names = [m["name"] for m in metrics]
        assert "neo4j" in names
        assert "redis" in names
        assert "postgres" in names
        assert "kafka" in names
