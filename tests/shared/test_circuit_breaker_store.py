"""Tests for circuit breaker storage backends."""

import pytest

from shared.circuit_breaker_store import (
    MemoryCircuitStore,
    get_store,
    reset_store,
)


class TestMemoryCircuitStore:
    """Tests for the in-memory storage backend."""

    def setup_method(self):
        self.store = MemoryCircuitStore()

    def test_default_state_is_closed(self):
        assert self.store.get_state("test") == "CLOSED"

    def test_set_and_get_state(self):
        self.store.set_state("test", "OPEN")
        assert self.store.get_state("test") == "OPEN"

    def test_default_failure_count_is_zero(self):
        assert self.store.get_failure_count("test") == 0

    def test_incr_failure(self):
        assert self.store.incr_failure("test") == 1
        assert self.store.incr_failure("test") == 2
        assert self.store.get_failure_count("test") == 2

    def test_reset_failures(self):
        self.store.incr_failure("test")
        self.store.incr_failure("test")
        self.store.reset_failures("test")
        assert self.store.get_failure_count("test") == 0

    def test_default_last_failure_time_is_zero(self):
        assert self.store.get_last_failure_time("test") == 0.0

    def test_set_and_get_last_failure_time(self):
        self.store.set_last_failure_time("test", 123.456)
        assert self.store.get_last_failure_time("test") == 123.456

    def test_independent_circuits(self):
        """Different circuit names should have independent state."""
        self.store.set_state("a", "OPEN")
        self.store.incr_failure("a")
        assert self.store.get_state("b") == "CLOSED"
        assert self.store.get_failure_count("b") == 0


class TestGetStore:
    """Tests for the global store factory."""

    def setup_method(self):
        reset_store()

    def teardown_method(self):
        reset_store()

    def test_default_is_memory(self, monkeypatch):
        monkeypatch.delenv("CIRCUIT_BREAKER_BACKEND", raising=False)
        store = get_store()
        assert isinstance(store, MemoryCircuitStore)

    def test_explicit_memory(self, monkeypatch):
        monkeypatch.setenv("CIRCUIT_BREAKER_BACKEND", "memory")
        store = get_store()
        assert isinstance(store, MemoryCircuitStore)

    def test_singleton(self):
        s1 = get_store()
        s2 = get_store()
        assert s1 is s2

    def test_redis_fallback_on_error(self, monkeypatch):
        """If Redis is unavailable, should fallback to memory."""
        monkeypatch.setenv("CIRCUIT_BREAKER_BACKEND", "redis")
        monkeypatch.setenv("CIRCUIT_BREAKER_REDIS_URL", "redis://nonexistent:9999/0")
        store = get_store()
        # Should fallback to MemoryCircuitStore
        assert isinstance(store, MemoryCircuitStore)
