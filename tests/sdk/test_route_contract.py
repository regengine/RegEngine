"""SDK <-> route contract test (#2531).

Guards against the SDK drifting from the real route table. Every path the
``RegEngineClient`` issues must resolve to a route registered on the
consolidated app. Previously the SDK hardcoded a ``/api/graph/fsma/...``
prefix that does not exist on the deploy target, so every call 404'd.

The test builds a minimal app from the SAME routers ``server/main.py`` mounts
(graph routes under ``/api/v1`` + the canonical records router which carries
its own ``/api/v1/records`` prefix), captures the (method, path) each SDK
method issues, and asserts each one matches a registered route — comparing
path templates segment-by-segment so ``{tlc}`` matches ``{event_id}`` etc.
"""

from __future__ import annotations

import re

import pytest

# sdk-ci runs this suite in a CLEAN venv (pytest + httpx + requests only) to
# prove the installed package works without the backend dependency tree. The
# route-contract half of this module needs the real routers, so it runs in
# the full backend suite instead of sdk-ci.
fastapi = pytest.importorskip("fastapi", reason="route-contract check requires the backend dependency tree")
from fastapi import FastAPI  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

from regengine import RegEngineClient
from regengine.models import CTEType


@pytest.fixture(scope="module")
def registered_routes() -> set[tuple[str, str]]:
    """(method, path_template) pairs for the real mounted route table."""
    from shared.paths import ensure_shared_importable

    ensure_shared_importable()
    from services.graph.app.routes import router as graph_router
    from services.ingestion.app.canonical_router import router as canonical_router

    app = FastAPI()
    # Mounts mirror server/main.py: graph router at /api/v1, canonical router
    # carries its own /api/v1/records prefix.
    app.include_router(graph_router, prefix="/api/v1")
    app.include_router(canonical_router)

    from shared.route_introspection import iter_effective_routes

    pairs: set[tuple[str, str]] = set()
    for path, route in iter_effective_routes(app):
        for method in route.methods or ():
            pairs.add((method.upper(), path))
    return pairs


def _captured_sdk_calls() -> list[tuple[str, str]]:
    """Drive every public SDK method and capture the (method, path) it issues.

    ``_request``/``_request_bytes`` are stubbed so no network call is made.
    Methods that are intentionally unsupported (no real route exists) raise
    ``NotImplementedError`` and are excluded — they must NOT issue a request.
    """
    client = RegEngineClient(api_key="rge_test")
    calls: list[tuple[str, str]] = []

    # **kwargs absorbs the transport-only options the real helpers take
    # (#2956 added parse/accept/expected_content_type); this stub asserts on
    # (method, path) only, so those are irrelevant here.
    def fake_request(method, path, params=None, json=None, **kwargs):
        calls.append((method.upper(), path))
        # Return shapes the SDK methods expect to parse without error.
        return {"events": [], "drills": [], "records": []}

    def fake_request_bytes(method, path, params=None, **kwargs):
        calls.append((method.upper(), path))
        return b""

    client._request = fake_request  # type: ignore[assignment]
    client._request_bytes = fake_request_bytes  # type: ignore[assignment]

    client.trace_forward("LOT-1")
    client.trace_backward("LOT-1")
    client.get_timeline("LOT-1")
    client.query_records("2026-01-01", "2026-12-31", cte_type=CTEType.SHIPPING)
    client.start_recall_drill("LOT-1")
    client.get_recall_drills()
    client.get_readiness_score()
    client.export_fda("LOT-1", "2026-01-01", "2026-12-31")
    # get_record raises NotFoundError on empty events but still issues a request
    from regengine.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        client.get_record("LOT-1")

    client._session.close()
    return calls


def _path_matches(sdk_path: str, route_path: str) -> bool:
    """Match an SDK path against a route template segment-by-segment.

    A ``{param}`` segment on either side matches any single concrete segment,
    so e.g. ``/api/v1/records/{tlc}`` would match ``/api/v1/records/{event_id}``.
    """
    sdk_segments = sdk_path.strip("/").split("/")
    route_segments = route_path.strip("/").split("/")
    if len(sdk_segments) != len(route_segments):
        return False
    placeholder = re.compile(r"^\{.+\}$")
    for s, r in zip(sdk_segments, route_segments):
        if placeholder.match(s) or placeholder.match(r):
            continue
        if s != r:
            return False
    return True


def test_every_sdk_path_resolves_to_a_registered_route(registered_routes):
    """#2531: each (method, path) the SDK issues must hit a real route."""
    unresolved: list[tuple[str, str]] = []
    for method, sdk_path in _captured_sdk_calls():
        if not any(method == r_method and _path_matches(sdk_path, r_path) for r_method, r_path in registered_routes):
            unresolved.append((method, sdk_path))

    assert not unresolved, (
        "SDK methods reference paths with no registered route: "
        + ", ".join(f"{m} {p}" for m, p in unresolved)
        + f". Registered fsma/records routes: "
        + ", ".join(sorted(f"{m} {p}" for m, p in registered_routes if "fsma" in p or "/records" in p))
    )


def test_unsupported_sdk_methods_are_removed():
    """#2531 → WS-11: create_record / check_ftl had no real route. They first
    became loud NotImplementedError stubs; WS-11 removed them entirely so the
    installed client exposes only methods with registered routes behind them.
    This pins the removal — reintroducing either name must come with a real
    route (and a test in _captured_sdk_calls scope)."""
    client = RegEngineClient(api_key="rge_test")
    try:
        assert not hasattr(client, "create_record")
        assert not hasattr(client, "check_ftl")
    finally:
        client._session.close()
