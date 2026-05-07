"""Regression tests for #1182 — subscription gate must fail CLOSED.

Specifically:
1. Missing Redis key (tenant not yet billed) -> HTTP 402 (was: 200).
2. Redis error / timeout -> HTTP 503 (was: 200 on first few failures).
3. ``SUBSCRIPTION_GATE_FAIL_OPEN=true`` env flag bypasses gate (explicit
   opt-in for incident response only).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.subscription_gate import require_active_subscription


app = FastAPI()


@app.get("/paid", dependencies=[Depends(require_active_subscription)])
async def paid_route():
    return {"ok": True}


@pytest.fixture
def fresh_circuit():
    from shared.circuit_breaker import redis_circuit

    redis_circuit.reset()
    yield redis_circuit
    redis_circuit.reset()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Missing key -> 402 (fail-closed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_key_returns_402(client, fresh_circuit):
    """New tenant with no billing key must get 402, not a free pass."""
    with patch("app.subscription_gate.os.getenv") as getenv_mock, \
         patch("app.subscription_gate.redis_circuit", fresh_circuit):
        getenv_mock.side_effect = lambda key, default=None: {
            "REDIS_URL": "redis://localhost:6379",
            "SUBSCRIPTION_GATE_FAIL_OPEN": "",
        }.get(key, default if default is not None else "")

        mock_redis = MagicMock()
        mock_redis.hget.return_value = None
        with patch("redis.from_url", return_value=mock_redis):
            resp = await client.get("/paid", headers={"X-Tenant-ID": "t1"})

    assert resp.status_code == 402
    assert "subscription" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Redis unavailable -> 503 (fail-closed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_error_returns_503_first_call(client, fresh_circuit):
    """Even a single Redis ConnectionError must 503 — no fail-open window."""
    import redis as redis_lib

    with patch("app.subscription_gate.os.getenv") as getenv_mock, \
         patch("app.subscription_gate.redis_circuit", fresh_circuit):
        getenv_mock.side_effect = lambda key, default=None: {
            "REDIS_URL": "redis://localhost:6379",
            "SUBSCRIPTION_GATE_FAIL_OPEN": "",
        }.get(key, default if default is not None else "")

        mock_redis = MagicMock()
        mock_redis.hget.side_effect = redis_lib.ConnectionError("refused")
        with patch("redis.from_url", return_value=mock_redis):
            resp = await client.get("/paid", headers={"X-Tenant-ID": "t1"})

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_no_redis_url_configured_returns_503(client, fresh_circuit):
    """REDIS_URL unset means we cannot check billing -> 503, not 200."""
    with patch("app.subscription_gate.os.getenv") as getenv_mock, \
         patch("app.subscription_gate.redis_circuit", fresh_circuit):
        getenv_mock.side_effect = lambda key, default=None: {
            "REDIS_URL": None,
            "SUBSCRIPTION_GATE_FAIL_OPEN": "",
        }.get(key, default if default is not None else "")
        resp = await client.get("/paid", headers={"X-Tenant-ID": "t1"})

    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Explicit bypass flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fail_open_flag_bypasses_gate(client, fresh_circuit):
    """SUBSCRIPTION_GATE_FAIL_OPEN=true skips Redis entirely (incident escape hatch)."""
    with patch("app.subscription_gate.os.getenv") as getenv_mock, \
         patch("app.subscription_gate.redis_circuit", fresh_circuit):
        getenv_mock.side_effect = lambda key, default=None: {
            "REDIS_URL": "redis://localhost:6379",
            "SUBSCRIPTION_GATE_FAIL_OPEN": "true",
        }.get(key, default if default is not None else "")

        # Redis.from_url should NEVER be called under the bypass.
        with patch("redis.from_url") as from_url_mock:
            resp = await client.get("/paid", headers={"X-Tenant-ID": "t1"})
            from_url_mock.assert_not_called()

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_fail_open_flag_off_by_default(client, fresh_circuit):
    """Default config is fail-closed — matches test above without flag."""
    with patch("app.subscription_gate.os.getenv") as getenv_mock, \
         patch("app.subscription_gate.redis_circuit", fresh_circuit):
        getenv_mock.side_effect = lambda key, default=None: {
            "REDIS_URL": "redis://localhost:6379",
            # No fail-open flag set.
        }.get(key, default if default is not None else "")

        mock_redis = MagicMock()
        mock_redis.hget.return_value = None
        with patch("redis.from_url", return_value=mock_redis):
            resp = await client.get("/paid", headers={"X-Tenant-ID": "t1"})

    assert resp.status_code == 402
