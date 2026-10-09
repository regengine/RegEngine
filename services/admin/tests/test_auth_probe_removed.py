"""The test-named RBAC probe must not ship in the production auth router."""

from __future__ import annotations

from fastapi import FastAPI
from starlette.testclient import TestClient

from services.admin.app import auth_routes


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_routes.router)
    return app


def test_check_permission_route_not_registered():
    paths = [getattr(route, "path", "") for route in auth_routes.router.routes]
    assert "/auth/check-permission" not in paths


def test_check_permission_returns_404():
    response = TestClient(_app()).get("/auth/check-permission")
    assert response.status_code == 404
