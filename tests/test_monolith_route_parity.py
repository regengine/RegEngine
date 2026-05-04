"""Route parity checks for the consolidated FastAPI app.

The standalone services still define the source router surfaces. The monolith
must mount those same routes, otherwise a deployment can silently drop working
endpoints when traffic moves from a service process to ``server.main``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]

ROUTE_ENV = {
    "REGENGINE_ENV": "test",
    "ENVIRONMENT": "test",
    "DATABASE_URL": "postgresql://localhost:5432/regengine_test",
    "ADMIN_DATABASE_URL": (
        "postgresql+psycopg://localhost:5432/regengine_admin_test"
    ),
    "AUTH_SECRET_KEY": "test-secret-key-with-enough-length",  # pragma: allowlist secret
    "ENABLE_PARTNER_GATEWAY_STUBS": "true",
    "ENABLE_EXPERIMENTAL_ROUTERS": "true",
}

ROUTE_SCRIPT = r"""
import importlib
import json
import os

from fastapi.routing import APIRoute

module = importlib.import_module(os.environ["REGENGINE_ROUTE_MODULE"])
route_keys = set()
for route in module.app.routes:
    if not isinstance(route, APIRoute):
        continue
    for method in route.methods or ():
        if method not in {"HEAD", "OPTIONS"}:
            route_keys.add(f"{method} {route.path}")

print("ROUTE_KEYS_JSON=" + json.dumps(sorted(route_keys)))
"""


def _route_keys(module_name: str) -> set[str]:
    env = os.environ.copy()
    env.update(ROUTE_ENV)
    env["REGENGINE_ROUTE_MODULE"] = module_name

    result = subprocess.run(
        [sys.executable, "-c", ROUTE_SCRIPT],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, (
        f"failed to import {module_name}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )

    output = result.stdout.splitlines() + result.stderr.splitlines()
    for line in reversed(output):
        if line.startswith("ROUTE_KEYS_JSON="):
            return set(json.loads(line.removeprefix("ROUTE_KEYS_JSON=")))

    pytest.fail(
        f"route extraction for {module_name} produced no marker\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


@pytest.fixture(scope="module")
def monolith_routes() -> set[str]:
    return _route_keys("server.main")


@pytest.mark.parametrize(
    ("service_name", "module_name"),
    [
        ("admin", "services.admin.main"),
        ("ingestion", "services.ingestion.main"),
    ],
)
def test_monolith_mounts_standalone_service_routes(
    monolith_routes: set[str], service_name: str, module_name: str
) -> None:
    service_routes = _route_keys(module_name)
    missing = service_routes - monolith_routes

    assert not missing, (
        f"server.main is missing {service_name} routes mounted by {module_name}:\n"
        + "\n".join(f"  {route}" for route in sorted(missing))
    )
