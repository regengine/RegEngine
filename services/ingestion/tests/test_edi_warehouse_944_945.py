"""Data-free checks for warehouse transaction set extraction."""

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
from app.edi_ingestion.extractors import _extract_fields_for_set  # noqa: E402
from app.edi_ingestion.routes import _quantity_element_present  # noqa: E402
from app.edi_ingestion.transaction_sets import _SUPPORTED_TRANSACTION_SETS  # noqa: E402


@pytest.mark.parametrize("transaction_set,header", [("944", "W17"), ("945", "W06")])
def test_warehouse_header_only_has_no_lines_or_location(transaction_set: str, header: str) -> None:
    extracted = _extract_fields_for_set(transaction_set, [["ST", transaction_set], [header]])
    assert extracted["line_items"] == []
    assert extracted["warehouse_name"] is None
    assert extracted["warehouse_gln"] is None
    assert extracted["reference_document_number"] is None
    if transaction_set == "944":
        assert extracted["receiving_location_name"] is None


@pytest.mark.parametrize("transaction_set,segment", [("944", "W07"), ("945", "W12")])
def test_warehouse_line_header_has_no_quantity(transaction_set: str, segment: str) -> None:
    assert _quantity_element_present(transaction_set, [[segment]]) is False


def test_unknown_transaction_set_keeps_the_same_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(edi_ingestion_routes, "_resolve_principal_tenant_id", lambda *args: "")
    monkeypatch.delenv("EDI_REQUIRE_PARTNER_ID", raising=False)
    monkeypatch.delenv("EDI_PARTNER_ALLOWLIST", raising=False)
    app = FastAPI()
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="", scopes=["edi.ingest"]
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ingest/edi/document",
            data={"traceability_lot_code": " "},
            files={"file": ("empty.edi", b"ISA*~ST~", "application/edi-x12")},
        )
    assert response.status_code == 400
    assert response.json()["detail"] == (
        f"Unsupported or unrecognized transaction set. Supported: {sorted(_SUPPORTED_TRANSACTION_SETS)}"
    )
