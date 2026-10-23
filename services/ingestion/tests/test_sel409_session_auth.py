"""SEL-409: workspace sessions reach the control plane without an API key."""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from app import authz
from app.authz import IngestionPrincipal
from app.canonical_router import router as records_router
from app.exception_router import router as exceptions_router
from app.request_workflow_router import router as requests_router
from app.routes_ingest import router as ingest_router
from app.rules_router import router as rules_router
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from shared.database import get_db_session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("credential_headers", "expected_cookie", "expected_token"),
    [
        ([(b"cookie", b"__Host-regengine_session=valid-session")], "valid-session", None),
        ([(b"authorization", b"Bearer signed-token")], None, "signed-token"),
    ],
)
async def test_session_principal_uses_admin_verifier_and_server_tenant(
    monkeypatch, credential_headers, expected_cookie, expected_token
):
    monkeypatch.setenv("ADMIN_DATABASE_URL", "sqlite:///:memory:")
    from shared.tenant_context import set_rls_tenant_id

    from services.admin.app import auth_routes, database, dependencies

    db = object()
    checked = []

    async def verify_user(request, token, db, session_store):
        checked.append((request.cookies.get("__Host-regengine_session"), token, db))
        set_rls_tenant_id("11111111-1111-4111-8111-111111111111")
        return SimpleNamespace(id="owner")

    monkeypatch.setattr(database, "SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr(database, "arm_global_admin_context", lambda _db: None)
    monkeypatch.setattr(database, "disarm_global_admin_context", lambda _db: None)
    monkeypatch.setattr(dependencies, "get_current_user", verify_user)
    monkeypatch.setattr(auth_routes, "_resolve_session_permissions", lambda **_kw: ["records.read"])

    request = Request({
        "type": "http", "method": "GET", "path": "/api/v1/records",
        "headers": credential_headers + [(b"x-tenant-id", b"22222222-2222-4222-8222-222222222222")],
    })
    principal = await authz._principal_from_user_session(request)

    assert checked == [(expected_cookie, expected_token, db)]
    assert principal.tenant_id == "11111111-1111-4111-8111-111111111111"
    assert principal.scopes == ["records.read"]
    assert principal.auth_mode == "session"
    set_rls_tenant_id(None)


def test_session_reaches_all_workspace_endpoints_without_api_key(monkeypatch):
    calls = []

    async def verified_session(request):
        calls.append(request.url.path)
        if request.cookies.get("__Host-regengine_session") != "valid-session":
            raise HTTPException(status_code=401, detail="Authentication required")
        return IngestionPrincipal(
            key_id="session:owner",
            scopes=["*"],
            tenant_id="11111111-1111-4111-8111-111111111111",
            auth_mode="session",
        )

    monkeypatch.setattr(authz, "_principal_from_user_session", verified_session)
    monkeypatch.setattr(authz, "_check_auth_rate_limit", lambda _ip: None)
    monkeypatch.setattr(authz, "_record_auth_failure", lambda _ip: None)
    monkeypatch.setattr(authz, "_is_dev_env", lambda: False)
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 10))

    app = FastAPI()
    for router in (
        records_router, rules_router, exceptions_router, requests_router,
        ingest_router,
    ):
        app.include_router(router)
    app.dependency_overrides[get_db_session] = lambda: None
    client = TestClient(app)
    cookies = {"__Host-regengine_session": "valid-session"}

    for path in (
        "/api/v1/records", "/api/v1/rules", "/api/v1/exceptions", "/api/v1/requests",
    ):
        response = client.get(path, cookies=cookies)
        assert response.status_code == 503, (path, response.status_code)
        assert calls[-1] == path

    for path, kwargs in (
        ("/v1/ingest/url", {"json": {}}),
    ):
        before = len(calls)
        response = client.post(path, cookies=cookies, **kwargs)
        assert response.status_code != 401, (path, response.status_code)
        assert len(calls) == before + 1, path

    response = client.get("/api/v1/records")
    assert response.status_code == 401
    assert len(calls) == 5

    for kwargs in (
        {"headers": {"X-Tenant-ID": "22222222-2222-4222-8222-222222222222"}},
        {"params": {"tenant_id": "22222222-2222-4222-8222-222222222222"}},
    ):
        response = client.get("/api/v1/records", cookies=cookies, **kwargs)
        assert response.status_code == 403

    assert client.get(
        "/api/v1/records", cookies={"__Host-regengine_session": "expired"}
    ).status_code == 401


def test_invalid_key_never_downgrades_to_session(monkeypatch):
    async def unexpected_session(_request):
        raise AssertionError("Session must not replace a presented API key")

    monkeypatch.setattr(authz, "_principal_from_user_session", unexpected_session)
    monkeypatch.setattr(authz, "_check_auth_rate_limit", lambda _ip: None)
    monkeypatch.setattr(authz, "_record_auth_failure", lambda _ip: None)

    app = FastAPI()
    app.include_router(records_router)
    response = TestClient(app).get(
        "/api/v1/records",
        cookies={"__Host-regengine_session": "valid-session"},
        headers={"X-RegEngine-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_verified_bearer_session_reaches_records(monkeypatch):
    async def verified_user(_request):
        return IngestionPrincipal(
            key_id="session:owner", scopes=["records.read"],
            tenant_id="11111111-1111-4111-8111-111111111111", auth_mode="session",
        )

    monkeypatch.setattr(authz, "_principal_from_user_session", verified_user)
    monkeypatch.setattr(authz, "_check_auth_rate_limit", lambda _ip: None)
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 10))
    app = FastAPI()
    app.include_router(records_router)
    app.dependency_overrides[get_db_session] = lambda: None

    response = TestClient(app).get("/api/v1/records", headers={"Authorization": "Bearer signed-token"})
    assert response.status_code == 503
