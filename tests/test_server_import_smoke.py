import importlib
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_consolidated_backend_imports():
    module = importlib.import_module("server.main")

    assert hasattr(module, "app")


def test_railway_cloud_import_disables_public_docs():
    script = """
import json
from fastapi.routing import APIRoute
import server.main as main

routes = []
for route in main.app.routes:
    if isinstance(route, APIRoute):
        for method in route.methods or ():
            if method not in {"HEAD", "OPTIONS"}:
                routes.append(f"{method} {route.path}")

print("DOCS_RESULT_JSON=" + json.dumps({
    "docs_url": main.app.docs_url,
    "redoc_url": main.app.redoc_url,
    "openapi_url": main.app.openapi_url,
    "docs_routes": sorted(
        route for route in routes
        if route in {"GET /docs", "GET /redoc", "GET /openapi.json"}
    ),
}))
"""
    for regengine_env in (None, "staging"):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("RAILWAY_")
            and key
            not in {
                "AUTH_TEST_BYPASS_TOKEN",
                "DATABASE_URL",
                "ENV",
                "REGENGINE_ENV",
            }
        }
        env.update(
            {
                "AUTH_SECRET_KEY": "test-secret-key-for-railway-docs-lockdown",  # pragma: allowlist secret
                "DATABASE_URL": (
                    "postgresql://regengine_cloud_test:regengine_cloud_test"
                    "@localhost:5432/regengine_cloud_test"
                ),
                "REGENGINE_API_KEY": "rge_test_cloud_docs_lockdown",  # pragma: allowlist secret
                "RAILWAY_ENVIRONMENT_NAME": "production",
                "TOOL_ACCESS_SECRET": "tool-access-secret-for-railway-docs-lockdown",  # pragma: allowlist secret
            }
        )
        if regengine_env is not None:
            env["REGENGINE_ENV"] = regengine_env

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        assert result.returncode == 0, (
            "server.main import failed "
            f"for REGENGINE_ENV={regengine_env!r}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        marker = "DOCS_RESULT_JSON="
        payload = next(
            json.loads(line.removeprefix(marker))
            for line in result.stdout.splitlines()
            if line.startswith(marker)
        )
        assert payload == {
            "docs_url": None,
            "redoc_url": None,
            "openapi_url": None,
            "docs_routes": [],
        }
