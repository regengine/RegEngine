"""SDK <-> route contract test (#2531, #2952).

Guards against the SDK drifting from the real route table. Every path the
``RegEngineClient`` issues must resolve to a route the consolidated app
registers, and — since #2952 — the route table is derived from the REAL
application factory (``server.main``) under both postures rather than from a
hand-mounted fixture app:

- production posture: ``REGENGINE_ENV=production`` with the release-approved
  ``ENABLED_ROUTERS`` allowlist and no experimental bypass, i.e. exactly what
  the deployed monolith serves;
- development posture: the broad table with experimental routers enabled.

The previous fixture built its own ``FastAPI()`` and mounted the graph router
unconditionally, skipping the ``RouterPolicy`` gate. Because graph is
experimental and auto-disabled in production, that certified 7 of the
client's 9 public methods against routes the deployed process never mounts.
Those methods are now declared in ``RegEngineClient.EXPERIMENTAL_METHODS``
and this module keeps the declaration exactly in sync with production
reality in both directions.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

# sdk-ci runs this suite in a CLEAN venv (pytest + httpx + requests only) to
# prove the installed package works without the backend dependency tree. The
# route-contract half of this module imports server.main, so it runs in the
# full backend suite instead of sdk-ci.
fastapi = pytest.importorskip("fastapi", reason="route-contract check requires the backend dependency tree")

from regengine import RegEngineClient  # noqa: E402
from regengine.models import CTEType  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

# Imports server.main in a subprocess (same pattern as
# tests/test_monolith_route_parity.py) so each posture gets a clean
# environment-dependent import instead of fighting sys.modules caching.
ROUTE_SCRIPT = r"""
import importlib
import json

module = importlib.import_module("server.main")

from shared.paths import ensure_shared_importable

ensure_shared_importable()
from shared.route_introspection import route_keys

print("ROUTE_KEYS_JSON=" + json.dumps(sorted(route_keys(module.app))))
"""

_COMMON_ENV = {
    "AUTH_SECRET_KEY": "route-contract-test-secret-with-enough-length",  # pragma: allowlist secret
    "DATABASE_URL": "postgresql://localhost:5432/regengine_test",
    "ADMIN_DATABASE_URL": "postgresql+psycopg://localhost:5432/regengine_admin_test",
    "REDIS_URL": "redis://localhost:6379/0",
    "TOOL_ACCESS_SECRET": "route-contract-test-tool-secret-distinct-value",  # pragma: allowlist secret
}

# Vars that would change (or reject) the posture under test if inherited.
_POSTURE_SENSITIVE = (
    "ADMIN_FALLBACK_SQLITE",
    "AUTH_TEST_BYPASS_TOKEN",
    "DISABLED_ROUTERS",
    "ENABLED_ROUTERS",
    "ENABLE_EXPERIMENTAL_ROUTERS",
    "ENV",
    "ENVIRONMENT",
    "REGENGINE_ENV",
)


def _server_route_keys(*, production: bool) -> set[tuple[str, str]]:
    """(method, path_template) pairs served by ``server.main`` under a posture."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("RAILWAY_") and key not in _POSTURE_SENSITIVE
    }
    env.update(_COMMON_ENV)
    if production:
        from server.router_policy import PRODUCTION_ENABLED_ROUTERS

        env["REGENGINE_ENV"] = "production"
        env["ENABLED_ROUTERS"] = ",".join(sorted(PRODUCTION_ENABLED_ROUTERS))
    else:
        env["REGENGINE_ENV"] = "test"
        env["ENVIRONMENT"] = "test"
        env["ENABLE_EXPERIMENTAL_ROUTERS"] = "true"

    result = subprocess.run(
        [sys.executable, "-c", ROUTE_SCRIPT],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, f"server.main import failed under posture:\n{result.stderr[-3000:]}"
    marker = "ROUTE_KEYS_JSON="
    keys = next(json.loads(line.removeprefix(marker)) for line in result.stdout.splitlines() if line.startswith(marker))
    pairs = {(key.split(" ", 1)[0], key.split(" ", 1)[1]) for key in keys}
    # Vacuous-pass self-check: the production monolith serves >200 operations.
    assert len(pairs) > 100, f"route enumeration returned only {len(pairs)} operations"
    return pairs


@pytest.fixture(scope="module")
def production_routes() -> set[tuple[str, str]]:
    """Exactly what the deployed monolith serves (release allowlist, no bypass)."""
    return _server_route_keys(production=True)


@pytest.fixture(scope="module")
def development_routes() -> set[tuple[str, str]]:
    """The broad table with experimental routers mounted."""
    return _server_route_keys(production=False)


def _captured_sdk_calls() -> dict[str, list[tuple[str, str]]]:
    """Drive every public SDK method; capture the (method, path) each issues.

    ``_request``/``_request_bytes`` are stubbed so no network call is made.
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

    from regengine.exceptions import NotFoundError

    def drive(name: str):
        if name == "trace_forward":
            client.trace_forward("LOT-1")
        elif name == "trace_backward":
            client.trace_backward("LOT-1")
        elif name == "get_timeline":
            client.get_timeline("LOT-1")
        elif name == "query_records":
            client.query_records("2026-01-01", "2026-12-31", cte_type=CTEType.SHIPPING)
        elif name == "start_recall_drill":
            client.start_recall_drill("LOT-1")
        elif name == "get_recall_drills":
            client.get_recall_drills()
        elif name == "get_readiness_score":
            client.get_readiness_score()
        elif name == "export_fda":
            client.export_fda("LOT-1", "2026-01-01", "2026-12-31")
        elif name == "get_record":
            # get_record raises NotFoundError on empty events but still issues a request
            with pytest.raises(NotFoundError):
                client.get_record("LOT-1")
        else:  # pragma: no cover - a new method must be wired in explicitly
            raise AssertionError(f"drive() has no scenario for SDK method {name!r}")

    method_names = [
        "get_record",
        "query_records",
        "trace_forward",
        "trace_backward",
        "get_timeline",
        "start_recall_drill",
        "get_recall_drills",
        "get_readiness_score",
        "export_fda",
    ]
    by_method: dict[str, list[tuple[str, str]]] = {}
    try:
        for name in method_names:
            start = len(calls)
            drive(name)
            issued = calls[start:]
            assert issued, f"SDK method {name} issued no request"
            by_method[name] = issued
    finally:
        client._session.close()
    return by_method


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


def _resolves(call: tuple[str, str], routes: set[tuple[str, str]]) -> bool:
    method, sdk_path = call
    return any(method == r_method and _path_matches(sdk_path, r_path) for r_method, r_path in routes)


def test_every_sdk_path_resolves_on_the_experimental_route_table(development_routes):
    """#2531: each (method, path) the SDK issues must hit a real route somewhere.

    The development table is the superset (all routers mounted); a miss here
    is prefix drift or a route that does not exist under any posture.
    """
    unresolved = [
        (name, method, path)
        for name, issued in _captured_sdk_calls().items()
        for method, path in issued
        if not _resolves((method, path), development_routes)
    ]

    assert not unresolved, "SDK methods reference paths with no registered route under ANY posture: " + ", ".join(
        f"{name}: {m} {p}" for name, m, p in unresolved
    )


def test_experimental_declaration_matches_production_route_table(production_routes):
    """#2952: the client's experimental set must equal production reality.

    - A method missing from production must be declared experimental (so the
      README/docstrings stop presenting it as a working hosted-API call).
    - A declared-experimental method must actually be absent from production
      (so promoting the graph routers forces this declaration — and the docs —
      to be updated in the same change).
    """
    by_method = _captured_sdk_calls()
    resolves_in_production = {
        name for name, issued in by_method.items() if all(_resolves(call, production_routes) for call in issued)
    }
    undeclared = set(by_method) - resolves_in_production - RegEngineClient.EXPERIMENTAL_METHODS
    stale = RegEngineClient.EXPERIMENTAL_METHODS & resolves_in_production
    unknown = RegEngineClient.EXPERIMENTAL_METHODS - set(by_method)

    assert not undeclared, (
        f"Client methods target routes production does not mount but are not declared "
        f"in RegEngineClient.EXPERIMENTAL_METHODS: {sorted(undeclared)}"
    )
    assert not stale, (
        f"Methods declared experimental now resolve on the production route table; "
        f"remove them from EXPERIMENTAL_METHODS and update regengine/README.md: {sorted(stale)}"
    )
    assert not unknown, f"EXPERIMENTAL_METHODS names methods this test does not drive: {sorted(unknown)}"


def test_unsupported_sdk_methods_are_removed():
    """#2531 → WS-11: create_record / check_ftl had no real route. They first
    became loud NotImplementedError stubs; WS-11 removed them entirely so the
    installed client exposes only methods with registered routes behind them.
    This pins the removal — reintroducing either name must come with a real
    route (and a drive() scenario in _captured_sdk_calls)."""
    client = RegEngineClient(api_key="rge_test")
    try:
        assert not hasattr(client, "create_record")
        assert not hasattr(client, "check_ftl")
    finally:
        client._session.close()
