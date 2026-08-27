"""Every published path must be mounted in production — #2861.

`scripts/generate_openapi.py` used to build the public spec from
`services/ingestion/main.py`. That entrypoint has no experimental-router gate,
so the committed spec advertised **9 of its 45 paths that production does not
mount** — 20% of the public contract returning 404 to every integrator and
every SDK generated from it.

The `openapi-public-spec` workflow made it worse rather than better: it
enforces that the committed file matches the generator output, so the drift
stayed consistent with a generator reading the wrong app, and therefore looked
verified.

The generator now builds from `server.main` under `REGENGINE_ENV=production`.
This test is the independent check on that — it does not ask the generator what
it produced, it asks the production app what it mounts, and compares.

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

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = _REPO_ROOT / "frontend" / "public" / "openapi.json"

# Mirrors _IMPORT_ONLY_ENV in scripts/generate_openapi.py. Import-only values:
# the child builds a route table and exits without serving anything.
_CHILD_ENV = {
    "REGENGINE_ENV": "production",
    "ENV": "production",
    "DATABASE_URL": "sqlite:///:memory:",
    "ADMIN_DATABASE_URL": "sqlite:///:memory:",
    "ADMIN_FALLBACK_SQLITE": "1",
    "AUTH_SECRET_KEY": "openapi-contract-test-import-only-not-a-real-secret-4f2b",
    "JWT_SECRET": "openapi-contract-test-import-only-not-a-real-jwt-secret-9c7e",
    "REGENGINE_API_KEY": "openapi-contract-test-import-only-not-a-real-key-1a3d",
    "TOOL_ACCESS_SECRET": "openapi-contract-test-import-only-not-a-real-tool-8e5c",
}

_CHILD_SCRIPT = """
import json, sys
sys.path.insert(0, {repo!r})
sys.path.insert(0, {services!r})
from server.main import app
from fastapi.routing import APIRoute
print("@@PATHS@@" + json.dumps(sorted({{r.path for r in app.routes if isinstance(r, APIRoute)}})))
"""


@pytest.fixture(scope="module")
def production_paths() -> set[str]:
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
    return set(json.loads(marker[-1][len("@@PATHS@@"):]))


@pytest.fixture(scope="module")
def published_paths() -> set[str]:
    return set(json.loads(_SPEC.read_text(encoding="utf-8"))["paths"])


def test_production_route_table_is_non_trivial(production_paths):
    """Guard the guard: an empty or tiny set would make the check below vacuous."""
    assert len(production_paths) > 100, (
        f"Only {len(production_paths)} production routes enumerated. The child process "
        f"probably failed to mount most routers, which would make the contract check "
        f"below pass for the wrong reason."
    )


def test_published_spec_is_non_empty(published_paths):
    assert published_paths, "The published spec has no paths — nothing to verify."


def test_every_published_path_is_mounted_in_production(published_paths, production_paths):
    """The #2861 defect itself."""
    dead = sorted(published_paths - production_paths)
    assert not dead, (
        f"{len(dead)} path(s) are published in frontend/public/openapi.json but are NOT "
        f"mounted by the production monolith, so they 404 for every integrator and every "
        f"SDK generated from the spec:\n  " + "\n  ".join(dead) + "\n\n"
        f"This is usually an experimental router: server.main auto-disables "
        f"_EXPERIMENTAL_ROUTERS when REGENGINE_ENV=production. Regenerate with "
        f"`python scripts/generate_openapi.py`, which now builds from the production "
        f"app, rather than adding the path to an allowlist (#2861)."
    )
