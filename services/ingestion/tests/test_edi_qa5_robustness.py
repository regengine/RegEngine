"""Data-free malformed-envelope and partner-gate regression checks."""

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
from app.edi_ingestion.parser import (  # noqa: E402
    _declared_transaction_set_count,
    _split_transaction_sets,
)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("EDI_REQUIRE_PARTNER_ID", raising=False)
    monkeypatch.delenv("EDI_PARTNER_ALLOWLIST", raising=False)
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


def test_legacy_856_bare_st_returns_400_not_500(client: TestClient) -> None:
    response = _post(client, b"ISA*~ST~")
    assert response.status_code == 400
    assert response.json()["detail"] == "Only X12 856 is currently supported"


def test_bare_n1_segment_is_tolerated() -> None:
    extracted = _extract_fields_for_set("856", [["N1"]])
    assert extracted["ship_from_name"] is None
    assert extracted["ship_to_name"] is None


def test_empty_payload_returns_400(client: TestClient) -> None:
    assert _post(client, b"").status_code == 400


def test_non_edi_payload_returns_400(client: TestClient) -> None:
    assert _post(client, b" ").status_code == 400


def test_unbalanced_st_se_rejected_on_document_route(client: TestClient) -> None:
    response = _post(client, b"ISA*~ST*856~", route="/document")
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "unbalanced_transaction_sets"


def test_require_partner_id_rejects_missing_header(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EDI_REQUIRE_PARTNER_ID", "true")
    response = _post(client, b"")
    assert response.status_code == 400
    assert "X-Partner-ID" in response.json()["detail"]


def test_require_partner_id_on_value_is_truthy(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDI_REQUIRE_PARTNER_ID", "on")
    response = _post(client, b"")
    assert response.status_code == 400
    assert "X-Partner-ID" in response.json()["detail"]


def test_declared_count_sums_across_functional_groups() -> None:
    # GE headers carry structural counts and no transaction records.
    segments = [["GE", str(len(["ST"]))], ["GE", str(len(["ST"]))]]
    assert _declared_transaction_set_count(segments) == len(segments)


def test_declared_count_skips_unparseable_ge01() -> None:
    assert _declared_transaction_set_count([["GE", ""]]) is None


def test_split_drops_stray_body_segments_between_transaction_sets() -> None:
    segments = [["ISA"], ["ST", "856"], ["SE"], ["N1"], ["ST", "856"], ["SE"]]
    slices = _split_transaction_sets(segments)
    assert len(slices) == 2
    assert all(["N1"] not in transaction for transaction in slices)
    assert all(["ISA"] in transaction for transaction in slices)
