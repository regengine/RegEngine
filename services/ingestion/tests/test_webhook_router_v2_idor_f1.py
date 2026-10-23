"""Data-free authorization failures on webhook read routes."""

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

service_dir = Path(__file__).resolve().parent.parent
if str(service_dir) not in sys.path:
    sys.path.insert(0, str(service_dir))

import app.webhook_router_v2 as wr  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402


class TestPermissionEnforced:
    def test_recent_rejects_principal_without_permission(self):
        principal = IngestionPrincipal(key_id="", scopes=[], tenant_id=None)
        with pytest.raises(HTTPException) as exc:
            wr._enforce_webhooks_read_principal("", principal, scope="recent")
        assert exc.value.status_code == 403

    def test_chain_verify_rejects_principal_without_permission(self):
        principal = IngestionPrincipal(key_id="", scopes=[], tenant_id=None)
        with pytest.raises(HTTPException) as exc:
            wr._enforce_webhooks_read_principal("", principal, scope="chain_verify")
        assert exc.value.status_code == 403


class TestUnauthenticated:
    def test_unauthenticated_request_rejected(self):
        app = FastAPI()
        app.include_router(wr.router)
        app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
            key_id="", scopes=[], tenant_id=None
        )
        client = TestClient(app)
        for path in ("/api/v1/webhooks/recent", "/api/v1/webhooks/chain/verify"):
            response = client.get(path, params={"tenant_id": ""})
            assert response.status_code == 401
