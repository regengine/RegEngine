"""Tests for subscription gate circuit breaker integration.

Validates that the subscription gate fails closed (HTTP 503) when Redis is
down and the circuit breaker opens, rather than silently allowing requests
through.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Depends
from httpx import ASGITransport, AsyncClient

from shared.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState

# ---------------------------------------------------------------------------
# Fixture: minimal FastAPI app with the subscription gate dependency
# ---------------------------------------------------------------------------

app = FastAPI()


# We import the actual dependency; tests control behaviour via mocks.
from app.subscription_gate import require_active_subscription


@app.get("/protected", dependencies=[Depends(require_active_subscription)])
async def protected_route():
    return {"ok": True}


@pytest.fixture
def fresh_circuit():
    """Provide a fresh redis_circuit and reset it after each test."""
    from shared.circuit_breaker import redis_circuit

    redis_circuit.reset()
    yield redis_circuit
    redis_circuit.reset()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Happy path: Redis healthy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_subscription_allowed(client, fresh_circuit):
    """Active subscription should return 200."""
    with patch("app.subscription_gate.os.getenv", return_value="redis://localhost:6379"), \
         patch("app.subscription_gate.redis_circuit", fresh_circuit):
        mock_redis = MagicMock()
        mock_redis.hget.return_value = "active"
        with patch("redis.from_url", return_value=mock_redis):
            resp = await client.get("/protected", params={"tenant_id": "t1"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cancelled_subscription_blocked(client, fresh_circuit):
    """Cancelled subscription should return 402."""
    with patch("app.subscription_gate.os.getenv", return_value="redis://localhost:6379"), \
         patch("app.subscription_gate.redis_circuit", fresh_circuit):
        mock_redis = MagicMock()
        mock_redis.hget.return_value = "cancelled"
        with patch("redis.from_url", return_value=mock_redis):
            resp = await client.get("/protected", params={"tenant_id": "t1"})
    assert resp.status_code == 402


@pytest.mark.asyncio
async def test_trialing_subscription_allowed(client, fresh_circuit):
    """Trialing subscription should return 200."""
    with patch("app.subscription_gate.os.getenv", return_value="redis://localhost:6379"), \
         patch("app.subscription_gate.redis_circuit", fresh_circuit):
        mock_redis = MagicMock()
        mock_redis.hget.return_value = "trialing"
        with patch("redis.from_url", return_value=mock_redis):
            resp = await client.get("/protected", params={"tenant_id": "t1"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_missing_key_allows_through(client, fresh_circuit):
    """When Redis key doesn't exist (None), request is allowed through."""
    with patch("app.subscription_gate.os.getenv", return_value="redis://localhost:6379"), \
         patch("app.subscription_gate.redis_circuit", fresh_circuit):
        mock_redis = MagicMock()
        mock_redis.hget.return_value = None
        with patch("redis.from_url", return_value=mock_redis):
            resp = await client.get("/protected", params={"tenant_id": "t1"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Circuit breaker: Redis down -> fail closed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold_failures(client, fresh_circuit):
    """After enough Redis failures the circuit opens and returns 503."""
    import redis as redis_lib

    with patch("app.subscription_gate.os.getenv", return_value="redis://localhost:6379"), \
         patch("app.subscription_gate.redis_circuit", fresh_circuit):
        mock_redis = MagicMock()
        mock_redis.hget.side_effect = redis_lib.ConnectionError("Connection refused")

        with patch("redis.from_url", return_value=mock_redis):
            # Drive failures up to the threshold (redis_circuit threshold=10)
            for _ in range(fresh_circuit.failure_threshold):
                resp = await client.get("/protected", params={"tenant_id": "t1"})
                # Individual failures still fail open (return 200) because
                # the circuit is not yet open — they return None from the
                # except branch.
                assert resp.status_code == 200

            # Next request should hit the open circuit -> 503
            resp = await client.get("/protected", params={"tenant_id": "t1"})
            assert resp.status_code == 503
            assert "temporarily unavailable" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_circuit_open_returns_503_immediately(client, fresh_circuit):
    """Once the circuit is open, requests get 503 without hitting Redis."""
    # Force the circuit open
    fresh_circuit._transition_to(CircuitState.OPEN)
    fresh_circuit._last_failure_time = time.monotonic()

    with patch("app.subscription_gate.os.getenv", return_value="redis://localhost:6379"), \
         patch("app.subscription_gate.redis_circuit", fresh_circuit):
        # Redis should NOT be called at all
        with patch("redis.from_url") as mock_from_url:
            resp = await client.get("/protected", params={"tenant_id": "t1"})
            assert resp.status_code == 503
            mock_from_url.assert_not_called()


# ---------------------------------------------------------------------------
# Circuit recovery: half-open -> closed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_circuit_recovers_after_timeout(client, fresh_circuit):
    """After recovery timeout, circuit goes half-open and resumes on success."""
    # Force circuit open with a last_failure_time far in the past
    fresh_circuit._transition_to(CircuitState.OPEN)
    fresh_circuit._last_failure_time = time.monotonic() - (fresh_circuit.recovery_timeout + 1)

    with patch("app.subscription_gate.os.getenv", return_value="redis://localhost:6379"), \
         patch("app.subscription_gate.redis_circuit", fresh_circuit):
        mock_redis = MagicMock()
        mock_redis.hget.return_value = "active"
        with patch("redis.from_url", return_value=mock_redis):
            # Circuit should be half-open now, and this success should work
            resp = await client.get("/protected", params={"tenant_id": "t1"})
            assert resp.status_code == 200

            # After enough successes, circuit should close
            for _ in range(fresh_circuit.half_open_max_calls):
                resp = await client.get("/protected", params={"tenant_id": "t1"})
                assert resp.status_code == 200

    assert fresh_circuit.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_no_tenant_id_skips_gate(client, fresh_circuit):
    """Requests without tenant_id skip the subscription gate entirely."""
    resp = await client.get("/protected")
    assert resp.status_code == 200
