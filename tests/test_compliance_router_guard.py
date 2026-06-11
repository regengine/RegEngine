"""Compliance-critical router guard in the production monolith (#979).

``DISABLED_ROUTERS`` must not silently disable FSMA 204-critical routers
in ``server/main.py``. The guard runs at import time, so each case
imports ``server.main`` in a fresh subprocess.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _import_server_main(extra_env: dict[str, str]) -> subprocess.CompletedProcess:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"ALLOW_DISABLE_COMPLIANCE_ROUTERS", "DISABLED_ROUTERS"}
    }
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", "import server.main"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_disabling_compliance_router_without_override_fails_startup():
    result = _import_server_main({"DISABLED_ROUTERS": "fda_export"})

    assert result.returncode != 0, (
        "server.main import should fail when fda_export is disabled "
        f"without override\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "RuntimeError" in result.stderr
    assert "ALLOW_DISABLE_COMPLIANCE_ROUTERS" in result.stderr
    assert "fda_export" in result.stderr


def test_disabling_compliance_router_with_override_succeeds():
    result = _import_server_main({"DISABLED_ROUTERS": "fda_export", "ALLOW_DISABLE_COMPLIANCE_ROUTERS": "true"})

    assert result.returncode == 0, (
        "ALLOW_DISABLE_COMPLIANCE_ROUTERS=true should allow startup\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
