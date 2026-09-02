import importlib
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from server.router_policy import PRODUCTION_ENABLED_ROUTERS

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
    assert "repair_null_email_fingerprints()" in src


@pytest.mark.asyncio
async def test_lifespan_runtime_rls_gate_is_unwrapped_and_precedes_workers(monkeypatch):
    """An inert/unknown runtime role must abort before auth or workers start."""
    main = importlib.import_module("server.main")
    admin_database = importlib.import_module("services.admin.app.database")
    auth_runtime = importlib.import_module("services.admin.app.auth_runtime")
    db_type_assertions = importlib.import_module("shared.db_type_assertions")
    external_connectors = importlib.import_module("shared.external_connectors.register_all")
    s3_utils = importlib.import_module("services.ingestion.app.s3_utils")
    shared_database = importlib.import_module("shared.database")
    task_processor = importlib.import_module("server.workers.task_processor")

    events: list[str] = []

    class RuntimePostureRejected(RuntimeError):
        pass

    def reject_runtime_posture(runtime_engine, sysadmin_engine):
        assert runtime_engine is shared_database.engine
        assert sysadmin_engine is admin_database._engine
        events.append("rls-posture")
        raise RuntimePostureRejected("inert runtime RLS posture")

    async def initialize_auth_runtime():
        events.append("auth-runtime")
        return object()

    def start_task_worker():
        events.append("task-worker")
        raise AssertionError("task worker started before the RLS posture gate")

    monkeypatch.setattr(s3_utils, "is_object_storage_configured", lambda: True)
    monkeypatch.setattr(admin_database, "init_db", lambda: None)
    monkeypatch.setattr(db_type_assertions, "verify_orm_db_type_alignment", lambda *_args: None)
    monkeypatch.setattr(external_connectors, "register_all_connectors", lambda: None)
    monkeypatch.setattr(shared_database, "validate_runtime_database_posture", reject_runtime_posture)
    monkeypatch.setattr(auth_runtime, "initialize_auth_runtime", initialize_auth_runtime)
    monkeypatch.setattr(task_processor, "start_task_worker", start_task_worker)

    with pytest.raises(RuntimePostureRejected, match="inert runtime RLS posture"):
        async with main.lifespan(main.app):
            pass

    assert events == ["rls-posture"]


def test_lifespan_initializes_and_always_shuts_down_auth_runtime():
    """The deployed monolith must not omit cluster-wide revocation wiring."""
    main = importlib.import_module("server.main")
    src = inspect.getsource(main.lifespan)

    initialize = "auth_runtime = await initialize_auth_runtime()"
    workers = "start_task_worker()"
    shutdown = 'await _shutdown_step("shutdown_auth_runtime"'
    assert initialize in src
    assert shutdown in src
    assert src.index(initialize) < src.index(workers) < src.index(shutdown)
    assert "finally:" in src[src.index(initialize) : src.index(shutdown)]
    assert "shutdown_auth_runtime(auth_runtime)" in src


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
    "mounted_routers": sorted(main._MOUNTED_ROUTERS),
    "excluded_routes_present": sorted(
        route for route in routes
        if route in {
            "POST /v1/scrape/cppa",
            "GET /v1/ingest/discovery/queue",
            "POST /api/v1/sandbox/evaluate",
            "POST /api/v1/query/traceability",
            "GET /api/v1/provisions/by-request",
            "GET /api/v1/simulations/scenarios",
            "POST /api/v1/suppliers/validation/{tenant_id}/validate",
        }
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
                "DISABLED_ROUTERS",
                "ENABLED_ROUTERS",
                "ENABLE_EXPERIMENTAL_ROUTERS",
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
                "ENABLED_ROUTERS": ",".join(sorted(PRODUCTION_ENABLED_ROUTERS)),
                "REDIS_URL": "redis://localhost:6379/15",
                "RATE_LIMIT_FAIL_MODE": "closed",
                "RAILWAY_ENVIRONMENT_NAME": "production",
                "SESSION_STORE_BACKEND": "database",
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
            "mounted_routers": sorted(PRODUCTION_ENABLED_ROUTERS),
            "excluded_routes_present": [],
        }
