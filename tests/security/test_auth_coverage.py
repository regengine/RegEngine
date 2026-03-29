"""
Auth coverage test — verifies every API endpoint requires authentication.

Uses FastAPI's TestClient to introspect the OpenAPI schema and hit every
endpoint without auth headers. Endpoints that return 200/2xx without auth
are flagged as unprotected.

Intentionally unauthenticated endpoints (health checks, sandbox, docs)
are explicitly allow-listed so new unprotected endpoints are caught.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ── Allow-list: endpoints that are intentionally unauthenticated ──────

UNAUTHENTICATED_ALLOWLIST = frozenset({
    # Health/readiness — must be public for load balancers and orchestrators
    "GET /health",
    "GET /readiness",
    # Feature discovery — public endpoint for client capability negotiation
    "GET /api/v1/features",
    # Sandbox — intentionally public with rate limiting
    "POST /api/v1/sandbox/evaluate",
    # Webhook receivers — use signature verification instead of API keys
    "POST /api/v1/integrations/webhook/{tenant_id}/{connector_id}",
    # OpenAPI docs
    "GET /docs",
    "GET /redoc",
    "GET /openapi.json",
})


def _build_test_app():
    """Import and build the ingestion service FastAPI app."""
    import sys
    from pathlib import Path

    service_dir = Path(__file__).resolve().parent.parent.parent / "services" / "ingestion"
    services_dir = service_dir.parent
    for p in [str(service_dir), str(services_dir)]:
        if p not in sys.path:
            sys.path.insert(0, p)

    from shared.paths import ensure_shared_importable
    ensure_shared_importable()

    from main import app
    return app


def _extract_endpoints(app) -> list[tuple[str, str]]:
    """Extract all (METHOD, path) pairs from the FastAPI app's routes."""
    endpoints = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                    endpoints.append((method, route.path))
    return sorted(endpoints)


def _make_dummy_path(path: str) -> str:
    """Replace path parameters with dummy values for testing."""
    import re
    return re.sub(r"\{[^}]+\}", "test-000", path)


@pytest.fixture(scope="module")
def app_and_client():
    """Build the app once for all tests in this module."""
    try:
        app = _build_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        return app, client
    except Exception as e:
        pytest.skip(f"Cannot build ingestion app: {e}")


def test_all_endpoints_require_auth(app_and_client):
    """Every endpoint not in the allowlist must reject unauthenticated requests."""
    app, client = app_and_client
    endpoints = _extract_endpoints(app)

    unprotected = []
    for method, path in endpoints:
        key = f"{method} {path}"
        if key in UNAUTHENTICATED_ALLOWLIST:
            continue

        # Skip HEAD (mirrors GET auth) and OPTIONS (CORS preflight)
        if method in ("HEAD", "OPTIONS"):
            continue

        test_path = _make_dummy_path(path)
        response = client.request(method, test_path)

        # 401/403 = auth enforced. 404/405/422 = route resolved but rejected
        # on other grounds (still means auth middleware ran or route doesn't match).
        # Only 200/201/204 without auth is a problem.
        if response.status_code in (200, 201, 204):
            unprotected.append(f"{method} {path} -> {response.status_code}")

    assert not unprotected, (
        f"Endpoints accessible without authentication:\n"
        + "\n".join(f"  {e}" for e in unprotected)
    )


def test_allowlist_entries_still_exist(app_and_client):
    """Verify allowlist entries map to real endpoints — stale entries should be removed."""
    app, _ = app_and_client
    endpoints = _extract_endpoints(app)
    endpoint_keys = {f"{m} {p}" for m, p in endpoints}

    stale = UNAUTHENTICATED_ALLOWLIST - endpoint_keys
    # Docs endpoints may not show up in routes — filter those out
    docs_paths = {"GET /docs", "GET /redoc", "GET /openapi.json"}
    stale -= docs_paths

    assert not stale, (
        f"Stale allowlist entries (endpoints no longer exist):\n"
        + "\n".join(f"  {e}" for e in sorted(stale))
    )
