"""Readiness probe contract for the consolidated monolith (server/main.py).

railway.toml uses healthcheckPath=/readiness, so this endpoint gates deploys
and restarts:

* Postgres down or unconfigured -> 503 (fatal; instance cannot serve traffic).
* Redis down or unconfigured in strict deployed runtimes -> 503.
* Diligence E07: ingestion worker error (startup failure or dead thread) ->
  503. Embedded scheduler error -> 503 only when SCHEDULER_EMBEDDED enables
  it; ``disabled`` / ``not_configured`` stay non-blocking.
* Neo4j and rate-limiter errors stay non-blocking (reported; never alone
  flip the status code). /health remains a separate liveness probe.
* A stalled dependency probe returns 503 within its overall deadline while
  the event loop remains available for liveness requests.
* Neo4j down (graph subsystem active) -> 200 with overall status ``degraded``
  and the component reported in ``checks`` (optional graph mirror; must never
  block a deploy).
* Neo4j configured but graph subsystem disabled (the prod default) -> 200
  ``ready`` with ``not_probed`` in ``checks``; the driver is never contacted
  (WS-6 — a mirror no mounted route serves must not gate deploys).
* Neo4j unconfigured -> 200 ``ready`` with ``not_configured`` in ``checks``.
* The Neo4j driver must be created with bounded connect timeouts so an
  unreachable host cannot hang the probe past the healthcheck window.

The handler opens fresh connections per call via function-local imports, so
these tests monkeypatch ``sqlalchemy.create_engine`` and
``neo4j.GraphDatabase.driver``. The readiness route is mounted on a minimal
app because the full monolith lifespan requires a live database (startup
drift checks).
"""

from unittest.mock import MagicMock

import neo4j
import pytest
import sqlalchemy
from fastapi import FastAPI
from fastapi.testclient import TestClient

import server.main as main


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.add_api_route("/readiness", main.readiness, methods=["GET"])
    return TestClient(app)


@pytest.fixture
def _postgres_ok(monkeypatch):
    """Set a placeholder DATABASE_URL (env_defaults deliberately provides none)
    and fake the engine so the check passes without a live Postgres."""
    url = "postgresql://probe:probe@localhost:5432/readiness_probe"  # pragma: allowlist secret
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *a, **k: MagicMock())


@pytest.fixture
def _redis_unset(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)


def test_neo4j_down_returns_200_degraded(client, monkeypatch, _postgres_ok, _redis_unset):
    """A down Neo4j is non-fatal: 200 with the component degraded in the body."""
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j.invalid:7687")

    def _down_driver(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(neo4j.GraphDatabase, "driver", _down_driver)

    resp = client.get("/readiness")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["postgres"]["status"] == "ok"
    assert body["checks"]["neo4j"]["status"] == "error"
    assert body["checks"]["neo4j"]["error"] == "OSError"


def test_neo4j_check_uses_bounded_timeouts(client, monkeypatch, _postgres_ok, _redis_unset):
    """The driver defaults to 30s connect / 60s acquisition timeouts — an
    unreachable Neo4j would hang the probe and time out the Railway
    healthcheck even though the eventual response is 200. The check must
    pass short explicit timeouts (like the Redis check's 2s)."""
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j.example:7687")
    captured: dict = {}

    def _fake_driver(uri, **kwargs):
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(neo4j.GraphDatabase, "driver", _fake_driver)

    resp = client.get("/readiness")

    assert resp.status_code == 200
    assert resp.json()["checks"]["neo4j"]["status"] == "ok"
    assert captured["connection_timeout"] <= 5.0
    assert captured["connection_acquisition_timeout"] <= 5.0


def test_neo4j_driver_closed_when_connectivity_fails(client, monkeypatch, _postgres_ok, _redis_unset):
    """Railway probes repeatedly; a failing verify_connectivity must not leak
    a driver (and its background reconnect attempts) on every probe."""
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j.example:7687")
    fake_driver = MagicMock()
    fake_driver.verify_connectivity.side_effect = OSError("neo4j unreachable")
    monkeypatch.setattr(neo4j.GraphDatabase, "driver", lambda *a, **k: fake_driver)

    resp = client.get("/readiness")

    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"
    fake_driver.close.assert_called_once()


def test_neo4j_unset_reports_not_configured_and_ready(client, monkeypatch, _postgres_ok, _redis_unset):
    monkeypatch.delenv("NEO4J_URI", raising=False)

    resp = client.get("/readiness")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["neo4j"]["status"] == "not_configured"


# ─── WS-6: Neo4j not probed when the graph subsystem is disabled ─────────────
# In production the graph routers are auto-disabled (experimental), but
# NEO4J_URI is still set for the best-effort admin mirror. The readiness
# probe must NOT reach out to Neo4j in that state — probing a mirror no
# mounted route serves only adds healthcheck latency and would flip the
# deploy-gating payload to ``degraded`` on a blip. Report ``not_probed``.


def test_neo4j_not_probed_when_graph_subsystem_disabled(client, monkeypatch, _postgres_ok, _redis_unset):
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j.prod:7687")
    monkeypatch.setattr(main, "_subsystem_active", lambda name: name != "graph")

    # If the probe touches Neo4j at all this would raise and surface as error.
    def _boom(*args, **kwargs):
        raise AssertionError("Neo4j must not be probed when graph is disabled")

    monkeypatch.setattr(neo4j.GraphDatabase, "driver", _boom)

    resp = client.get("/readiness")

    assert resp.status_code == 200
    body = resp.json()
    # not_probed is informational — overall stays ready, never degraded.
    assert body["status"] == "ready"
    assert body["checks"]["neo4j"]["status"] == "not_probed"
    assert body["checks"]["neo4j"]["reason"] == "graph subsystem disabled"


def test_neo4j_probed_when_graph_subsystem_active(client, monkeypatch, _postgres_ok, _redis_unset):
    """Symmetric guard: when graph IS active, the probe runs (existing tests
    rely on the non-prod default; this pins the branch explicitly)."""
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j.example:7687")
    monkeypatch.setattr(main, "_subsystem_active", lambda name: True)
    monkeypatch.setattr(neo4j.GraphDatabase, "driver", lambda *a, **k: MagicMock())

    resp = client.get("/readiness")

    assert resp.status_code == 200
    assert resp.json()["checks"]["neo4j"]["status"] == "ok"


def test_postgres_down_returns_503(client, monkeypatch, _redis_unset):
    """Postgres failures remain fatal regardless of the optional components."""
    # Configured-but-unreachable (env_defaults deliberately sets no URL).
    url = "postgresql://probe:probe@localhost:5432/readiness_probe"  # pragma: allowlist secret
    monkeypatch.setenv("DATABASE_URL", url)

    def _pg_down(*args, **kwargs):
        raise ConnectionError("postgres down")

    monkeypatch.setattr(sqlalchemy, "create_engine", _pg_down)
    monkeypatch.delenv("NEO4J_URI", raising=False)

    resp = client.get("/readiness")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["postgres"]["status"] == "error"


def test_missing_database_url_returns_503(client, monkeypatch, _redis_unset):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("NEO4J_URI", raising=False)

    resp = client.get("/readiness")

    assert resp.status_code == 503
    assert resp.json()["checks"]["postgres"]["status"] == "not_configured"


# ─── #2518: background-runner readiness signals ─────────────────────────────


class _LiveThread:
    @staticmethod
    def is_alive() -> bool:
        return True


class _DeadThread:
    @staticmethod
    def is_alive() -> bool:
        return False


def _client_with_state(**state) -> TestClient:
    """Mount /readiness on an app whose app.state carries runner flags."""
    app = FastAPI()
    for key, value in state.items():
        setattr(app.state, key, value)
    app.add_api_route("/readiness", main.readiness, methods=["GET"])
    return TestClient(app)


def test_runners_ok_when_started_and_alive(monkeypatch, _postgres_ok, _redis_unset):
    """Both runners up cleanly -> ready, with worker/scheduler reporting ok."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    client = _client_with_state(
        ingestion_worker_started=True,
        ingestion_worker_thread=_LiveThread(),
        embedded_scheduler_started=True,
        embedded_scheduler=object(),
    )

    resp = client.get("/readiness")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["worker"]["status"] == "ok"
    assert body["checks"]["scheduler"]["status"] == "ok"


def test_worker_start_failure_returns_503(monkeypatch, _postgres_ok, _redis_unset):
    """E07: swallowed ingestion-worker start failure fails readiness (503)."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    client = _client_with_state(
        ingestion_worker_started=False,
        ingestion_worker_thread=None,
        embedded_scheduler_started=True,
        embedded_scheduler=object(),
    )

    resp = client.get("/readiness")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["worker"]["status"] == "error"
    assert body["checks"]["postgres"]["status"] == "ok"


def test_worker_dead_thread_returns_503(monkeypatch, _postgres_ok, _redis_unset):
    """E07: started but the loop thread died -> worker=error and 503."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    client = _client_with_state(
        ingestion_worker_started=True,
        ingestion_worker_thread=_DeadThread(),
        embedded_scheduler_started=True,
        embedded_scheduler=object(),
    )

    resp = client.get("/readiness")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["worker"]["status"] == "error"


def test_scheduler_disabled_is_healthy(monkeypatch, _postgres_ok, _redis_unset):
    """A None scheduler runner after a successful start is the *intended*
    disabled state (SCHEDULER_EMBEDDED=0), not a failure -> scheduler=disabled,
    overall stays ready (scheduler is not essential when disabled)."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.setenv("SCHEDULER_EMBEDDED", "0")
    client = _client_with_state(
        ingestion_worker_started=True,
        ingestion_worker_thread=_LiveThread(),
        embedded_scheduler_started=True,
        embedded_scheduler=None,
    )

    resp = client.get("/readiness")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["scheduler"]["status"] == "disabled"


def test_scheduler_start_failure_returns_503_when_embedded(monkeypatch, _postgres_ok, _redis_unset):
    """E07: raised embedded-scheduler start -> 503 when SCHEDULER_EMBEDDED=1."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.setenv("SCHEDULER_EMBEDDED", "1")
    client = _client_with_state(
        ingestion_worker_started=True,
        ingestion_worker_thread=_LiveThread(),
        embedded_scheduler_started=False,
        embedded_scheduler=None,
    )

    resp = client.get("/readiness")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["scheduler"]["status"] == "error"


def test_scheduler_start_failure_degrades_when_not_embedded(monkeypatch, _postgres_ok, _redis_unset):
    """Scheduler error is non-essential when SCHEDULER_EMBEDDED=0 -> 200/degraded."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.setenv("SCHEDULER_EMBEDDED", "0")
    client = _client_with_state(
        ingestion_worker_started=True,
        ingestion_worker_thread=_LiveThread(),
        embedded_scheduler_started=False,
        embedded_scheduler=None,
    )

    resp = client.get("/readiness")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["scheduler"]["status"] == "error"


def test_worker_and_postgres_down_both_reported_as_503(monkeypatch, _redis_unset):
    """Postgres-down and worker-down both fail readiness; both appear in checks."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    # Configured-but-unreachable (env_defaults deliberately sets no URL).
    url = "postgresql://probe:probe@localhost:5432/readiness_probe"  # pragma: allowlist secret
    monkeypatch.setenv("DATABASE_URL", url)

    def _pg_down(*args, **kwargs):
        raise ConnectionError("postgres down")

    monkeypatch.setattr(sqlalchemy, "create_engine", _pg_down)
    client = _client_with_state(
        ingestion_worker_started=False,
        ingestion_worker_thread=None,
        embedded_scheduler_started=True,
        embedded_scheduler=object(),
    )

    resp = client.get("/readiness")

    assert resp.status_code == 503
    assert resp.json()["checks"]["postgres"]["status"] == "error"
    assert resp.json()["checks"]["worker"]["status"] == "error"


def test_minimal_app_without_state_reports_not_configured(monkeypatch, _postgres_ok, _redis_unset):
    """Mounted on a bare app (no lifespan) -> runners reported not_configured,
    not error, so existing minimal-app tests stay ready."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    app = FastAPI()
    app.add_api_route("/readiness", main.readiness, methods=["GET"])
    resp = TestClient(app).get("/readiness")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["worker"]["status"] == "not_configured"
    assert body["checks"]["scheduler"]["status"] == "not_configured"


def test_scheduler_dead_thread_returns_503_when_embedded(monkeypatch, _postgres_ok, _redis_unset):
    """#2697 / E07: dead scheduler thread fails readiness when embedded is on."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.setenv("SCHEDULER_EMBEDDED", "1")

    class _DeadRunner:
        thread_alive = False

    client = _client_with_state(
        ingestion_worker_started=True,
        ingestion_worker_thread=_LiveThread(),
        embedded_scheduler_started=True,
        embedded_scheduler=_DeadRunner(),
    )

    resp = client.get("/readiness")

    assert resp.status_code == 503
    body = resp.json()
    assert body["checks"]["scheduler"]["status"] == "error"
    assert "not alive" in body["checks"]["scheduler"]["error"]
    assert body["status"] == "not_ready"


def test_scheduler_dead_thread_degrades_when_not_embedded(monkeypatch, _postgres_ok, _redis_unset):
    """Dead scheduler thread only degrades when SCHEDULER_EMBEDDED=0."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.setenv("SCHEDULER_EMBEDDED", "0")

    class _DeadRunner:
        thread_alive = False

    client = _client_with_state(
        ingestion_worker_started=True,
        ingestion_worker_thread=_LiveThread(),
        embedded_scheduler_started=True,
        embedded_scheduler=_DeadRunner(),
    )

    resp = client.get("/readiness")

    assert resp.status_code == 200
    body = resp.json()
    assert body["checks"]["scheduler"]["status"] == "error"
    assert body["status"] == "degraded"


def test_scheduler_live_thread_is_ok(monkeypatch, _postgres_ok, _redis_unset):
    monkeypatch.delenv("NEO4J_URI", raising=False)

    class _LiveRunner:
        thread_alive = True

    client = _client_with_state(
        ingestion_worker_started=True,
        ingestion_worker_thread=_LiveThread(),
        embedded_scheduler_started=True,
        embedded_scheduler=_LiveRunner(),
    )

    resp = client.get("/readiness")

    assert resp.status_code == 200
    assert resp.json()["checks"]["scheduler"]["status"] == "ok"


def test_rate_limiter_memory_in_prod_with_missing_redis_is_not_ready(monkeypatch, _postgres_ok, _redis_unset):
    """#2711: production on memory:// slowapi storage must be visible."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    import shared.env as env_mod
    import shared.rate_limit as rl_mod

    monkeypatch.setattr(rl_mod, "slowapi_storage_backend", lambda: "memory")
    monkeypatch.setattr(env_mod, "is_production", lambda: True)

    client = _client_with_state(
        ingestion_worker_started=True,
        ingestion_worker_thread=_LiveThread(),
        embedded_scheduler_started=True,
        embedded_scheduler=object(),
    )
    resp = client.get("/readiness")

    assert resp.status_code == 503  # Redis is required in production.
    body = resp.json()
    assert body["checks"]["rate_limiter"]["status"] == "error"
    assert body["status"] == "not_ready"


def test_rate_limiter_redis_backend_is_ok(monkeypatch, _postgres_ok, _redis_unset):
    monkeypatch.delenv("NEO4J_URI", raising=False)
    import shared.rate_limit as rl_mod

    monkeypatch.setattr(rl_mod, "slowapi_storage_backend", lambda: "redis")

    client = _client_with_state(
        ingestion_worker_started=True,
        ingestion_worker_thread=_LiveThread(),
        embedded_scheduler_started=True,
        embedded_scheduler=object(),
    )
    resp = client.get("/readiness")

    assert resp.status_code == 200
    assert resp.json()["checks"]["rate_limiter"] == {"status": "ok", "backend": "redis"}


def test_rate_limiter_memory_outside_prod_is_ok(monkeypatch, _postgres_ok, _redis_unset):
    monkeypatch.delenv("NEO4J_URI", raising=False)
    import shared.env as env_mod
    import shared.rate_limit as rl_mod

    monkeypatch.setattr(rl_mod, "slowapi_storage_backend", lambda: "memory")
    monkeypatch.setattr(env_mod, "is_production", lambda: False)

    client = _client_with_state(
        ingestion_worker_started=True,
        ingestion_worker_thread=_LiveThread(),
        embedded_scheduler_started=True,
        embedded_scheduler=object(),
    )
    resp = client.get("/readiness")

    assert resp.status_code == 200
    assert resp.json()["checks"]["rate_limiter"]["status"] == "ok"


@pytest.mark.parametrize("configured", [True, False])
def test_strict_runtime_requires_redis(client, monkeypatch, _postgres_ok, configured):
    import redis
    import shared.env as env

    monkeypatch.setattr(env, "requires_strict_auth_runtime", lambda: True)
    monkeypatch.delenv("NEO4J_URI", raising=False)
    if configured:
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        connection = MagicMock()
        connection.ping.side_effect = redis.TimeoutError("secret-host-or-password")
        monkeypatch.setattr(redis, "from_url", lambda *a, **k: connection)
    else:
        monkeypatch.delenv("REDIS_URL", raising=False)
    response = client.get("/readiness")
    assert response.status_code == 503
    assert "secret-host-or-password" not in response.text
    if configured:
        connection.close.assert_called_once()


def test_redis_read_timeout_and_no_retries(client, monkeypatch, _postgres_ok):
    import redis

    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.delenv("NEO4J_URI", raising=False)
    factory = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(redis, "from_url", factory)
    assert client.get("/readiness").status_code == 200
    kwargs = factory.call_args.kwargs
    assert kwargs["socket_timeout"] == 2
    assert kwargs["socket_connect_timeout"] == 2
    assert kwargs["retry"].get_retries() == 0


def test_postgres_timeout_and_disposal_on_error(client, monkeypatch, _postgres_ok, _redis_unset):
    engine = MagicMock()
    engine.connect.side_effect = ConnectionError("private-connection-details")
    factory = MagicMock(return_value=engine)
    monkeypatch.setattr(sqlalchemy, "create_engine", factory)
    monkeypatch.delenv("NEO4J_URI", raising=False)
    response = client.get("/readiness")
    assert response.status_code == 503
    assert "private-connection-details" not in response.text
    assert factory.call_args.kwargs["connect_args"] == {
        "connect_timeout": 2,
        "options": "-c statement_timeout=2000",
    }
    engine.dispose.assert_called_once()


def test_stalled_probe_is_bounded_and_does_not_block_liveness(monkeypatch):
    import asyncio
    import threading

    import httpx

    started = threading.Event()
    release = threading.Event()

    def stalled_probe(request):
        started.set()
        release.wait(timeout=2)
        return {"status": "ready"}

    monkeypatch.setattr(main, "_readiness_checks", stalled_probe)
    monkeypatch.setattr(main, "_READINESS_TIMEOUT_SECONDS", 0.1)
    app = FastAPI()
    app.add_api_route("/readiness", main.readiness, methods=["GET"])

    @app.get("/health")
    async def health():
        return {"status": "alive"}

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            probe = asyncio.create_task(client.get("/readiness"))
            try:
                for _ in range(100):
                    if started.is_set():
                        break
                    await asyncio.sleep(0.001)
                assert started.is_set()
                live = await asyncio.wait_for(client.get("/health"), timeout=0.05)
                assert live.status_code == 200
                response = await asyncio.wait_for(probe, timeout=0.5)
                assert response.status_code == 503
                assert response.json()["checks"]["probe"]["error"] == "dependency probe timed out"
            finally:
                release.set()
                await probe

    asyncio.run(exercise())


@pytest.mark.parametrize("cancel_request", [False, True])
def test_timed_out_or_cancelled_probes_retain_bounded_capacity(monkeypatch, cancel_request):
    import asyncio
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import httpx

    release = threading.Event()
    calls = []

    def stalled_probe(request):
        calls.append(request)
        release.wait(timeout=3)
        return {"status": "ready"}

    monkeypatch.setattr(main, "_readiness_checks", stalled_probe)
    monkeypatch.setattr(main, "_READINESS_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(main, "_READINESS_SLOTS", threading.BoundedSemaphore(2))
    app = FastAPI()
    app.add_api_route("/readiness", main.readiness, methods=["GET"])

    @app.get("/health")
    async def health():
        return {"status": "alive"}

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            probes = [asyncio.create_task(client.get("/readiness")) for _ in range(2)]
            try:
                for _ in range(100):
                    if len(calls) == 2:
                        break
                    await asyncio.sleep(0.001)
                assert len(calls) == 2
                if cancel_request:
                    for probe in probes:
                        probe.cancel()
                    await asyncio.gather(*probes, return_exceptions=True)
                else:
                    responses = await asyncio.gather(*probes)
                    assert all(response.status_code == 503 for response in responses)
                # Neither deadline nor caller cancellation releases driver slots.
                responses = await asyncio.wait_for(
                    asyncio.gather(*(client.get("/readiness") for _ in range(40))),
                    timeout=0.5,
                )
                assert all(response.status_code == 503 for response in responses)
                assert all("capacity exhausted" in response.text for response in responses)
                assert len(calls) == 2
                assert (await client.get("/health")).status_code == 200
                release.set()
                # Completion of the underlying drivers releases admission again.
                for _ in range(100):
                    response = await client.get("/readiness")
                    if response.status_code == 200:
                        break
                    await asyncio.sleep(0.001)
                assert response.status_code == 200
            finally:
                release.set()
                await asyncio.gather(*probes, return_exceptions=True)

    with ThreadPoolExecutor(max_workers=2) as executor:
        monkeypatch.setattr(main, "_READINESS_EXECUTOR", executor)
        asyncio.run(exercise())


def test_e07_neo4j_error_stays_non_blocking(monkeypatch, _postgres_ok, _redis_unset):
    """E07: Neo4j stays non-blocking even when essential units are healthy."""
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j.invalid:7687")
    monkeypatch.setenv("SCHEDULER_EMBEDDED", "1")
    monkeypatch.setattr(
        neo4j.GraphDatabase,
        "driver",
        lambda *a, **k: (_ for _ in ()).throw(OSError("connection refused")),
    )
    client = _client_with_state(
        ingestion_worker_started=True,
        ingestion_worker_thread=_LiveThread(),
        embedded_scheduler_started=True,
        embedded_scheduler=object(),
    )

    resp = client.get("/readiness")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["neo4j"]["status"] == "error"
    assert body["checks"]["worker"]["status"] == "ok"


def test_e07_rate_limiter_error_alone_stays_non_blocking(monkeypatch, _postgres_ok, _redis_unset):
    """E07: rate_limiter error alone never flips readiness to 503."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    import shared.env as env_mod
    import shared.rate_limit as rl_mod

    monkeypatch.setattr(rl_mod, "slowapi_storage_backend", lambda: "memory")
    # Force the rate-limiter error path without making Redis required.
    monkeypatch.setattr(env_mod, "is_production", lambda: True)
    monkeypatch.setattr(env_mod, "requires_strict_auth_runtime", lambda: False)

    client = _client_with_state(
        ingestion_worker_started=True,
        ingestion_worker_thread=_LiveThread(),
        embedded_scheduler_started=True,
        embedded_scheduler=object(),
    )
    resp = client.get("/readiness")

    assert resp.status_code == 200
    body = resp.json()
    assert body["checks"]["rate_limiter"]["status"] == "error"
    assert body["status"] == "degraded"


def test_e07_readiness_recovers_to_200_after_restart(monkeypatch, _postgres_ok, _redis_unset):
    """E07: after a failed essential unit, a healthy restart returns 200."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.setenv("SCHEDULER_EMBEDDED", "1")

    failed = _client_with_state(
        ingestion_worker_started=False,
        ingestion_worker_thread=None,
        embedded_scheduler_started=False,
        embedded_scheduler=None,
    )
    failed_resp = failed.get("/readiness")
    assert failed_resp.status_code == 503
    assert failed_resp.json()["status"] == "not_ready"

    class _LiveRunner:
        thread_alive = True

    recovered = _client_with_state(
        ingestion_worker_started=True,
        ingestion_worker_thread=_LiveThread(),
        embedded_scheduler_started=True,
        embedded_scheduler=_LiveRunner(),
    )
    recovered_resp = recovered.get("/readiness")
    assert recovered_resp.status_code == 200
    body = recovered_resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["worker"]["status"] == "ok"
    assert body["checks"]["scheduler"]["status"] == "ok"


def test_e07_liveness_unaffected_when_essential_unit_fails(monkeypatch, _postgres_ok, _redis_unset):
    """E07: /health stays 200 while /readiness is 503 for an essential failure.

    Keeps Railway from coupling liveness to background-unit death (no restart
    loop driven by a combined probe).
    """
    monkeypatch.delenv("NEO4J_URI", raising=False)
    app = FastAPI()
    app.state.ingestion_worker_started = False
    app.state.ingestion_worker_thread = None
    app.state.embedded_scheduler_started = True
    app.state.embedded_scheduler = object()
    app.add_api_route("/readiness", main.readiness, methods=["GET"])

    @app.get("/health")
    async def health():
        return {"status": "alive"}

    client = TestClient(app)
    assert client.get("/readiness").status_code == 503
    live = client.get("/health")
    assert live.status_code == 200
    assert live.json()["status"] == "alive"
