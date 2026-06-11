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
