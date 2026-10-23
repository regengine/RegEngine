"""Data-free regression checks for the SEL-409 authentication boundary."""

from contextlib import nullcontext

import pytest
from app import authz
from app.authz import get_ingestion_principal
from fastapi import HTTPException, Request
from shared.tenant_context import set_rls_tenant_id


def _request(path: str) -> Request:
    return Request({"type": "http", "method": "POST", "path": path, "headers": []})


@pytest.mark.asyncio
async def test_session_without_selected_rls_tenant_is_denied(monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.setenv("ADMIN_FALLBACK_SQLITE", "sqlite:///:memory:")
    monkeypatch.delenv("ADMIN_DATABASE_URL", raising=False)
    from services.admin.app import auth_routes, database, dependencies

    async def verified_user(**_kwargs):
        return object()

    monkeypatch.setattr(database, "SessionLocal", lambda: nullcontext(object()))
    monkeypatch.setattr(dependencies, "get_current_user", verified_user)
    monkeypatch.setattr(auth_routes, "_resolve_session_permissions", lambda **_kwargs: [])
    set_rls_tenant_id(None)
    with pytest.raises(HTTPException) as error:
        await authz._principal_from_user_session(_request("/api/v1/records"))
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_empty_tenant_entitlement_source_grants_nothing(monkeypatch):
    from services.admin.app import api_key_admin_store

    class EmptyKeyStore:
        def list_keys(self):
            return []

    monkeypatch.setattr(api_key_admin_store, "get_admin_api_key_store", EmptyKeyStore)
    assert await authz._tenant_jurisdictions("") == []


@pytest.mark.asyncio
async def test_missing_credentials_rejected_by_workspace(monkeypatch):
    monkeypatch.setattr(authz, "_check_auth_rate_limit", lambda _ip: None)
    monkeypatch.setattr(authz, "_record_auth_failure", lambda _ip: None)
    monkeypatch.setattr(authz, "_is_dev_env", lambda: False)
    with pytest.raises(HTTPException) as workspace_error:
        await get_ingestion_principal(_request("/api/v1/records"), None)
    assert workspace_error.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_credentials_rejected_by_epcis():
    pytest.importorskip("typesafe_sdk")
    from app.webhook_compat import _verify_api_key

    with pytest.raises(HTTPException) as error:
        await _verify_api_key(_request("/api/v1/epcis/events"), None)
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_internal_ingest_rejects_missing_principal_tenant():
    pytest.importorskip("typesafe_sdk")
    from app.webhook_compat import ingest_events

    with pytest.raises(PermissionError):
        await ingest_events(None, principal_tenant_id="")
