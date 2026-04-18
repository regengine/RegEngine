"""Shared rate-limit utilities.

Provides two distinct primitives:

1. ``limiter`` / ``add_rate_limiting`` -- route-level rate limiting via
   slowapi. Used as a decorator on individual FastAPI endpoints.

2. ``BruteForceLimiter`` -- cross-process failure counter backed by
   Redis. Used for high-stakes paths (admin master key, password
   login, MFA verify) where a per-process in-memory counter would be
   bypassed by multi-worker / multi-replica deployments. (#1392)

The brute-force limiter falls back to an in-memory implementation when
Redis is not available, so local development still works. In
production, setting ``REGENGINE_REDIS_URL`` enables the shared
counter.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict
from typing import Optional, Protocol

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from fastapi import FastAPI


# ---------------------------------------------------------------------------
# slowapi route-level limiter (unchanged public API)
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)


def add_rate_limiting(app: FastAPI):
    """Add standardized rate limiting middleware to the FastAPI app."""
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)


# ---------------------------------------------------------------------------
# Shared brute-force limiter (#1392)
# ---------------------------------------------------------------------------


class _RedisLike(Protocol):
    """Minimal Redis surface we need -- matches ``redis.Redis`` and
    most stand-ins used in tests."""

    def incr(self, name: str) -> int: ...

    def expire(self, name: str, time: int) -> bool: ...

    def get(self, name: str) -> Optional[bytes]: ...

    def delete(self, name: str) -> int: ...


class BruteForceLimiter:
    """Sliding-window failure counter shared across workers.

    Stores failure counts in Redis keyed by
    ``<namespace>:<subject>``. Each recorded failure increments the
    counter and (on first increment) sets an expiry equal to the
    window. When the counter exceeds the threshold, ``is_limited``
    returns True for the remainder of the window.

    This is intentionally simpler than a precise sliding-window log
    (we use a fixed-window counter with TTL). For the brute-force
    path -- where even 2x overshoot on window boundary is acceptable
    compared to per-worker bypass -- the trade-off is correct.
    """

    def __init__(
        self,
        *,
        namespace: str,
        max_failures: int,
        window_seconds: int,
        redis_client: Optional[_RedisLike] = None,
    ) -> None:
        self._namespace = namespace
        self._max = max_failures
        self._window = window_seconds

        self._redis = redis_client
        if self._redis is None:
            self._redis = self._try_connect_redis()

        # In-memory fallback (matches the previous routes.py behavior).
        # Used when no Redis connection is available (local dev, tests).
        self._mem_failures: dict[str, list[float]] = defaultdict(list)
        self._mem_lock = threading.Lock()

    @staticmethod
    def _try_connect_redis() -> Optional[_RedisLike]:
        """Try to connect to Redis; return None if unavailable."""
        url = (
            os.getenv("REGENGINE_REDIS_URL")
            or os.getenv("REDIS_URL")
            or os.getenv("UPSTASH_REDIS_REST_URL")
        )
        if not url:
            return None
        try:  # pragma: no cover -- depends on Redis being available
            import redis  # type: ignore

            client = redis.Redis.from_url(url, socket_timeout=1, socket_connect_timeout=1)
            # Ping to confirm before handing out.
            client.ping()
            return client
        except Exception:
            return None

    def _key(self, subject: str) -> str:
        return f"{self._namespace}:{subject}"

    def is_limited(self, subject: str) -> bool:
        """Return True if this subject has exceeded the threshold."""
        if self._redis is not None:
            try:
                raw = self._redis.get(self._key(subject))
                if raw is None:
                    return False
                try:
                    count = int(raw)
                except (ValueError, TypeError):
                    return False
                return count >= self._max
            except Exception:
                # Redis failure -- fall through to in-memory to avoid
                # a DoS on the auth path when Redis is flaky.
                pass

        # In-memory fallback (per-process, matches legacy behavior)
        now = time.time()
        with self._mem_lock:
            self._mem_failures[subject] = [
                t for t in self._mem_failures[subject] if now - t < self._window
            ]
            return len(self._mem_failures[subject]) >= self._max

    def record_failure(self, subject: str) -> int:
        """Record a failure and return the current count."""
        if self._redis is not None:
            try:
                key = self._key(subject)
                count = self._redis.incr(key)
                if count == 1:
                    # First failure in this window -- arm the TTL.
                    self._redis.expire(key, self._window)
                return int(count)
            except Exception:
                pass

        # In-memory fallback
        now = time.time()
        with self._mem_lock:
            self._mem_failures[subject].append(now)
            if len(self._mem_failures[subject]) > self._max * 4:
                self._mem_failures[subject] = self._mem_failures[subject][
                    -(self._max * 2):
                ]
            return len(self._mem_failures[subject])

    def reset(self, subject: str) -> None:
        """Clear the failure counter for a subject (e.g., on success)."""
        if self._redis is not None:
            try:
                self._redis.delete(self._key(subject))
            except Exception:
                pass
        with self._mem_lock:
            self._mem_failures.pop(subject, None)

    @property
    def window_seconds(self) -> int:
        return self._window

    @property
    def max_failures(self) -> int:
        return self._max

    @property
    def is_redis_backed(self) -> bool:
        """Reports whether this limiter is using a shared store.

        False => single-process fallback in use; a multi-worker or
        multi-replica deployment will let attackers achieve
        ``max_failures * N_replicas`` attempts before lockout. Ops
        should alert on this being False in prod.
        """
        return self._redis is not None
