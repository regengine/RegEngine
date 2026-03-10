"""Tests for the admin funnel metrics endpoint."""

from __future__ import annotations

import sys

from fastapi.testclient import TestClient

from services.admin.main import app as admin_app


def test_admin_funnel_endpoint_returns_stage_metrics(monkeypatch) -> None:
    routes_mod = sys.modules.get("app.routes") or sys.modules.get("services.admin.app.routes")
    assert routes_mod is not None

    def _override_session():
        yield object()

    admin_app.dependency_overrides[routes_mod.require_funnel_read] = lambda: None
    admin_app.dependency_overrides[routes_mod.get_session] = _override_session

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

    try:
        with TestClient(admin_app) as client:
            response = client.get("/v1/admin/funnel")

        assert response.status_code == 200
        body = response.json()
        assert body["stages"][0]["name"] == "signup_completed"
        assert body["stages"][-1]["name"] == "payment_completed"
        assert body["stages"][-1]["count"] == 1
    finally:
        admin_app.dependency_overrides.pop(routes_mod.require_funnel_read, None)
        admin_app.dependency_overrides.pop(routes_mod.get_session, None)


def test_admin_funnel_endpoint_requires_auth_by_default() -> None:
    with TestClient(admin_app) as client:
        response = client.get("/v1/admin/funnel")

    assert response.status_code in {401, 403}
