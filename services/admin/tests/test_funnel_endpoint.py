"""Tests for the admin funnel metrics endpoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Previously imported services.admin.main, which eagerly initialized the
# Postgres pool at module load and broke any test host without a running
# local Postgres. Build a minimal FastAPI app around just the v1_router
# so the endpoint is exercisable with in-memory mocks.
from app import routes as routes_mod


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(routes_mod.v1_router)
    return app


def test_admin_funnel_endpoint_returns_stage_metrics(monkeypatch) -> None:
    app = _build_app()

    def _override_session():
        yield object()

    app.dependency_overrides[routes_mod.require_funnel_read] = lambda: None
    app.dependency_overrides[routes_mod.get_session] = _override_session

    monkeypatch.setattr(
        routes_mod,
        "get_funnel_stage_metrics",
        lambda db_session=None: [
            {"name": "signup_completed", "count": 10, "conversion_from_previous_pct": 100.0},
            {"name": "first_ingest", "count": 6, "conversion_from_previous_pct": 60.0},
            {"name": "first_scan", "count": 4, "conversion_from_previous_pct": 66.67},
            {"name": "first_nlp_query", "count": 3, "conversion_from_previous_pct": 75.0},
            {"name": "checkout_started", "count": 2, "conversion_from_previous_pct": 66.67},
            {"name": "payment_completed", "count": 1, "conversion_from_previous_pct": 50.0},
        ],
    )

    with TestClient(app) as client:
        response = client.get("/v1/admin/funnel")

    assert response.status_code == 200
    body = response.json()
    assert body["stages"][0]["name"] == "signup_completed"
    assert body["stages"][-1]["name"] == "payment_completed"
    assert body["stages"][-1]["count"] == 1


def test_admin_funnel_endpoint_requires_auth_by_default() -> None:
    app = _build_app()

    with TestClient(app) as client:
        response = client.get("/v1/admin/funnel")

    assert response.status_code in {401, 403}
