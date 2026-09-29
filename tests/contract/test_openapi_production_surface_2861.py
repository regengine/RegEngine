"""Every published path must be mounted in production — #2861.

Both public OpenAPI URLs serve frontend/src/lib/public-openapi.ts. The former
generator and static JSON artifact were removed in 85df24ed. Load that maintained
spec and independently compare its operations against server.main with the exact
release-approved production router allowlist.

**Why a subprocess.** The production route set depends on module-level state
evaluated at import (`_is_prod` gates `_router_enabled`). By the time this test
runs, `server.main` may already be imported under a different environment, and
re-importing would return the cached module. The env also cannot simply be set
for the whole session: `services/ingestion/main.py` raises under
`REGENGINE_ENV=production` via `assert_legacy_entrypoint_not_in_production`, so
a global switch would break every test that builds the ingestion app. A clean
child process is the only way to observe the real production mount set without
disturbing anything else.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.contract.public_openapi import load_public_openapi

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Import-only values:
# the child builds a route table and exits without serving anything.
_CHILD_ENV = {
    "REGENGINE_ENV": "production",
    "ENV": "production",
    "DATABASE_URL": "sqlite:///:memory:",
    "ADMIN_DATABASE_URL": "sqlite:///:memory:",
    "ADMIN_FALLBACK_SQLITE": "1",
    # Strict auth validates this setting at import; no lifespan is started.
    "REDIS_URL": "redis://127.0.0.1:1/0",
    "AUTH_SECRET_KEY": "openapi-contract-test-import-only-not-a-real-secret-4f2b",
    "JWT_SECRET": "openapi-contract-test-import-only-not-a-real-jwt-secret-9c7e",
    "REGENGINE_API_KEY": "openapi-contract-test-import-only-not-a-real-key-1a3d",
    "TOOL_ACCESS_SECRET": "openapi-contract-test-import-only-not-a-real-tool-8e5c",
}

_CHILD_SCRIPT = """
import json, os, sys
sys.path.insert(0, {repo!r})
sys.path.insert(0, {services!r})
from server.router_policy import PRODUCTION_ENABLED_ROUTERS
os.environ["ENABLED_ROUTERS"] = ",".join(sorted(PRODUCTION_ENABLED_ROUTERS))
from server.main import app
from fastapi.routing import APIRoute
print("@@PATHS@@" + json.dumps(sorted({{(r.path, method.lower()) for r in app.routes if isinstance(r, APIRoute) for method in r.methods}})))
"""


@pytest.fixture(scope="module")
def production_operations() -> set[tuple[str, str]]:
    env = {**os.environ, **_CHILD_ENV}
    env.pop("ENABLE_EXPERIMENTAL_ROUTERS", None)  # default production posture
    env.pop("DISABLED_ROUTERS", None)
    # Test-only vars the production config validator rejects outright. Inheriting
    # them from the pytest environment makes the child refuse to start, which
    # would look like a contract failure rather than an environment one.
    for _test_only in ("AUTH_TEST_BYPASS_TOKEN", "ALLOW_LEGACY_ENTRYPOINT_IN_PROD"):
        env.pop(_test_only, None)
    script = _CHILD_SCRIPT.format(repo=str(_REPO_ROOT), services=str(_REPO_ROOT / "services"))
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_REPO_ROOT),
        timeout=300,
    )
    marker = [ln for ln in proc.stdout.splitlines() if ln.startswith("@@PATHS@@")]
    if not marker:
        pytest.fail(
            "Could not enumerate the production route table.\n"
            f"exit={proc.returncode}\nstdout tail:\n{proc.stdout[-1500:]}\n"
            f"stderr tail:\n{proc.stderr[-1500:]}"
        )
    return {tuple(operation) for operation in json.loads(marker[-1][len("@@PATHS@@") :])}


@pytest.fixture(scope="module")
def spec() -> dict:
    return load_public_openapi()


def test_production_route_table_is_non_trivial(production_operations):
    """Guard the guard: an empty or tiny set would make the check below vacuous."""
    assert len(production_operations) > 100, (
        f"Only {len(production_operations)} production operations enumerated. The child process "
        f"probably failed to mount most routers, which would make the contract check "
        f"below pass for the wrong reason."
    )


def test_published_spec_is_the_curated_public_surface(spec):
    assert set(spec["paths"]) == {
        "/api/v1/webhooks/ingest",
        "/api/v1/webhooks/recent",
        "/api/v1/webhooks/chain/verify",
        "/api/v1/records/ingestion-runs",
        "/api/v1/fda/export/all",
    }


def test_every_published_operation_is_mounted_in_production(spec, production_operations):
    """The #2861 defect itself."""
    published_operations = {
        (path, method)
        for path, item in spec["paths"].items()
        for method in item
        if method in {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
    }
    dead = sorted(published_operations - production_operations)
    assert not dead, (
        f"{len(dead)} operation(s) are published in frontend/src/lib/public-openapi.ts but are NOT "
        f"mounted by the production monolith, so they 404 for every integrator and every "
        f"SDK generated from the spec:\n  " + "\n  ".join(f"{method.upper()} {path}" for path, method in dead)
    )


class TestPublicSpecIsEnvironmentIndependent:
    """Backend environment overrides must not alter the curated public spec."""

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("ENABLE_EXPERIMENTAL_ROUTERS", "1"),
            ("DISABLED_ROUTERS", "fda_export,csv"),
            ("ENABLED_ROUTERS", "admin"),
            ("REGENGINE_ENV", "development"),
            ("REGENGINE_ENV", "test"),
            ("ENV", "staging"),
        ],
    )
    def test_router_overrides_do_not_change_the_published_spec(self, spec, name, value):
        assert load_public_openapi({name: value}) == spec
