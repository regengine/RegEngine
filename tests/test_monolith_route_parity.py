"""Route parity checks for the consolidated FastAPI app.

The standalone services still define the source router surfaces. The monolith
must mount those same routes, otherwise a deployment can silently drop working
endpoints when traffic moves from a service process to ``server.main``.

Two properties are checked for every discoverable service, not just a
hard-coded pair:

- every ``METHOD path`` served by the standalone service is also served by
  the monolith (lost routes fail the build);
- every shared ``METHOD path`` carries the same auth-guard dependency set in
  both apps (a dropped or swapped guard fails the build).

Auth guards are fingerprinted as the sorted ``module:name`` keys of every
dependency in the route's FastAPI dependant tree, the same signal the
production security manifest in ``server/route_security_policy.py`` derives
its classification from.
"""

from __future__ import annotations

import functools
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICES_DIR = REPO_ROOT / "services"

ROUTE_ENV = {
    "REGENGINE_ENV": "test",
    "ENVIRONMENT": "test",
    "DATABASE_URL": "postgresql://localhost:5432/regengine_test",
    "ADMIN_DATABASE_URL": ("postgresql+psycopg://localhost:5432/regengine_admin_test"),
    "AUTH_SECRET_KEY": "test-secret-key-with-enough-length",  # pragma: allowlist secret
    "ENABLE_EXPERIMENTAL_ROUTERS": "true",
}

# Standalone entrypoints that do not expose an HTTP app, so there is no
# route table to compare. The scheduler serves a stdlib ``/status`` handler
# and is prod-blocked; the monolith restores that surface on
# ``GET /v1/scheduler/status`` instead of mounting routes.
NON_HTTP_SERVICE_MODULES = {
    "services.scheduler.main": "stdlib status handler, no FastAPI app; covered by server/routes_scheduler_status.py",
}

# Shared service directories whose entrypoint module is not
# ``services.<name>.main`` (kept explicit so a wrong guess fails loudly
# instead of silently comparing the wrong app).
SERVICE_ENTRYPOINT_OVERRIDES = {
    "graph": "services.graph.app.main",
}

# Operations where the monolith intentionally serves a different handler than
# the standalone service under the same method plus path, so the auth-guard
# comparison does not apply. Each entry names the canonical monolith owner
# that wins the collision. The route itself must still exist on both apps.
KNOWN_DIVERGENT_AUTH_OPERATIONS = {
    # The consolidated /health and /metrics endpoints come from the
    # ingestion health router; the admin service-local compatibility
    # handlers with the same paths are excluded at mount time.
    ("GET", "/health"),
    ("GET", "/metrics"),
    # Same collision for the nlp service-local diagnostics, which the
    # monolith excludes in favour of the canonical endpoints.
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/metrics"),
}

ROUTE_SCRIPT = r"""
import importlib
import json
import os

module = importlib.import_module(os.environ["REGENGINE_ROUTE_MODULE"])

from shared.paths import ensure_shared_importable

ensure_shared_importable()
# Flattening lives in shared.route_introspection: since fastapi 0.137 a
# walk of module.app.routes sees included routers as single opaque entries,
# which would make both apps look like they mount almost nothing and let
# this parity check pass on two empty sets.
from shared.route_introspection import iter_effective_routes


def _callable_key(call):
    module_name = getattr(call, "__module__", None) or call.__class__.__module__
    name = getattr(call, "__name__", None) or call.__class__.__name__
    return f"{module_name}:{name}"


def _dependency_keys(route):
    keys = set()
    stack = list(route.dependant.dependencies)
    while stack:
        child = stack.pop()
        keys.add(_callable_key(child.call))
        stack.extend(child.dependencies)
    return sorted(keys)


table = {}
for path, route in iter_effective_routes(module.app):
    for method in route.methods or ():
        if method not in {"HEAD", "OPTIONS"}:
            table[f"{method} {path}"] = _dependency_keys(route)

print("ROUTE_TABLE_JSON=" + json.dumps(table, sort_keys=True))
"""


def _discover_service_modules() -> list[tuple[str, str]]:
    """Return ``(service_name, module_name)`` for every service entrypoint.

    Discovery is filesystem-driven so adding a service directory to
    ``services/`` extends this check instead of silently escaping it. A new
    directory must either map to an importable entrypoint (via
    ``SERVICE_ENTRYPOINT_OVERRIDES`` when its layout differs) or be recorded
    in ``NON_HTTP_SERVICE_MODULES`` with the reason it has no route table.
    """
    discovered: list[tuple[str, str]] = []
    for service_dir in sorted(SERVICES_DIR.iterdir()):
        if not service_dir.is_dir() or service_dir.name.startswith(("_", ".")):
            continue
        if service_dir.name == "shared":
            continue
        module_name = SERVICE_ENTRYPOINT_OVERRIDES.get(service_dir.name, f"services.{service_dir.name}.main")
        if module_name in NON_HTTP_SERVICE_MODULES:
            continue
        if (REPO_ROOT / module_name.replace(".", "/")).with_suffix(".py").is_file():
            discovered.append((service_dir.name, module_name))
    return discovered


SERVICE_MODULES = _discover_service_modules()


@functools.lru_cache(maxsize=None)
def _route_table(module_name: str) -> dict[str, list[str]]:
    # Cached so the mounts check and the auth-guard check share one
    # subprocess extraction per service instead of importing each app twice.
    env = os.environ.copy()
    env.update(ROUTE_ENV)
    env["REGENGINE_ROUTE_MODULE"] = module_name

    result = subprocess.run(
        [sys.executable, "-c", ROUTE_SCRIPT],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, f"failed to import {module_name}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    output = result.stdout.splitlines() + result.stderr.splitlines()
    for line in reversed(output):
        if line.startswith("ROUTE_TABLE_JSON="):
            table = json.loads(line.removeprefix("ROUTE_TABLE_JSON="))
            assert table, f"route extraction for {module_name} returned no routes"
            return table

    pytest.fail(
        f"route extraction for {module_name} produced no marker\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.fixture(scope="module")
def monolith_table() -> dict[str, list[str]]:
    table = _route_table("server.main")
    # Vacuous-pass self-check: the consolidated app serves hundreds of
    # operations; a tiny table means enumeration broke, not that parity holds.
    assert len(table) > 100, f"monolith route enumeration returned only {len(table)} operations"
    return table


def test_service_discovery_covers_known_http_services() -> None:
    names = {name for name, _ in SERVICE_MODULES}
    assert {"admin", "compliance", "graph", "ingestion", "nlp"} <= names, (
        f"service discovery lost an entrypoint: {sorted(names)}"
    )


@pytest.mark.parametrize(
    ("service_name", "module_name"),
    SERVICE_MODULES,
)
def test_monolith_mounts_standalone_service_routes(
    monolith_table: dict[str, list[str]], service_name: str, module_name: str
) -> None:
    service_table = _route_table(module_name)
    missing = set(service_table) - set(monolith_table)

    assert not missing, f"server.main is missing {service_name} routes mounted by {module_name}:\n" + "\n".join(
        f"  {route}" for route in sorted(missing)
    )


@pytest.mark.parametrize(
    ("service_name", "module_name"),
    SERVICE_MODULES,
)
def test_monolith_preserves_standalone_service_auth_guards(
    monolith_table: dict[str, list[str]], service_name: str, module_name: str
) -> None:
    service_table = _route_table(module_name)
    drifted: list[str] = []
    for route in sorted(set(service_table) & set(monolith_table)):
        method, _, path = route.partition(" ")
        if (method, path) in KNOWN_DIVERGENT_AUTH_OPERATIONS:
            continue
        service_guards = service_table[route]
        monolith_guards = monolith_table[route]
        if service_guards != monolith_guards:
            drifted.append(f"  {route}:\n    {module_name}: {service_guards}\n    server.main: {monolith_guards}")

    assert not drifted, (
        f"server.main serves {service_name} routes with different auth guards than {module_name}:\n"
        + "\n".join(drifted)
    )


@pytest.mark.parametrize(
    "route",
    [
        "POST /api/v1/proof/verify",
        "POST /api/v1/proof/recall-drill",
    ],
)
def test_public_proof_routes_are_mounted_on_ingestion_and_monolith(
    monolith_table: dict[str, list[str]], route: str
) -> None:
    ingestion_table = _route_table("services.ingestion.main")

    assert route in ingestion_table
    assert route in monolith_table
