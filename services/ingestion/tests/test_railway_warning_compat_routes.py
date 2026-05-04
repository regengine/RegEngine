"""Compatibility routes that keep production probes out of warning logs."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.fsma_readiness_compat import router as fsma_readiness_compat_router
from app.routes_health_metrics import router as health_metrics_router
from app.stripe_billing.routes import list_plans


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(health_metrics_router)
    app.include_router(fsma_readiness_compat_router)

    @app.get("/billing/plans")
    async def list_billing_plans_compat():
        return await list_plans()

    return TestClient(app)


def test_health_aliases_return_liveness_payload() -> None:
    client = _client()

    for path in ("/healthz", "/api/health"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()["status"] in {"healthy", "degraded"}


def test_billing_plans_compat_path_returns_plans() -> None:
    response = _client().get("/billing/plans")

    assert response.status_code == 200
    assert response.json()["plans"]


def test_fsma_customer_readiness_compat_paths_are_explicitly_not_connected() -> None:
    client = _client()

    export_jobs = client.get("/api/v1/fsma/export-jobs")
    mappings = client.get("/api/v1/fsma/mappings")

    assert export_jobs.status_code == 200
    assert export_jobs.json()["meta"]["status"] == "not_connected"
    assert mappings.status_code == 200
    assert mappings.json()["meta"]["status"] == "not_connected"
