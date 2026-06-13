"""Shared fixtures for contract tests."""

import pytest


@pytest.fixture(autouse=True)
def _clear_admin_brute_force_state():
    """Clear ``admin_auth:*`` brute-force counters in local Redis before each test.

    The admin contract ``client`` fixture sets
    ``REDIS_URL=redis://localhost:6379/0`` before importing the admin service,
    so ``BruteForceLimiter(namespace="admin_auth")`` is Redis-backed whenever a
    local Redis is running. Failure counts for ip="testclient" then persist
    across pytest processes: two suite runs within the 60s window poison each
    other, and tests expecting 401/403 get 429 instead.

    Only localhost is flushed -- a remote REDIS_URL must never be touched, and
    production stays Redis-backed (#1392).
    """
    try:
        import redis

        client = redis.Redis.from_url(
            "redis://localhost:6379/0",
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        keys = list(client.scan_iter("admin_auth:*"))
        if keys:
            client.delete(*keys)
    except Exception:
        # No local Redis -> the limiter falls back to in-memory and each
        # pytest process starts clean; nothing to clear.
        pass
