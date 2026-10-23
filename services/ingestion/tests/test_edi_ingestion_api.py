"""Data-free validation checks for the EDI ingestion routes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.edi_ingestion.routes as edi_ingestion_routes  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.edi_ingestion import router as edi_router  # noqa: E402


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("EDI_REQUIRE_PARTNER_ID", raising=False)
    monkeypatch.delenv("EDI_PARTNER_ALLOWLIST", raising=False)
    # These checks stop before tenant resolution has any bearing on behavior.
    monkeypatch.setattr(edi_ingestion_routes, "_resolve_principal_tenant_id", lambda *args: "")
    app = FastAPI()
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="", scopes=["edi.ingest"]
    )
    with TestClient(app) as test_client:
        yield test_client


def _post(client: TestClient, raw: bytes, *, route: str = ""):
    return client.post(
        f"/api/v1/ingest/edi{route}",
        data={"traceability_lot_code": " "},
        files={"file": ("empty.edi", raw, "application/edi-x12")},
    )


def test_legacy_route_requires_file(client: TestClient) -> None:
    response = client.post("/api/v1/ingest/edi", data={"traceability_lot_code": " "})
    assert response.status_code == 422
    assert any("file" in error["loc"] for error in response.json()["detail"])


def test_ingest_rejects_empty_payload(client: TestClient) -> None:
    response = _post(client, b"")
    assert response.status_code == 400
    assert response.json()["detail"] == "Empty EDI payload"


def test_ingest_rejects_non_edi_payload(client: TestClient) -> None:
    response = _post(client, b" ")
    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported EDI payload format"


def test_ingest_rejects_non_856_transaction_set(client: TestClient) -> None:
    response = _post(client, b"ISA*~ST*850~")
    assert response.status_code == 400
    assert response.json()["detail"] == "Only X12 856 is currently supported"


def test_ingest_rejects_missing_required_segments(client: TestClient) -> None:
    response = _post(client, b"ISA*~GS~ST*856~SE~GE~IEA~")
    assert response.status_code == 422
    assert {"BSN", "HL"} <= set(response.json()["detail"]["missing_segments"])


def test_ingest_edi_856_rejects_oversize_before_parsing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(edi_ingestion_routes, "MAX_EDI_FILE_SIZE_BYTES", 0)
    response = _post(client, b"ISA")
    assert response.status_code == 413


def test_ingest_denied_without_edi_ingest_scope() -> None:
    app = FastAPI()
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(key_id="", scopes=[])
    with TestClient(app) as client:
        response = _post(client, b"")
    assert response.status_code == 403
    assert "requires 'edi.ingest'" in response.json()["detail"]


def test_document_route_requires_file(client: TestClient) -> None:
    response = client.post("/api/v1/ingest/edi/document", data={"traceability_lot_code": " "})
    assert response.status_code == 422
    assert any("file" in error["loc"] for error in response.json()["detail"])


def test_document_route_rejects_empty_payload(client: TestClient) -> None:
    response = _post(client, b"", route="/document")
    assert response.status_code == 400
    assert response.json()["detail"] == "Empty EDI payload"


def test_document_route_rejects_unrecognized_set(client: TestClient) -> None:
    response = _post(client, b"ISA~ST~", route="/document")
    assert response.status_code == 400
    assert response.json()["detail"].startswith("Unsupported or unrecognized transaction set")


def test_segment_cap_exceeded_returns_413(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDI_MAX_SEGMENTS", "1")
    response = _post(client, b"ISA~GS~", route="/document")
    assert response.status_code == 413
    assert response.json()["detail"]["error"] == "segment_count_exceeded"


def test_decode_preserves_latin1_byte() -> None:
    assert edi_ingestion_routes._decode_edi_bytes(bytes([0xF1])) == "ñ"
