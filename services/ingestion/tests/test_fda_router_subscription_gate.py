"""Static guard: every data route on the FDA export router carries the
subscription gate.

Regression protection for the gap where ``get_merkle_root`` and
``get_merkle_proof`` shipped with only ``require_permission("fda.verify")``
and no ``require_active_subscription`` — every sibling route on the router
had the gate, so a lapsed-billing tenant with a live ``fda.verify`` key
could still pull hash-chain metadata. The whole router is exposed publicly
at ``regengine.co/api/v1/fda/:path*``, so a missing gate is a live billing
bypass, not a theoretical one.

This introspects the router rather than exercising each endpoint, so a new
route added without the gate fails here immediately — the class of bug, not
just the two instances.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.fda_export.router import router
from app.subscription_gate import require_active_subscription

# Routes deliberately NOT behind the billing gate, each with a reason. Keep
# this list empty unless there is a documented, reviewed exemption — adding a
# path here is the explicit, greppable way to opt a route out.
SUBSCRIPTION_EXEMPT_PATHS: set[str] = set()


def _route_dependency_calls(route) -> set:
    """Every dependency callable FastAPI will resolve for this route."""
    return {dep.call for dep in route.dependant.dependencies}


def _data_routes():
    for route in router.routes:
        methods = getattr(route, "methods", set()) or set()
        # Skip pure OPTIONS/HEAD plumbing; every GET/POST here reads or
        # mutates tenant evidence and must be gated.
        if methods & {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            yield route


def test_every_fda_route_requires_active_subscription():
    missing = []
    for route in _data_routes():
        if route.path in SUBSCRIPTION_EXEMPT_PATHS:
            continue
        if require_active_subscription not in _route_dependency_calls(route):
            missing.append(f"{sorted(route.methods)} {route.path}")
    assert not missing, (
        "FDA export routes exposed without require_active_subscription "
        "(billing bypass on the public /api/v1/fda surface): "
        + ", ".join(missing)
    )


def test_merkle_endpoints_are_gated():
    """Pin the two specific endpoints the guard was written for."""
    gated = {
        route.path
        for route in router.routes
        if require_active_subscription in _route_dependency_calls(route)
    }
    assert "/api/v1/fda/export/merkle-root" in gated
    assert "/api/v1/fda/export/merkle-proof" in gated
