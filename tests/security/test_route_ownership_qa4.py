"""QA deep-pass: route ownership stamping and exclusion guards.

Exercises server/route_ownership.py directly on scratch FastAPI apps: owner
normalization, double-registration conflicts, exact exclusion matching, and
the excluded-route inventory. Fast and deterministic, no network.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

from server.route_ownership import (
    RouteOwnershipError,
    claim_existing_operation,
    excluded_owned_routes,
    include_owned_router,
    owned_api_route,
    route_owner,
)


def _app_with_router(owner="health"):
    app = FastAPI()
    router = APIRouter()

    @router.get("/ping")
    def ping():
        return {"ok": True}

    include_owned_router(app, router, owner=owner)
    return app


def test_owner_is_normalized_to_lowercase_stripped():
    app = _app_with_router(owner="  Health ")
    routes = [r for r in app.routes if isinstance(r, APIRoute)]
    assert len(routes) == 1
    assert route_owner(routes[0]) == "health"


def test_empty_owner_is_rejected():
    app = FastAPI()
    router = APIRouter()

    @router.get("/ping")
    def ping():
        return {"ok": True}

    with pytest.raises(RouteOwnershipError, match="non-empty"):
        include_owned_router(app, router, owner="   ")


def test_reassigning_route_to_another_owner_fails():
    app = _app_with_router(owner="health")
    (route,) = [r for r in app.routes if isinstance(r, APIRoute)]
    from server.route_ownership import _assign_owner

    with pytest.raises(RouteOwnershipError, match="already belongs"):
        _assign_owner([route], "billing")


def test_same_owner_reassignment_is_idempotent():
    app = _app_with_router(owner="health")
    (route,) = [r for r in app.routes if isinstance(r, APIRoute)]
    from server.route_ownership import _assign_owner

    _assign_owner([route], "health")
    assert route_owner(route) == "health"


def test_plain_include_leaves_every_entry_unstamped():
    """Routes that bypass include_owned_router carry no owner attribute."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/raw")
    def raw():
        return {}

    app.include_router(router)
    assert len(app.routes) > 0
    for entry in app.routes:
        assert route_owner(entry) is None


def test_exact_exclusion_removes_route_and_records_inventory():
    app = FastAPI()
    router = APIRouter()

    @router.get("/internal")
    def internal():
        return {}

    include_owned_router(app, router, owner="sandbox", excluded_operations=[("GET", "/internal")])
    assert [r for r in app.routes if isinstance(r, APIRoute)] == []
    excluded = excluded_owned_routes(app)
    assert len(excluded) == 1
    assert route_owner(excluded[0]) == "sandbox"


def test_exclusion_matching_is_case_insensitive_on_method():
    app = FastAPI()
    router = APIRouter()

    @router.get("/internal")
    def internal():
        return {}

    include_owned_router(app, router, owner="sandbox", excluded_operations=[("get", "/internal")])
    assert [r for r in app.routes if isinstance(r, APIRoute)] == []


def test_exclusion_for_unregistered_operation_fails_closed():
    app = FastAPI()
    router = APIRouter()

    @router.get("/internal")
    def internal():
        return {}

    with pytest.raises(RouteOwnershipError, match="not registered"):
        include_owned_router(app, router, owner="sandbox", excluded_operations=[("GET", "/missing")])


def test_partial_exclusion_of_multi_method_route_fails():
    app = FastAPI()
    router = APIRouter()

    @router.api_route("/multi", methods=["GET", "POST"])
    def multi():
        return {}

    with pytest.raises(RouteOwnershipError, match="partially exclude"):
        include_owned_router(app, router, owner="sandbox", excluded_operations=[("GET", "/multi")])


def test_owned_api_route_registers_exactly_one_operation():
    app = FastAPI()

    @owned_api_route(app, owner="status", path="/v1/qa4-probe", methods=["GET"])
    def probe():
        return {"ok": True}

    matches = [r for r in app.routes if isinstance(r, APIRoute) and r.path == "/v1/qa4-probe"]
    assert len(matches) == 1
    assert route_owner(matches[0]) == "status"


def test_claim_existing_operation_requires_exact_single_match():
    app = FastAPI()

    @app.get("/metrics")
    def metrics():
        return {}

    claim_existing_operation(app, owner="metrics", method="GET", path="/metrics")
    (route,) = [r for r in app.routes if isinstance(r, APIRoute) and r.path == "/metrics"]
    assert route_owner(route) == "metrics"

    with pytest.raises(RouteOwnershipError, match="exactly one"):
        claim_existing_operation(app, owner="metrics", method="POST", path="/metrics")


def test_excluded_inventory_is_empty_by_default():
    assert excluded_owned_routes(FastAPI()) == ()
