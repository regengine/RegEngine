"""Readiness probe contract for the consolidated monolith (server/main.py).

railway.toml uses healthcheckPath=/readiness, so this endpoint gates deploys
and restarts:

* Postgres down or unconfigured -> 503 (fatal; instance cannot serve traffic).
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
    assert "connection refused" in body["checks"]["neo4j"]["error"]


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


def test_worker_start_failure_degrades_but_stays_200(monkeypatch, _postgres_ok, _redis_unset):
    """A swallowed ingestion-worker start failure surfaces as worker=error and
    degrades the payload — but /readiness stays 200 (not 503), so a background
    failure does not block deploys the way postgres-down does (#2518)."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    client = _client_with_state(
        ingestion_worker_started=False,
        ingestion_worker_thread=None,
        embedded_scheduler_started=True,
        embedded_scheduler=object(),
    )

    resp = client.get("/readiness")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["worker"]["status"] == "error"
    # postgres-down is the only 503 path; confirm worker-down is NOT one.
    assert body["checks"]["postgres"]["status"] == "ok"


def test_worker_dead_thread_is_error(monkeypatch, _postgres_ok, _redis_unset):
    """Started but the loop thread died -> worker=error/degraded."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
    client = _client_with_state(
        ingestion_worker_started=True,
        ingestion_worker_thread=_DeadThread(),
        embedded_scheduler_started=True,
        embedded_scheduler=object(),
    )

    resp = client.get("/readiness")

    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"
    assert resp.json()["checks"]["worker"]["status"] == "error"


def test_scheduler_disabled_is_healthy(monkeypatch, _postgres_ok, _redis_unset):
    """A None scheduler runner after a successful start is the *intended*
    disabled state (SCHEDULER_EMBEDDED=0), not a failure -> scheduler=disabled,
    overall stays ready."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
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


def test_scheduler_start_failure_degrades(monkeypatch, _postgres_ok, _redis_unset):
    """A raised embedded-scheduler start -> scheduler=error/degraded (200)."""
    monkeypatch.delenv("NEO4J_URI", raising=False)
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


def test_worker_down_distinguished_from_postgres_down(monkeypatch, _redis_unset):
    """The required-vs-optional contract: postgres-down is 503, worker-down is
    200/degraded. Same probe, different severity (#2518)."""
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

    # postgres-down dominates -> 503 regardless of the worker signal.
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


def test_scheduler_dead_thread_is_error(monkeypatch, _postgres_ok, _redis_unset):
    """#2697: a scheduler runner whose daemon thread died after a successful
    start must degrade the payload instead of reporting ok forever."""
    monkeypatch.delenv("NEO4J_URI", raising=False)

    class _DeadRunner:
        thread_alive = False

    client = _client_with_state(
        ingestion_worker_started=True,
        ingestion_worker_thread=_LiveThread(),
        embedded_scheduler_started=True,
        embedded_scheduler=_DeadRunner(),
    )

    resp = client.get("/readiness")

    assert resp.status_code == 200  # degraded, never 503 (documented contract)
    body = resp.json()
    assert body["checks"]["scheduler"]["status"] == "error"
    assert "not alive" in body["checks"]["scheduler"]["error"]
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


def test_rate_limiter_memory_in_prod_degrades(monkeypatch, _postgres_ok, _redis_unset):
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

    assert resp.status_code == 200  # degraded, never 503
    body = resp.json()
    assert body["checks"]["rate_limiter"]["status"] == "error"
    assert body["status"] == "degraded"


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
