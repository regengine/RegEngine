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
    # Service root and liveness aliases — public for platform probes
    "GET /",
    # Health/readiness — must be public for load balancers and orchestrators
    "GET /health",
    "GET /api/health",
    # Feature discovery — public endpoint for client capability negotiation
    "GET /api/v1/features",
    # Public/static compatibility and reference data — no tenant data returned
    "GET /api/v1/billing/plans",
    "GET /api/v1/fsma/export-jobs",
    "GET /api/v1/fsma/mappings",
    "GET /api/v1/onboarding/steps",
    "GET /api/v1/products/categories/ftl",
    "GET /api/v1/team/roles/definitions",
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
    """Import and build the ingestion service FastAPI app.

    Assumes auth-related environment variables are already configured by the
    ``app_and_client`` fixture so the enforced-auth path is active. The shared
    test env sets ``REGENGINE_ENV=test`` (tests/env_defaults.py), which would
    otherwise activate the ``dev_open`` auth fallback in
    ``authz.get_ingestion_principal`` and authenticate every request, making
    this coverage test vacuous. The settings cache is cleared so the configured
    key is picked up at app build time.
    """
    import sys
    from pathlib import Path

    service_dir = Path(__file__).resolve().parent.parent.parent / "services" / "ingestion"
    services_dir = service_dir.parent
    for p in [str(services_dir), str(service_dir)]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)
    for name in list(sys.modules):
        if name == "main" or name == "app" or name.startswith("app."):
            sys.modules.pop(name, None)

    from shared.paths import ensure_shared_importable
    ensure_shared_importable()

    from app.config import get_settings
    get_settings.cache_clear()

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
    """Build the app once for all tests in this module, with auth enforced.

    Sets ``API_KEY`` so the auth layer rejects unauthenticated requests
    instead of falling through to the ``dev_open`` test fallback, then
    restores the prior environment on teardown so the change does not leak
    into the rest of the test session.
    """
    import os
    import sys

    env_keys = ("API_KEY", "REGENGINE_ENV", "ENV", "AUTH_TEST_BYPASS_TOKEN")
    prev_env = {key: os.environ.get(key) for key in env_keys}
    prev_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "main" or name == "app" or name.startswith("app.")
    }
    prev_sys_path = list(sys.path)
    os.environ["API_KEY"] = "test-auth-coverage-master-key"  # pragma: allowlist secret
    os.environ["REGENGINE_ENV"] = "staging"
    os.environ["ENV"] = "staging"
    os.environ.pop("AUTH_TEST_BYPASS_TOKEN", None)
    try:
        app = _build_test_app()
        client = TestClient(app, raise_server_exceptions=False)
    except Exception as e:
        _restore_test_state(prev_env, prev_modules, prev_sys_path)
        pytest.skip(f"Cannot build ingestion app: {e}")
        return

    try:
        yield app, client
    finally:
        _restore_test_state(prev_env, prev_modules, prev_sys_path)


def _restore_test_state(prev_env, prev_modules, prev_sys_path):
    """Restore auth-related environment and module import state after the module runs."""
    import os
    import sys

    for key, value in prev_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    sys.path[:] = prev_sys_path
    for name in list(sys.modules):
        if name == "main" or name == "app" or name.startswith("app."):
            sys.modules.pop(name, None)
    sys.modules.update(prev_modules)
    for module_name in ("app.config", "services.ingestion.app.config"):
        module = sys.modules.get(module_name)
        get_settings = getattr(module, "get_settings", None)
        cache_clear = getattr(get_settings, "cache_clear", None)
        if cache_clear is not None:
            cache_clear()


def test_all_endpoints_require_auth(app_and_client):
    """Every endpoint not in the allowlist must reject unauthenticated requests."""
    app, client = app_and_client
    endpoints = _extract_endpoints(app)

    # Reset the per-IP auth failure counter between requests. Otherwise, after
    # 15 unauthenticated probes the rate limiter blocks "testclient" and every
    # subsequent endpoint returns 429 — which would mask a genuinely
    # unprotected endpoint behind the block and make this assertion
    # order-dependent.
    from app import authz

    unprotected = []
    for method, path in endpoints:
        key = f"{method} {path}"
        if key in UNAUTHENTICATED_ALLOWLIST:
            continue

        # Skip HEAD (mirrors GET auth) and OPTIONS (CORS preflight)
        if method in ("HEAD", "OPTIONS"):
            continue

        authz._auth_failures.clear()
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
