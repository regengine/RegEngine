import importlib
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_consolidated_backend_imports():
    module = importlib.import_module("server.main")

    assert hasattr(module, "app")


def test_lifespan_verifies_admin_and_api_key_bases_at_startup():
    """Phase 2 wiring contract.

    ``server.main.lifespan`` runs ``verify_orm_db_type_alignment`` for every
    Base on the production hot path. The function itself is unit-tested
    elsewhere; this test asserts the call sites stay wired up so that
    silently dropping an ORM surface from the startup drift check shows
    up as a failing test, not a prod 500 storm.
    """
    main = importlib.import_module("server.main")
    src = inspect.getsource(main.lifespan)

    # Both call sites must be present and use the expected (engine, base)
    # pairs. If a future refactor renames a binding, update this test
    # along with the new wiring — the criteria for adding a Base here
    # are documented inline in server/main.py.
    assert "verify_orm_db_type_alignment(_admin_engine, _admin_base)" in src
    assert "verify_orm_db_type_alignment(_shared_engine, _api_key_base)" in src


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
                "ADMIN_DATABASE_URL",
                # Test envs set this; a real Railway deploy never has it.
                "ADMIN_FALLBACK_SQLITE",
                "AUTH_TEST_BYPASS_TOKEN",
                "DATABASE_URL",
                "ENV",
                "REGENGINE_ENV",
            }
        }
        database_url = "postgresql://regengine_cloud_test:regengine_cloud_test@localhost:5432/regengine_cloud_test"  # pragma: allowlist secret
        env.update(
            {
                # Railway always provides both DB URLs; without them the admin
                # engine correctly refuses to boot in a cloud environment.
                "ADMIN_DATABASE_URL": database_url,
                "AUTH_SECRET_KEY": "test-secret-key-for-railway-docs-lockdown",  # pragma: allowlist secret
                "DATABASE_URL": database_url,
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
            json.loads(line.removeprefix(marker)) for line in result.stdout.splitlines() if line.startswith(marker)
        )
        assert payload == {
            "docs_url": None,
            "redoc_url": None,
            "openapi_url": None,
            "docs_routes": [],
        }
