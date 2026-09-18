"""#2849 — the subscription gate must not do synchronous Redis I/O on the loop.

``require_active_subscription`` is an ``async def`` FastAPI dependency on the
primary ingest path (``POST /api/v1/webhooks/ingest``). It used to call a
synchronous redis-py helper inline, and that helper built a brand-new client
(and ConnectionPool) per call. Two defects in one:

1. **Event-loop blocking.** Uvicorn runs one loop per worker, so a blocking
   TCP round-trip inside the dependency stalls *every* concurrent request in
   the process — health probes included — for the duration of the call.
2. **Connection churn.** A fresh ``from_url`` per request opens a new TCP
   (and, for ``rediss://``, TLS) connection, uses it once, and drops it
   without closing — paying full setup cost per request and pushing against
   Redis' connection limit.

The existing gate tests (``test_subscription_gate.py``,
``test_subscription_gate_fail_closed.py``) assert only status-code semantics
and pass either way, so these are the tests that pin the fix.
"""

from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import services.ingestion.app.subscription_gate as gate
from services.ingestion.app.subscription_gate import require_active_subscription
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient


def _reset_redis_client() -> None:
    """Drop the gate's cached client if it has one.

    Resolved at call time and tolerant of its absence on purpose: the point
    of these tests is the *behaviour* below, so reverting the fix must make
    them fail on their assertions rather than on a missing import.
    """
    reset = getattr(gate, "reset_redis_client", None)
    if reset is not None:
        reset()

REDIS_URL = "redis://localhost:6379"

app = FastAPI()


@app.middleware("http")
async def _inject_authenticated_tenant(request, call_next):
    tenant_id = request.headers.get("X-Tenant-ID")
    if tenant_id:
        request.state.api_key = SimpleNamespace(tenant_id=tenant_id)
    return await call_next(request)


@app.get("/paid", dependencies=[Depends(require_active_subscription)])
async def paid_route():
    return {"ok": True}


@pytest.fixture(autouse=True)
def _fresh_state():
    """Reset the cached client and the shared circuit breaker per test."""
    from shared.circuit_breaker import redis_circuit

    _reset_redis_client()
    redis_circuit.reset()
    yield
    _reset_redis_client()
    redis_circuit.reset()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_redis_hget_runs_off_the_event_loop(client):
    """The blocking ``hget`` must execute on a worker thread, not the loop.

    ``AsyncClient(ASGITransport)`` drives the app on the *same* loop as this
    test body, so this test's own thread id is the event-loop thread id.
    """
    loop_thread_id = threading.get_ident()
    call_thread_ids: list[int] = []

    def _hget(*_args, **_kwargs):
        call_thread_ids.append(threading.get_ident())
        return "active"

    mock_redis = MagicMock()
    mock_redis.hget.side_effect = _hget

    with patch("services.ingestion.app.subscription_gate.os.getenv", return_value=REDIS_URL):
        with patch("redis.from_url", return_value=mock_redis):
            resp = await client.get("/paid", headers={"X-Tenant-ID": "t1"})

    assert resp.status_code == 200
    assert call_thread_ids, "the gate never called Redis"
    assert loop_thread_id not in call_thread_ids, (
        "subscription gate ran a blocking Redis call on the event loop thread "
        f"(loop={loop_thread_id}, calls={call_thread_ids})"
    )


@pytest.mark.asyncio
async def test_slow_redis_does_not_stall_concurrent_tasks(client):
    """A slow Redis must not freeze other work on the loop.

    ``hget`` blocks for 250ms. A concurrent asyncio ticker runs every 10ms.
    Off the loop the ticker keeps running throughout; on the loop it cannot
    run at all until the gate returns.
    """
    block_seconds = 0.25
    tick_interval = 0.01
    ticks = 0

    async def _ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(tick_interval)
            ticks += 1

    mock_redis = MagicMock()
    mock_redis.hget.side_effect = lambda *_a, **_k: (time.sleep(block_seconds), "active")[1]

    ticker_task = asyncio.create_task(_ticker())
    try:
        await asyncio.sleep(tick_interval * 2)  # let the ticker get going
        ticks_before = ticks

        with patch("services.ingestion.app.subscription_gate.os.getenv", return_value=REDIS_URL):
            with patch("redis.from_url", return_value=mock_redis):
                resp = await client.get("/paid", headers={"X-Tenant-ID": "t1"})
    finally:
        ticker_task.cancel()

    assert resp.status_code == 200
    ticks_during = ticks - ticks_before
    # 250ms of blocking / 10ms per tick is ~25 ticks with the offload; a
    # blocked loop yields 0–1. Assert well below the ideal to stay stable on
    # a loaded CI box while still failing hard on a blocked loop.
    assert ticks_during >= 5, (
        f"event loop was stalled during the subscription check: only {ticks_during} "
        f"ticks in {block_seconds}s of blocking Redis I/O"
    )


@pytest.mark.asyncio
async def test_redis_client_is_built_once_and_reused(client):
    """One pooled client per process — not one per gated request."""
    mock_redis = MagicMock()
    mock_redis.hget.return_value = "active"
    built: list[tuple] = []

    def _from_url(*args, **kwargs):
        built.append((args, kwargs))
        return mock_redis

    with patch("services.ingestion.app.subscription_gate.os.getenv", return_value=REDIS_URL):
        with patch("redis.from_url", side_effect=_from_url):
            for _ in range(5):
                resp = await client.get("/paid", headers={"X-Tenant-ID": "t1"})
                assert resp.status_code == 200

    assert len(built) == 1, f"built {len(built)} Redis clients for 5 gated requests (expected 1)"
    assert mock_redis.hget.call_count == 5, "the cached client must still be queried per request"
    mock_redis.close.assert_not_called()


@pytest.mark.asyncio
async def test_cached_client_uses_bounded_timeouts(client):
    """The pooled client bounds both connect and read.

    It now runs in a worker thread; an unbounded client would pin one of the
    finite threadpool threads for as long as Redis hangs.
    """
    mock_redis = MagicMock()
    mock_redis.hget.return_value = "active"
    built: list[dict] = []

    def _from_url(*_args, **kwargs):
        built.append(kwargs)
        return mock_redis

    with patch("services.ingestion.app.subscription_gate.os.getenv", return_value=REDIS_URL):
        with patch("redis.from_url", side_effect=_from_url):
            resp = await client.get("/paid", headers={"X-Tenant-ID": "t1"})

    assert resp.status_code == 200
    assert built, "no Redis client was constructed"
    assert built[0].get("socket_connect_timeout"), "connect is unbounded"
    assert built[0].get("socket_timeout"), "read is unbounded"


@pytest.mark.asyncio
async def test_changed_redis_url_rebuilds_the_client(client):
    """A rotated ``REDIS_URL`` must not keep answering from the old host."""
    first, second = MagicMock(), MagicMock()
    first.hget.return_value = "active"
    second.hget.return_value = "active"
    urls: list[str] = []

    def _from_url(url, *_args, **_kwargs):
        urls.append(url)
        return first if url == REDIS_URL else second

    with patch("redis.from_url", side_effect=_from_url):
        with patch("services.ingestion.app.subscription_gate.os.getenv", return_value=REDIS_URL):
            assert (await client.get("/paid", headers={"X-Tenant-ID": "t1"})).status_code == 200
        with patch("services.ingestion.app.subscription_gate.os.getenv", return_value="redis://rotated:6379"):
            assert (await client.get("/paid", headers={"X-Tenant-ID": "t1"})).status_code == 200

    assert urls == [REDIS_URL, "redis://rotated:6379"]
    assert second.hget.call_count == 1
