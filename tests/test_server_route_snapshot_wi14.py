"""The production route set of ``server.main`` is pinned (tech-debt WI-14).

``server/main.py`` was split into ``startup_checks.py``, ``workers_boot.py``,
``routers_mount.py`` and ``readiness.py`` with no behaviour change. This test
imports ``server.main`` in a child process under production posture with the
release-approved router set and compares every ``METHOD path`` APIRoute with
``tests/snapshots/server_main_production_routes.json``, which was generated
from the pre-split file. Regenerate the snapshot only for a deliberate route
change, with the ``--regenerate`` note below, and say so in the PR.

To regenerate: run this module's ``_collect()`` and write the list to the
snapshot file (``python -c "from tests.test_server_route_snapshot_wi14 import
_collect, SNAPSHOT; import json; json.dump(_collect(), open(SNAPSHOT, 'w'), indent=1)"``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = REPO_ROOT / "tests" / "snapshots" / "server_main_production_routes.json"


def _synthetic_fernet_key() -> str:
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


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
    "AUTH_SECRET_KEY": "route-snapshot-import-only-not-a-real-secret-4f2b",  # pragma: allowlist secret -- synthetic import-only value
    "JWT_SECRET": "route-snapshot-import-only-not-a-real-jwt-secret-9c7e",  # pragma: allowlist secret -- synthetic import-only value
    "REGENGINE_API_KEY": "route-snapshot-import-only-not-a-real-key-1a3d",  # pragma: allowlist secret -- synthetic import-only value
    "TOOL_ACCESS_SECRET": "route-snapshot-import-only-not-a-real-tool-8e5c",  # pragma: allowlist secret -- synthetic import-only value
}

_CHILD_SCRIPT = """
import json, os, sys
sys.path.insert(0, {repo!r})
sys.path.insert(0, {services!r})
from server.router_policy import PRODUCTION_ENABLED_ROUTERS
os.environ["ENABLED_ROUTERS"] = ",".join(sorted(PRODUCTION_ENABLED_ROUTERS))
from server.main import app
from fastapi.routing import APIRoute
rows = sorted({{f"{{m}} {{r.path}}" for r in app.routes if isinstance(r, APIRoute) for m in sorted(r.methods or [])}})
print("@@ROUTES@@" + json.dumps(rows))
"""


def _collect() -> list[str]:
    env = {**os.environ, **_CHILD_ENV, "MFA_ENCRYPTION_KEY": _synthetic_fernet_key()}
    # Router flags are set by the child; test-only variables the production
    # config validator rejects, and placeholder storage keys other suites
    # export, must not reach it (same scrub as the OpenAPI contract test).
    for key in (
        "ENABLED_ROUTERS",
        "DISABLED_ROUTERS",
        "ENABLE_EXPERIMENTAL_ROUTERS",
        "ALLOW_DISABLE_COMPLIANCE_ROUTERS",
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
        env.pop(key, None)
    script = _CHILD_SCRIPT.format(repo=str(REPO_ROOT), services=str(REPO_ROOT / "services"))
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=300
    )
    lines = [line for line in result.stdout.splitlines() if line.startswith("@@ROUTES@@")]
    assert lines, f"server.main import produced no route list\nstdout:\n{result.stdout[-2000:]}\nstderr:\n{result.stderr[-3000:]}"
    return json.loads(lines[0][len("@@ROUTES@@") :])


def test_production_route_set_matches_the_pre_split_snapshot():
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    actual = _collect()
    missing = sorted(set(expected) - set(actual))
    added = sorted(set(actual) - set(expected))
    assert not missing and not added, (
        f"production route set drifted from {SNAPSHOT.relative_to(REPO_ROOT)}\n"
        f"missing ({len(missing)}): {missing[:20]}\nadded ({len(added)}): {added[:20]}"
    )
    assert len(actual) == len(expected)
