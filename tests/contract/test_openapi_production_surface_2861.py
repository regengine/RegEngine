"""The canonical curated public spec must match mounted production routes.

The TypeScript export replaced the retired Python generator/static asset.
Production routes are independently enumerated in an import-only subprocess.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Import-only values for production route enumeration:
# the child builds a route table and exits without serving anything.
_CHILD_ENV = {
    "REGENGINE_ENV": "production",
    "ENV": "production",
    "EVENT_BACKBONE": "pg",
    "REDIS_URL": "redis://127.0.0.1:6379/15",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "5",
    "SESSION_STORE_BACKEND": "redis",
    "DATABASE_URL": "sqlite:///:memory:",
    "ADMIN_DATABASE_URL": "sqlite:///:memory:",
    "ADMIN_FALLBACK_SQLITE": "1",
    "AUTH_SECRET_KEY": "openapi-contract-test-import-only-not-a-real-secret-4f2b",
    "JWT_SECRET": "openapi-contract-test-import-only-not-a-real-jwt-secret-9c7e",
    "REGENGINE_API_KEY": "openapi-contract-test-import-only-not-a-real-key-1a3d",
    "TOOL_ACCESS_SECRET": "openapi-contract-test-import-only-not-a-real-tool-8e5c",
    # DATABASE_URL (above) is the only startup credential the production
    # secret gate requires: optional subsystems stay disabled in the child
    # (the production router set has no graph; EVENT_BACKBONE is pg),
    # so no other credential values are seeded here. Never used to
    # connect anywhere — the child builds a route table and exits.
}

_CHILD_SCRIPT = """
import json, os, sys
sys.path.insert(0, {repo!r})
sys.path.insert(0, {services!r})
from server.router_policy import PRODUCTION_ENABLED_ROUTERS
os.environ["ENABLED_ROUTERS"] = ",".join(sorted(PRODUCTION_ENABLED_ROUTERS))
from server.main import app
from fastapi.routing import APIRoute
print("@@PATHS@@" + json.dumps(sorted({{r.path for r in app.routes if isinstance(r, APIRoute)}})))
"""


@pytest.fixture(scope="module")
def production_paths() -> set[str]:
    env = {**os.environ, **_CHILD_ENV}
    env.pop("ENABLE_EXPERIMENTAL_ROUTERS", None)  # default production posture
    env.pop("DISABLED_ROUTERS", None)
    # Test-only vars the production config validator rejects outright, plus
    # placeholder storage keys inherited from the pytest environment (other
    # suites export test-* values) that the secrets gate rejects as insecure
    # whenever set. Inheriting any of them makes the child refuse to start,
    # which would look like a contract failure rather than an environment one.
    for _test_only in (
        "AUTH_TEST_BYPASS_TOKEN",
        "ALLOW_LEGACY_ENTRYPOINT_IN_PROD",
        "ALLOW_INMEMORY_SESSION_STORE",
        "AUTH_ALLOW_LEGACY_JTI_FREE",
        "NEO4J_URI",
        "NEO4J_URL",
        "NEO4J_PASSWORD",
        "OBJECT_STORAGE_ACCESS_KEY_ID",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY",
    ):
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
    return set(json.loads(marker[-1][len("@@PATHS@@") :]))


@pytest.fixture(scope="module")
def published_paths(published_spec) -> set[str]:
    return set(published_spec()["paths"])


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
    assert not dead, f"{len(dead)} canonical public path(s) are not mounted in production:\n  " + "\n  ".join(dead)


class TestPublishedSpecIsEnvironmentIndependent:
    """Per-deploy backend knobs must not change the curated public contract."""

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            # Router overrides — the finding as originally reported.
            ("ENABLE_EXPERIMENTAL_ROUTERS", "1"),
            ("DISABLED_ROUTERS", "fda_export,csv"),
            # The deeper cause found while fixing it: the generator used
            # os.environ.setdefault, so an inherited REGENGINE_ENV won and it
            # built the non-production app. This is the common case, not an
            # exotic one — pytest exports REGENGINE_ENV=test, and plenty of
            # developers have REGENGINE_ENV=development in their shell.
            ("REGENGINE_ENV", "development"),
            ("REGENGINE_ENV", "test"),
            ("ENV", "staging"),
        ],
    )
    def test_router_overrides_do_not_change_the_published_spec(self, name, value, published_spec):
        baseline = published_spec()
        assert published_spec({**os.environ, name: value}) == baseline
