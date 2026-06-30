"""Readiness probe contract for the consolidated monolith (server/main.py).

railway.toml uses healthcheckPath=/readiness, so this endpoint gates deploys
and restarts:

* Postgres down or unconfigured -> 503 (fatal; instance cannot serve traffic).
* Neo4j down -> 200 with overall status ``degraded`` and the component
  reported in ``checks`` (optional graph mirror; must never block a deploy).
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
    """DATABASE_URL is set by tests/env_defaults.py; fake the engine so the
    check passes without a live Postgres."""
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


def test_postgres_down_returns_503(client, monkeypatch, _redis_unset):
    """Postgres failures remain fatal regardless of the optional components."""

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
