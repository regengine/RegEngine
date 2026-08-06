"""Tests for /system/status honesty in the consolidated (Railway) topology.

Regression coverage for #2750: the former ingestion/compliance standalone
services are now mounted in THIS FastAPI process, so the old loopback
``/health`` self-check was a tautology — it returned 200 whenever the app
could answer at all, so ingestion/compliance could NEVER be reported
unhealthy even when a real downstream dependency was down.

The fix reports the in-process routers explicitly and backs their status
with a real DB ``SELECT 1`` probe (plus a Redis PING when configured). These
tests assert that when the DB dependency is unavailable, /system/status is
no longer tautologically green.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_sysadmin = True
    return user


def _build_app(user: MagicMock, db) -> FastAPI:
    from services.admin.app.dependencies import get_current_user, get_session
    from services.admin.app.system_routes import router

    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: db
    return app


def _railway_env(monkeypatch) -> None:
    """Simulate the consolidated Railway deployment with no remote peers."""
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    # Ensure ingestion/compliance are treated as in-process, not remote.
    monkeypatch.delenv("INGESTION_SERVICE_URL", raising=False)
    monkeypatch.delenv("COMPLIANCE_SERVICE_URL", raising=False)
    monkeypatch.delenv("GRAPH_SERVICE_URL", raising=False)
    # Redis is optional — leave it unconfigured so no ping is attempted.
    monkeypatch.delenv("REDIS_URL", raising=False)


def test_status_reports_in_process_routers_when_db_healthy(monkeypatch) -> None:
    _railway_env(monkeypatch)

    db = MagicMock()
    db.execute.return_value = MagicMock()  # SELECT 1 succeeds

    client = TestClient(_build_app(_make_user(), db))
    resp = client.get("/v1/system/status")

    assert resp.status_code == 200
    body = resp.json()
    by_name = {s["name"]: s for s in body["services"]}

    # The consolidated routers are reported and marked as in-process.
    assert set(by_name) >= {"ingestion", "compliance"}
    for name in ("ingestion", "compliance"):
        entry = by_name[name]
        assert entry["status"] == "healthy"
        assert entry["details"]["mode"] == "in-process (consolidated)"
        assert entry["details"]["database"] == "ok"

    assert body["overall_status"] == "healthy"
    # A real DB probe ran — proving the status is NOT a loopback self-check.
    assert db.execute.called


def test_status_goes_unhealthy_when_db_down(monkeypatch) -> None:
    """The core regression: DB dependency down => ingestion/compliance
    unhealthy and overall degraded. Previously this was tautologically
    green because the loopback self-check always saw the app answer."""
    _railway_env(monkeypatch)

    db = MagicMock()
    db.execute.side_effect = RuntimeError("DB pool exhausted")

    client = TestClient(_build_app(_make_user(), db))
    resp = client.get("/v1/system/status")

    assert resp.status_code == 200
    body = resp.json()
    by_name = {s["name"]: s for s in body["services"]}

    for name in ("ingestion", "compliance"):
        entry = by_name[name]
        assert entry["status"] == "unhealthy", f"{name} should reflect DB outage"
        assert entry["details"]["mode"] == "in-process (consolidated)"
        assert "error" in entry["details"]["database"]

    # No longer tautologically green.
    assert body["overall_status"] == "degraded"


def test_status_does_not_self_http_check_loopback(monkeypatch) -> None:
    """In the consolidated topology, no HTTP health check is issued for the
    in-process routers — their status derives from the DB probe only."""
    _railway_env(monkeypatch)

    import services.admin.app.system_routes as system_routes

    # _get_service_urls must not emit loopback ingestion/compliance URLs.
    urls = system_routes._get_service_urls()
    assert "ingestion" not in urls
    assert "compliance" not in urls

    # If any HTTP check WERE issued it would blow up here.
    def _boom(*args, **kwargs):  # pragma: no cover - guard
        raise AssertionError("check_service_health must not run for in-process routers")

    monkeypatch.setattr(system_routes, "check_service_health", _boom)

    db = MagicMock()
    db.execute.return_value = MagicMock()
    client = TestClient(_build_app(_make_user(), db))
    resp = client.get("/v1/system/status")

    assert resp.status_code == 200
    assert db.execute.called
