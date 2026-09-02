"""SDK <-> route contract test (#2531, #2952).

Guards against the SDK drifting from the real route table. Every path the
``RegEngineClient`` issues must be judged against the routers production
actually mounts — not against a hand-built FastAPI app that always includes
experimental graph routes.

``server/main.py`` mounts graph only when ``_router_enabled("graph")``. Graph
is in ``EXPERIMENTAL_ROUTERS`` and is not in the production allowlist, so it
is off unless ``ENABLE_EXPERIMENTAL_ROUTERS`` is set (a non-production bypass
that production policy rejects). This module builds the same two-router
surface the original contract used (graph + canonical records) but applies
that gate so 7 of 9 client methods are not certified against routes that 404.
"""

from __future__ import annotations

import os
import re

import pytest

from regengine import RegEngineClient
from regengine.models import CTEType

# SDK methods whose paths live on the graph router (``/api/v1/fsma/...``).
# The two remaining public methods hit canonical records, which production
# mounts.
_GRAPH_PATH_MARKER = "/api/v1/fsma/"


def _experimental_routers_enabled() -> bool:
    return os.environ.get("ENABLE_EXPERIMENTAL_ROUTERS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _graph_router_enabled() -> bool:
    """Same production gate ``server/main.py`` uses for ``_router_enabled("graph")``.

    Production mounts graph only if it is in the release allowlist.
    ``ENABLE_EXPERIMENTAL_ROUTERS`` is the documented non-production bypass.
    """
    from server.router_policy import PRODUCTION_ENABLED_ROUTERS

    if _experimental_routers_enabled():
        return True
    return "graph" in PRODUCTION_ENABLED_ROUTERS


def _registered_routes() -> set[tuple[str, str]]:
    """(method, path_template) pairs for the gated mount set.

    FastAPI is required. A missing install must fail this helper, not skip.
    """
    from fastapi import FastAPI

    from shared.paths import ensure_shared_importable

    ensure_shared_importable()
    from services.ingestion.app.canonical_router import router as canonical_router

    app = FastAPI()
    # Canonical records carry their own ``/api/v1/records`` prefix (production).
    app.include_router(canonical_router)
    if _graph_router_enabled():
        from services.graph.app.routes import router as graph_router

        app.include_router(graph_router, prefix="/api/v1")

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


def _resolves(method: str, sdk_path: str, registered: set[tuple[str, str]]) -> bool:
    return any(
        method == r_method and _path_matches(sdk_path, r_path) for r_method, r_path in registered
    )


def _is_graph_backed(sdk_path: str) -> bool:
    return _GRAPH_PATH_MARKER in sdk_path


def test_production_sdk_paths_resolve_and_graph_is_not_certified(monkeypatch):
    """#2531 + #2952: production-default mount set.

    Canonical-records methods must resolve. Graph-backed methods must not be
    certified as present while experimental routers are off.
    """
    from server.router_policy import EXPERIMENTAL_ROUTERS, PRODUCTION_ENABLED_ROUTERS

    monkeypatch.delenv("ENABLE_EXPERIMENTAL_ROUTERS", raising=False)
    assert "graph" in EXPERIMENTAL_ROUTERS
    assert "graph" not in PRODUCTION_ENABLED_ROUTERS
    assert not _graph_router_enabled()

    registered = _registered_routes()
    unresolved_production: list[tuple[str, str]] = []
    certified_graph: list[tuple[str, str]] = []
    missing_graph: list[tuple[str, str]] = []

    for method, sdk_path in _captured_sdk_calls():
        hit = _resolves(method, sdk_path, registered)
        if _is_graph_backed(sdk_path):
            if hit:
                certified_graph.append((method, sdk_path))
            else:
                missing_graph.append((method, sdk_path))
        elif not hit:
            unresolved_production.append((method, sdk_path))

    assert not unresolved_production, (
        "SDK methods reference production paths with no registered route: "
        + ", ".join(f"{m} {p}" for m, p in unresolved_production)
    )
    assert not certified_graph, (
        "Graph-backed SDK methods must not be certified as present when "
        "experimental routers are off: "
        + ", ".join(f"{m} {p}" for m, p in certified_graph)
    )
    assert len(missing_graph) == 7, (
        "expected 7 graph-backed SDK methods to be absent from the production "
        f"route table; classified {len(missing_graph)}: "
        + ", ".join(f"{m} {p}" for m, p in missing_graph)
    )


def test_experimental_routers_may_certify_graph_backed_sdk_methods(monkeypatch):
    """#2952: when ENABLE_EXPERIMENTAL_ROUTERS is on, graph methods may resolve."""
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_ROUTERS", "true")
    assert _graph_router_enabled()

    registered = _registered_routes()
    unresolved: list[tuple[str, str]] = []
    for method, sdk_path in _captured_sdk_calls():
        if not _resolves(method, sdk_path, registered):
            unresolved.append((method, sdk_path))

    assert not unresolved, (
        "SDK methods reference paths with no registered route (experimental "
        "routers on): "
        + ", ".join(f"{m} {p}" for m, p in unresolved)
        + ". Registered fsma/records routes: "
        + ", ".join(sorted(f"{m} {p}" for m, p in registered if "fsma" in p or "/records" in p))
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
