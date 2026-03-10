"""API tests for QR/GS1 decode endpoint."""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import app.authz as authz
from app.authz import IngestionPrincipal, get_ingestion_principal
import app.qr_decoder as qr_decoder
from app.qr_decoder import router as qr_router

SAMPLE_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7+R1kAAAAASUVORK5CYII="
)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app = FastAPI()
    app.include_router(qr_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="scan-key",
        tenant_id="00000000-0000-0000-0000-000000000321",
        scopes=["scan.decode"],
        auth_mode="test",
    )
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kwargs: (True, 99))

    with TestClient(app) as test_client:
        yield test_client


def test_decode_qr_parses_gs1_digital_link(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        qr_decoder,
        "_decode_image_bytes",
        lambda _image_bytes: "https://id.example.com/01/09506000134352/10/LOT-2026-44/21/SER-778/17/260930",
    )

    response = client.post(
        "/api/v1/qr/decode",
        files={"file": ("sample.png", SAMPLE_PNG_BYTES, "image/png")},
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["raw_value"].startswith("https://id.example.com/")
    assert payload["fsma_compatible"] is True
    assert payload["fields"]["source_format"] == "digital_link"
    assert payload["fields"]["gtin"] == "09506000134352"
    assert payload["fields"]["traceability_lot_code"] == "LOT-2026-44"
    assert payload["fields"]["serial"] == "SER-778"
    assert payload["fields"]["expiry_date"] == "2026-09-30"
    assert payload["fields"]["valid_gtin"] is True


def test_decode_qr_parses_gs1_ai_fields(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gs = chr(29)
    monkeypatch.setattr(
        qr_decoder,
        "_decode_image_bytes",
        lambda _image_bytes: f"011061414100001910LOT-900{gs}172609301326080121SER-55",
    )

    response = client.post(
        "/api/v1/qr/decode",
        files={"file": ("sample.png", SAMPLE_PNG_BYTES, "image/png")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["fields"]["source_format"] == "gs1_ai"
    assert payload["fields"]["gtin"] == "10614141000019"
    assert payload["fields"]["traceability_lot_code"] == "LOT-900"
    assert payload["fields"]["serial"] == "SER-55"
    assert payload["fields"]["expiry_date"] == "2026-09-30"
    assert payload["fields"]["pack_date"] == "2026-08-01"


def test_decode_qr_rejects_non_image_upload(client: TestClient) -> None:
    response = client.post(
        "/api/v1/qr/decode",
        files={"file": ("sample.txt", b"not-an-image", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Upload must be an image content type"


def test_decode_qr_denied_without_scan_decode_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    app.include_router(qr_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="limited-key",
        tenant_id="00000000-0000-0000-0000-000000000321",
        scopes=["exchange.read"],
        auth_mode="test",
    )
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kwargs: (True, 99))

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/qr/decode",
            files={"file": ("sample.png", SAMPLE_PNG_BYTES, "image/png")},
        )

    assert response.status_code == 403
    assert "requires 'scan.decode'" in response.json()["detail"]

