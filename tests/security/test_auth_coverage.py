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
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

STRIPE_SIGNATURE_OPERATIONS = frozenset(
    {
        "billing:POST:/api/v1/billing/webhook/stripe",
        "billing:POST:/api/v1/billing/webhooks",
    }
)


class _AuthProbePipeline:
    def __init__(self, redis) -> None:
        self.redis = redis
        self.key = ""

    def incr(self, key):
        self.key = key
        return self

    def expire(self, key, _seconds):
        assert key == self.key
        return self

    async def execute(self):
        self.redis.values[self.key] = self.redis.values.get(self.key, 0) + 1
        return [self.redis.values[self.key], True]


class _AuthProbeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    async def get(self, key):
        return self.values.get(key)

    def pipeline(self, transaction=True):
        assert transaction is True
        return _AuthProbePipeline(self)

    async def delete(self, key):
        self.values.pop(key, None)
        return 1


def _build_test_app():
    """Build the exact production route table, without starting its lifespan."""
    from server.main import app as inventory_app
    from server.route_ownership import route_owner
    from server.route_security_manifest import PRODUCTION_OWNERS, build_route_security_manifest

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.router.routes.extend(
        route
        for route in inventory_app.routes
        if isinstance(route, APIRoute) and route_owner(route) in PRODUCTION_OWNERS
    )
    # Classify before swapping the global throttle: a manifest error then
    # leaves no probe throttle behind to 429 later modules in the session.
    app.state.security_manifest = build_route_security_manifest(inventory_app)
    from services.admin.app import privileged_auth

    app.state.previous_privileged_auth_throttle = privileged_auth._privileged_auth_throttle
    privileged_auth_redis = _AuthProbeRedis()
    privileged_auth._privileged_auth_throttle = privileged_auth.PrivilegedAuthThrottle(
        redis_client=privileged_auth_redis
    )
    app.state.privileged_auth_probe_redis = privileged_auth_redis
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
    """Replace path parameters with type-valid values for auth probing."""
    from server.route_security_manifest import _concrete_probe_path

    return _concrete_probe_path(path)


@pytest.fixture(scope="module")
def app_and_client():
    """Build the app once for all tests in this module, with auth enforced.

    Uses staging auth semantics and restores the prior environment on teardown
    so the change does not leak into the rest of the test session.
    """
    import os
    import sys

    env_keys = (
        "ADMIN_FALLBACK_SQLITE",
        "API_KEY",
        "AUTH_SECRET_KEY",
        "AUTH_TEST_BYPASS_TOKEN",
        "ENV",
        "METRICS_API_KEY",
        "REDIS_URL",
        "REGENGINE_API_KEY",
        "REGENGINE_ENV",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
    )
    prev_env = {key: os.environ.get(key) for key in env_keys}
    prev_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "main" or name == "app" or name.startswith("app.")
    }
    prev_sys_path = list(sys.path)
    os.environ.pop("API_KEY", None)
    os.environ.pop("REGENGINE_API_KEY", None)
    # Import-time database setup may use the explicit SQLite test fallback;
    # request-time auth is switched to staging below to disable dev_open.
    os.environ["REGENGINE_ENV"] = "test"
    os.environ["ENV"] = "test"
    os.environ["ADMIN_FALLBACK_SQLITE"] = "sqlite:///:memory:"
    os.environ.setdefault("AUTH_SECRET_KEY", "auth-coverage-signing-material")
    os.environ.setdefault("METRICS_API_KEY", "auth-coverage-metrics")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_auth_coverage")
    os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_auth_coverage")
    os.environ.pop("AUTH_TEST_BYPASS_TOKEN", None)
    try:
        app = _build_test_app()
        os.environ["REGENGINE_ENV"] = "staging"
        os.environ["ENV"] = "staging"
        client = TestClient(app, raise_server_exceptions=False)
    except Exception as e:
        _restore_test_state(prev_env, prev_modules, prev_sys_path)
        pytest.fail(f"Cannot build ingestion app for mandatory auth coverage: {e}")

    try:
        yield app, client
    finally:
        from services.admin.app import privileged_auth

        privileged_auth._privileged_auth_throttle = app.state.previous_privileged_auth_throttle
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
    """Every protected production operation reaches an exact auth denial."""
    app, client = app_and_client
    manifest = app.state.security_manifest

    # Reset the per-IP auth failure counter between requests. Otherwise, after
    # 15 unauthenticated probes the rate limiter blocks "testclient" and every
    # subsequent endpoint returns 429 — which would mask a genuinely
    # unprotected endpoint behind the block and make this assertion
    # order-dependent.
    from services.ingestion.app import authz

    unprotected = []
    for operation in manifest["enabled_operations"]:
        if operation["classification"] == "public":
            continue
        authz._get_auth_limiter().reset("testclient")
        # The privileged human/workload realm intentionally shares a much
        # tighter Redis-backed failure budget. Reset the in-process test
        # double between route probes so a prior denial cannot turn later
        # checks into 429 responses that mask whether their auth dependency
        # was actually reached.
        app.state.privileged_auth_probe_redis.values.clear()
        method = operation["method"]
        path = operation["path"]
        request_kwargs = {"json": {}} if method in {"POST", "PUT", "PATCH", "DELETE"} else {}
        response = client.request(method, _make_dummy_path(path), **request_kwargs)

        # Only an exact authentication/authorization denial is evidence. A
        # 404/405/422 can mean the probe never exercised the auth dependency.
        expected_statuses = {400} if operation["operation"] in STRIPE_SIGNATURE_OPERATIONS else {401, 403}
        if response.status_code not in expected_statuses:
            unprotected.append(f"{operation['operation']} -> {response.status_code}")

    assert not unprotected, f"Endpoints accessible without authentication:\n" + "\n".join(f"  {e}" for e in unprotected)


def test_allowlist_entries_still_exist(app_and_client):
    """Public operations are exactly the explicit reviewed policy set."""
    app, _ = app_and_client
    from server.route_security_policy import PUBLIC_OPERATIONS

    manifest_public = {
        (operation["owner"], operation["method"], operation["path"])
        for operation in app.state.security_manifest["enabled_operations"]
        if operation["classification"] == "public"
    }

    assert manifest_public == PUBLIC_OPERATIONS
