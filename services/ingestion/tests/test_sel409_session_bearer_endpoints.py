"""SEL-409 regression: a verified session bearer, with no API key, reaches the
records, rules, exceptions, requests and ingest auth gates.

The admin verifier is replaced by one that accepts only a token generated in
this test (uuid4) and binds a uuid4 tenant, standing in for the real
signature/expiry/membership checks in ``services.admin.app.dependencies``.
Unverified bearers must still be rejected, and API keys still take the
API-key path.
"""

from __future__ import annotations

import uuid
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from app import authz
from app.authz import IngestionPrincipal, require_permission
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

SESSION_ENDPOINTS = [
    ("/api/v1/records", "records.read"),
    ("/api/v1/rules", "rules.read"),
    ("/api/v1/exceptions", "exceptions.read"),
    ("/api/v1/requests", "requests.read"),
    ("/api/v1/ingest/csv", "webhooks.ingest"),
]


@pytest.fixture
def session_env(monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.setenv("ADMIN_FALLBACK_SQLITE", "sqlite:///:memory:")
    monkeypatch.delenv("ADMIN_DATABASE_URL", raising=False)
    from shared.tenant_context import set_rls_tenant_id

    from services.admin.app import auth_routes, database, dependencies

    good_token = uuid.uuid4().hex
    tenant_id = str(uuid.uuid4())
    user_id = uuid.uuid4()
    calls = {"api_key": 0}

    async def verifier(*, request, token, db, session_store):
        if token != good_token:
            raise HTTPException(status_code=401, detail="Could not validate credentials")
        set_rls_tenant_id(tenant_id)
        return SimpleNamespace(id=user_id)

    async def fake_require_api_key(*, request, x_regengine_api_key):
        calls["api_key"] += 1
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    monkeypatch.setattr(dependencies, "get_current_user", verifier)
    monkeypatch.setattr(database, "SessionLocal", lambda: nullcontext(object()))
    monkeypatch.setattr(
        auth_routes,
        "_resolve_session_permissions",
        lambda **_kw: [scope for _path, scope in SESSION_ENDPOINTS],
    )

    async def no_jurisdictions(_tenant):
        return []

    monkeypatch.setattr(authz, "_tenant_jurisdictions", no_jurisdictions)
    monkeypatch.setattr(authz, "require_api_key", fake_require_api_key)
    monkeypatch.setattr(authz, "_check_auth_rate_limit", lambda _ip: None)
    monkeypatch.setattr(authz, "_record_auth_failure", lambda _ip: None)
    monkeypatch.setattr(authz, "_is_dev_env", lambda: False)
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 100), raising=False)

    app = FastAPI()
    for path, scope in SESSION_ENDPOINTS:

        def _make(dep):
            async def endpoint(principal: IngestionPrincipal = Depends(dep)):
                return {"tenant_id": principal.tenant_id, "auth_mode": principal.auth_mode}

            return endpoint

        app.add_api_route(path, _make(require_permission(scope)), methods=["GET"])
    set_rls_tenant_id(None)
    return SimpleNamespace(
        client=TestClient(app), token=good_token, tenant_id=tenant_id, calls=calls
    )


@pytest.mark.parametrize("path", [p for p, _ in SESSION_ENDPOINTS])
def test_verified_session_bearer_without_api_key_is_accepted(session_env, path):
    response = session_env.client.get(path, headers={"Authorization": f"Bearer {session_env.token}"})
    assert response.status_code == 200, response.text
    assert response.json() == {"tenant_id": session_env.tenant_id, "auth_mode": "session"}
    assert session_env.calls["api_key"] == 0


@pytest.mark.parametrize("path", [p for p, _ in SESSION_ENDPOINTS])
def test_unverified_session_bearer_is_rejected(session_env, path):
    forged = uuid.uuid4().hex
    response = session_env.client.get(path, headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


@pytest.mark.parametrize("path", [p for p, _ in SESSION_ENDPOINTS])
def test_session_cannot_pivot_to_another_tenant(session_env, path):
    response = session_env.client.get(
        path,
        params={"tenant_id": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {session_env.token}"},
    )
    assert response.status_code in (403, 409)


@pytest.mark.parametrize("path", [p for p, _ in SESSION_ENDPOINTS])
def test_api_key_still_takes_api_key_path(session_env, path):
    response = session_env.client.get(path, headers={"X-RegEngine-API-Key": uuid.uuid4().hex})
    assert response.status_code == 401
    assert session_env.calls["api_key"] == 1


@pytest.mark.parametrize("path", [p for p, _ in SESSION_ENDPOINTS])
def test_no_credentials_rejected(session_env, path):
    assert session_env.client.get(path).status_code == 401


def _depends_on(dependant, target) -> bool:
    for dep in dependant.dependencies:
        if dep.call is target or _depends_on(dep, target):
            return True
    return False


@pytest.mark.parametrize(
    "module_name",
    [
        "app.canonical_router",
        "app.rules_router",
        "app.exception_router",
        "app.request_workflow_router",
    ],
)
def test_workspace_routers_gate_on_session_capable_principal(module_name):
    import importlib

    module = importlib.import_module(module_name)
    routes = [r for r in module.router.routes if hasattr(r, "dependant")]
    assert routes
    for route in routes:
        assert _depends_on(route.dependant, authz.get_ingestion_principal), route.path


def test_csv_ingest_gates_on_session_capable_principal():
    from app import csv_templates

    routes = [r for r in csv_templates.router.routes if getattr(r, "path", "").endswith("/ingest/csv")]
    assert routes
    for route in routes:
        assert _depends_on(route.dependant, authz.get_ingestion_principal)
