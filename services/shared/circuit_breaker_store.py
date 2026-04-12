"""Pluggable storage backends for distributed circuit breaker state.

The in-memory backend (default) works for single-instance deployments.
The Redis backend shares state across all replicas so a circuit opened
by instance A is immediately visible to instance B.

Usage::

    # Automatic — uses Redis if CIRCUIT_BREAKER_BACKEND=redis
    from shared.circuit_breaker_store import get_store
    store = get_store()

    # Or explicit
    store = RedisCircuitStore(redis_url="redis://redis:6379/3")
"""

from __future__ import annotations

import os
import time
from typing import Optional, Protocol

import structlog

logger = structlog.get_logger("circuit_breaker_store")


# ---------------------------------------------------------------------------
# Protocol (interface)
# ---------------------------------------------------------------------------

class CircuitStore(Protocol):
    """Backend for persisting circuit breaker state."""

    def get_state(self, name: str) -> str: ...
    def set_state(self, name: str, state: str) -> None: ...
    def get_failure_count(self, name: str) -> int: ...
    def incr_failure(self, name: str) -> int: ...
    def reset_failures(self, name: str) -> None: ...
    def get_last_failure_time(self, name: str) -> float: ...
    def set_last_failure_time(self, name: str, t: float) -> None: ...


# ---------------------------------------------------------------------------
# In-memory backend (default, single-process)
# ---------------------------------------------------------------------------

class MemoryCircuitStore:
    """In-memory store — same behaviour as the original dataclass fields."""

    def __init__(self) -> None:
        self._states: dict[str, str] = {}
        self._failures: dict[str, int] = {}
        self._last_failure: dict[str, float] = {}

    def get_state(self, name: str) -> str:
        return self._states.get(name, "CLOSED")

    def set_state(self, name: str, state: str) -> None:
        self._states[name] = state

    def get_failure_count(self, name: str) -> int:
        return self._failures.get(name, 0)

    def incr_failure(self, name: str) -> int:
        self._failures[name] = self._failures.get(name, 0) + 1
        return self._failures[name]

    def reset_failures(self, name: str) -> None:
        self._failures[name] = 0

    def get_last_failure_time(self, name: str) -> float:
        return self._last_failure.get(name, 0.0)

    def set_last_failure_time(self, name: str, t: float) -> None:
        self._last_failure[name] = t


# ---------------------------------------------------------------------------
# Redis backend (distributed, survives restarts)
# ---------------------------------------------------------------------------

class RedisCircuitStore:
    """Redis-backed store for multi-instance deployments.

    Uses synchronous redis-py so the circuit breaker stays fully sync.
    All keys auto-expire after 1 hour to prevent stale state.
    """

    _KEY_TTL = 3600  # 1 hour

    def __init__(self, redis_url: Optional[str] = None) -> None:
        import redis as _redis

        url = redis_url or os.getenv("CIRCUIT_BREAKER_REDIS_URL") or os.getenv("REDIS_URL", "redis://redis:6379/0")
        self._redis = _redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
        self._redis.ping()  # Fail fast if Redis is unreachable
        self._prefix = "cb:"
        logger.info("redis_circuit_store_init", url=url.split("@")[-1])  # redact creds

    def _key(self, name: str, suffix: str) -> str:
        return f"{self._prefix}{name}:{suffix}"

    def get_state(self, name: str) -> str:
        return self._redis.get(self._key(name, "state")) or "CLOSED"

    def set_state(self, name: str, state: str) -> None:
        self._redis.set(self._key(name, "state"), state, ex=self._KEY_TTL)

    def get_failure_count(self, name: str) -> int:
        val = self._redis.get(self._key(name, "failures"))
        return int(val) if val else 0

    def incr_failure(self, name: str) -> int:
        key = self._key(name, "failures")
        count = self._redis.incr(key)
        self._redis.expire(key, self._KEY_TTL)
        return count

    def reset_failures(self, name: str) -> None:
        self._redis.delete(self._key(name, "failures"))

    def get_last_failure_time(self, name: str) -> float:
        val = self._redis.get(self._key(name, "last_fail"))
        return float(val) if val else 0.0

    def set_last_failure_time(self, name: str, t: float) -> None:
        self._redis.set(self._key(name, "last_fail"), str(t), ex=self._KEY_TTL)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_global_store: Optional[CircuitStore] = None


def get_store() -> CircuitStore:
    """Return the global circuit store (lazy-init, env-driven backend)."""
    global _global_store
    if _global_store is not None:
        return _global_store

    backend = os.getenv("CIRCUIT_BREAKER_BACKEND", "memory").lower()
    if backend == "redis":
        try:
            _global_store = RedisCircuitStore()
        except Exception as exc:
            logger.warning("redis_store_fallback_to_memory", error=str(exc))
            from shared.redis_health import report_redis_fallback
            report_redis_fallback("circuit_breaker", str(exc))
            _global_store = MemoryCircuitStore()
    else:
        _global_store = MemoryCircuitStore()

    return _global_store


def reset_store() -> None:
    """Reset global store (for testing)."""
    global _global_store
    _global_store = None
