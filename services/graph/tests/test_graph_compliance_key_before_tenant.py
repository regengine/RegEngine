"""API-key-only callers must resolve their tenant on the graph compliance routes.

Every handler in ``routers/fsma/compliance.py`` declares
``Depends(get_current_tenant_id)`` ahead of ``Depends(require_api_key)``. FastAPI
resolves endpoint dependencies in declaration order, so the tenant lookup ran
first, found no principal on ``request.state`` (the #2524 fallback), and failed
closed with 401 "Tenant ID not found in authentication context" before the key
was ever validated. Only callers that also carried a JWT or the internal
service header pair could reach these exports.

The router now declares ``require_api_key`` as a router-level dependency, which
FastAPI resolves before any endpoint parameter. ``test_key_only_caller_reaches_handler``
pins the surface behaviour through the real ``require_api_key`` (env bypass, no
dependency overrides); ``test_every_compliance_route_checks_key_before_tenant``
pins the resolution order so a future route cannot regress it.

The eight sibling graph routers shared the ordering. ``recall``, ``science``,
``traceability`` and ``lineage_traversal`` now carry the same router-level
dependency; ``metrics`` and ``labels`` each expose an open ``/health`` route, so
their key+tenant handlers were reordered instead. ``regulations`` and the
``provisions`` route in ``routes.py`` already declared the key first.
``test_every_graph_route_checks_key_before_tenant`` walks every route served
under ``services.graph.app.routes.router`` so none of them can regress.
"""

from __future__ import annotations

import sys
import uuid
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
for _p in (str(REPO_ROOT), str(REPO_ROOT / "services")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from shared.auth import require_api_key  # noqa: E402
from shared.middleware import get_current_tenant_id  # noqa: E402

from services.graph.tests.test_fda_request_export_header import _neo4j_stub  # noqa: E402

TENANT = "11111111-1111-1111-1111-111111111111"
BYPASS_TOKEN = "graph-key-before-tenant-test"  # noqa: S105 — test-only env bypass value


@pytest.fixture(autouse=True)
def _rate_limiter_off(monkeypatch):
    """Keep this file's GETs out of the shared 10/min export quota.

    The limiter's storage follows ``REDIS_URL`` when it is set, so resetting
    ``limiter._storage`` from a test would flush rate-limit keys in whatever
    Redis the environment points at. Disabling the limiter for the duration
    of each test touches nothing shared.
    """
    from shared.rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)


@pytest.fixture
def _env_bypass(monkeypatch):
    """Route the real ``require_api_key`` through its development-only bypass."""
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.setenv("AUTH_TEST_BYPASS_TOKEN", BYPASS_TOKEN)
    monkeypatch.setenv("AUTH_TEST_BYPASS_TENANT_ID", TENANT)


def _bare_app() -> FastAPI:
    """The compliance router with no dependency overrides and no tenant middleware.

    Without ``TenantContextMiddleware`` there is no ``request.state.tenant_id``, so
    ``get_current_tenant_id`` can only succeed through the API-key principal.
    """
    from services.graph.app.routers.fsma import compliance_router

    app = FastAPI()
    app.include_router(compliance_router, prefix="/v1/fsma/compliance")
    return app


def _patched_range_query(stack: ExitStack, events: list) -> AsyncMock:
    """Stub ``query_events_by_range`` wherever the compliance module looks it up."""
    from services.graph.app.routers.fsma import compliance as compliance_module

    query = AsyncMock(return_value=events)
    stack.enter_context(patch("services.graph.app.fsma_utils.query_events_by_range", new=query))
    if hasattr(compliance_module, "query_events_by_range"):
        stack.enter_context(patch.object(compliance_module, "query_events_by_range", new=query))
    return query


def test_key_only_caller_reaches_handler(_env_bypass):
    client = TestClient(_bare_app(), raise_server_exceptions=False)
    with ExitStack() as stack:
        stack.enter_context(patch("services.graph.app.routers.fsma.compliance.Neo4jClient", _neo4j_stub()))
        query = _patched_range_query(stack, events=[])
        resp = client.get(
            "/v1/fsma/compliance/export/fda-request",
            params={"start_date": "2026-01-01", "end_date": "2026-12-31"},
            headers={"X-RegEngine-API-Key": BYPASS_TOKEN},
        )

    assert resp.status_code == 200, resp.text
    assert resp.content.startswith(b"\xef\xbb\xbf"), "expected the BOM-prefixed FDA CSV"
    # The tenant that scoped the Neo4j query came from the API key itself.
    assert query.await_count == 1
    assert query.await_args.args[3] == TENANT


def test_missing_key_fails_on_the_key_not_the_tenant(_env_bypass):
    """Fail closed, and name the real problem: the key check now runs first."""
    client = TestClient(_bare_app(), raise_server_exceptions=False)
    resp = client.get(
        "/v1/fsma/compliance/export/fda-request",
        params={"start_date": "2026-01-01", "end_date": "2026-12-31"},
    )
    assert resp.status_code == 401
    assert "Missing API key" in resp.text
    assert "Tenant ID not found" not in resp.text


def test_invalid_key_fails_on_the_key_not_the_tenant(_env_bypass):
    """An unknown key is rejected by the key check; the handler is never reached."""
    client = TestClient(_bare_app(), raise_server_exceptions=False)
    with ExitStack() as stack:
        stack.enter_context(patch("services.graph.app.routers.fsma.compliance.Neo4jClient", _neo4j_stub()))
        query = _patched_range_query(stack, events=[])
        resp = client.get(
            "/v1/fsma/compliance/export/fda-request",
            params={"start_date": "2026-01-01", "end_date": "2026-12-31"},
            headers={"X-RegEngine-API-Key": "not-" + BYPASS_TOKEN},
        )
    assert resp.status_code == 401
    assert "Invalid API key" in resp.text
    assert "Tenant ID not found" not in resp.text
    assert query.await_count == 0


def _resolution_order(route: APIRoute) -> list:
    """Dependency callables in the order FastAPI resolves them (depth-first)."""
    order: list = []

    def walk(dependant) -> None:
        for sub in dependant.dependencies:
            walk(sub)
            order.append(sub.call)

    walk(route.dependant)
    return order


def test_every_compliance_route_checks_key_before_tenant():
    from services.graph.app.routers.fsma import compliance_router

    routes = [r for r in compliance_router.routes if isinstance(r, APIRoute)]
    assert routes, "compliance router has no routes"
    for route in routes:
        order = _resolution_order(route)
        assert require_api_key in order, f"{route.path} does not require an API key"
        if get_current_tenant_id in order:
            assert order.index(require_api_key) < order.index(get_current_tenant_id), (
                f"{route.path}: tenant resolution runs before API-key validation"
            )


def _effective_api_routes(router) -> list:
    """Every ``APIRoute`` served under ``router`` the way the monolith mounts it.

    FastAPI (>= 0.141) includes routers lazily: ``router.routes`` holds wrapper objects,
    and the effective routes (prefix applied, router-level dependencies merged) are
    materialised by ``iter_route_contexts``, the same walk the OpenAPI generator uses.
    Each returned item exposes ``path``, ``methods`` and ``dependant`` for the effective
    route. Older FastAPI flattened routes at include time, so ``app.routes`` is already flat.
    """
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:  # pragma: no cover - FastAPI < 0.141
        return [r for r in app.routes if isinstance(r, APIRoute)]
    return [ctx for ctx in iter_route_contexts(app.routes) if isinstance(ctx.route, APIRoute)]


def test_every_graph_route_checks_key_before_tenant():
    from services.graph.app import routes as graph_routes

    routes = _effective_api_routes(graph_routes.router)
    assert routes, "graph router has no routes"

    checked: list[str] = []
    offenders: list[str] = []
    for route in routes:
        order = _resolution_order(route)
        if get_current_tenant_id not in order:
            continue  # open route (health), metrics-key route, or key-only route
        checked.append(route.path)
        if require_api_key not in order:
            # Graph routes are API-key only: a tenant-bound route with no key
            # dependency has no principal to resolve the tenant from.
            offenders.append(f"{sorted(route.methods)} {route.path}: no API-key dependency")
        elif order.index(require_api_key) > order.index(get_current_tenant_id):
            offenders.append(f"{sorted(route.methods)} {route.path}")

    # The walk must reach the sub-routers, not just the operational routes in routes.py.
    for expected in (
        "/api/v1/fsma/compliance/export/fda-request",
        "/api/v1/fsma/recall/history",
        "/api/v1/fsma/traceability/search/events",
        "/api/v1/labels/batch/init",
        "/api/v1/provisions/by-request",
    ):
        assert expected in checked, f"{expected} not reached from routes.router"

    assert not offenders, "tenant-bound routes without a leading API-key check:\n  " + "\n  ".join(offenders)
