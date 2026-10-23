"""Data-free API validation checks for the QR endpoint."""

from __future__ import annotations

import pytest
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.qr_decoder import router as qr_router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import app.authz as authz

    app = FastAPI()
    app.include_router(qr_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="", tenant_id=None, scopes=["scan.decode"]
    )
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kwargs: (True, 1))
    with TestClient(app) as test_client:
        yield test_client


def test_decode_qr_rejects_non_image_upload(client: TestClient) -> None:
    response = client.post(
        "/api/v1/qr/decode",
        files={"file": ("upload", b"", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Upload must be an image content type"


def test_decode_qr_rejects_empty_image_upload(client: TestClient) -> None:
    response = client.post(
        "/api/v1/qr/decode",
        files={"file": ("upload", b"", "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded image is empty"


def test_decode_qr_denied_without_scan_decode_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.authz as authz

    app = FastAPI()
    app.include_router(qr_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="", tenant_id=None, scopes=[]
    )
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kwargs: (True, 1))
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/qr/decode",
            files={"file": ("upload", b"", "image/png")},
        )
    assert response.status_code == 403
    assert "scan.decode" in response.json()["detail"]
