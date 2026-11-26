"""Tenant-context regression tests for legacy ``_verify_api_key`` routers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import app.webhook_compat as webhook_compat
import pytest
from app import epcis_export, team_mgmt
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

TENANT_A = "00000000-0000-0000-0000-0000000000aa"
TENANT_B = "00000000-0000-0000-0000-0000000000bb"


def _install_scoped_key(monkeypatch, tenant_id: str = TENANT_A):
    async def _fake_require(*, request, x_regengine_api_key):
        request.state.api_key = SimpleNamespace(
            key_id="key-a",
            tenant_id=tenant_id,
        )
        return request.state.api_key

    monkeypatch.setattr(webhook_compat, "require_api_key", _fake_require)


def test_legacy_path_tenant_mismatch_rejected_before_handler(monkeypatch):
    _install_scoped_key(monkeypatch, TENANT_A)
    app = FastAPI()
    app.include_router(team_mgmt.router)

    response = TestClient(app).get(
        f"/api/v1/team/{TENANT_B}",
        headers={"X-RegEngine-API-Key": "scoped-key"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "E_TENANT_MISMATCH"


def test_legacy_json_body_tenant_mismatch_rejected_before_handler(monkeypatch):
    _install_scoped_key(monkeypatch, TENANT_A)
    query = Mock(side_effect=AssertionError("Unauthorized export must not query storage"))
    monkeypatch.setattr(epcis_export, "_query_tenant_events", query)
    app = FastAPI()
    app.include_router(epcis_export.router)

    response = TestClient(app).post(
        "/api/v1/export/epcis",
        headers={"X-RegEngine-API-Key": "scoped-key"},
        json={"tenant_id": TENANT_B, "format": "epcis"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "E_TENANT_MISMATCH"
    query.assert_not_called()


@pytest.mark.parametrize("headers", [{}, {"X-RegEngine-API-Key": "invalid-test-key"}])
def test_export_auth_failure_rejected_before_storage(monkeypatch, headers):
    async def _deny_key(*, request, x_regengine_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    monkeypatch.setattr(webhook_compat, "require_api_key", _deny_key)
    query = Mock(side_effect=AssertionError("Unauthorized export must not query storage"))
    monkeypatch.setattr(epcis_export, "_query_tenant_events", query)
    app = FastAPI()
    app.include_router(epcis_export.router)

    response = TestClient(app).post(
        "/api/v1/export/epcis",
        headers=headers,
        json={"tenant_id": TENANT_A, "format": "epcis"},
    )

    assert response.status_code == 401
    assert "regengine:exportMetadata" not in response.json()
    assert "X-RegEngine-Integrity-Verified" not in response.headers
    query.assert_not_called()
