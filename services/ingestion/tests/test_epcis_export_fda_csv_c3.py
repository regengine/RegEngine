"""C3: ingestion FDA CSV aligned with compliance sortable KDE columns.

Synthetic fixtures only. Uses harvest CSV lot strings and asn_856 GLNs.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

_ingestion_dir = Path(__file__).resolve().parent.parent
if str(_ingestion_dir) not in sys.path:
    sys.path.insert(0, str(_ingestion_dir))
_services_dir = _ingestion_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

pytest.importorskip("fastapi")

import app.epcis_export as epcis_export
from app.epcis_export import FDA_CSV_HEADER, router as epcis_export_router
from app.webhook_compat import _verify_api_key, require_tenant_context
from shared.tenant_context import TenantContext

FIXTURES = Path(__file__).resolve().parent / "fixtures"
HARVEST_CSV = FIXTURES / "01_harvesting.csv"
ASN_EXPECTED = FIXTURES / "edi_corpus" / "asn_856.expected.json"

REQUIRED_NEW = (
    "Reference_Document",
    "TLC_Source_Reference",
    "Immediate_Previous_Source",
    "Additional_KDEs_JSON",
)


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(epcis_export_router)

    async def _tenant_ctx(request: Request) -> TenantContext:
        tenant_id = None
        if request.method in {"POST", "PUT", "PATCH"}:
            try:
                body = await request.json()
            except Exception:
                body = {}
            if isinstance(body, dict):
                tenant_id = body.get("tenant_id")
        return TenantContext(
            tenant_id=tenant_id or str(uuid4()),
            principal_kind="test",
            principal_id=uuid4().hex,
        )

    app.dependency_overrides[_verify_api_key] = lambda: None
    app.dependency_overrides[require_tenant_context] = _tenant_ctx
    return TestClient(app)


def test_fda_header_includes_compliance_kde_columns() -> None:
    cols = FDA_CSV_HEADER.split(",")
    for name in REQUIRED_NEW:
        assert name in cols
    # SHA256 still present; new cols sit before it or adjacent
    assert "SHA256_Hash" in cols
    assert cols.index("Reference_Document") < cols.index("SHA256_Hash")


def test_fda_export_row_fills_reference_and_tlc_source(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    with HARVEST_CSV.open(newline="") as fh:
        harvest = next(csv.DictReader(fh))
    asn = json.loads(ASN_EXPECTED.read_text())
    lot = harvest["traceability_lot_code"]

    def _rows(*_a, **_k):
        return [
            {
                "event_type": "shipping",
                "traceability_lot_code": lot,
                "product_description": asn["line_items"][0]["product_description"],
                "quantity": asn["line_items"][0]["quantity"],
                "unit_of_measure": asn["line_items"][0]["unit_of_measure"],
                "event_timestamp": datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
                "location_gln": None,
                "location_name": None,
                "ship_from": asn["ship_from_name"],
                "ship_from_gln": asn["ship_from_gln"],
                "ship_to": asn["ship_to_name"],
                "ship_to_gln": asn["ship_to_gln"],
                "carrier": "CarrierCo",
                "temperature_c": None,
                "reference_document": f"BM:{asn['reference_document_number']}",
                "tlc_source_reference": "https://id.gs1.org/414/6141410000014",
                "immediate_previous_source": "",
                "field_id": harvest.get("field_id"),
                "harvester_name": harvest.get("harvester_name"),
                "sha256_hash": "abc",
            }
        ]

    monkeypatch.setattr(epcis_export, "_load_export_rows", _rows)
    response = client.post("/api/v1/export/fda", json={"tenant_id": str(uuid4())})
    assert response.status_code == 200
    lines = [ln for ln in response.text.splitlines() if ln]
    assert lines[0] == FDA_CSV_HEADER
    reader = csv.DictReader(lines)
    row = next(reader)
    assert row["Traceability_Lot_Code"] == lot
    assert row["Reference_Document"] == "BM:BOL-9001"
    assert "414/6141410000014" in row["TLC_Source_Reference"]
    assert "FIELD-SVF-7" in row["Additional_KDEs_JSON"]
    assert row["Ship_From_GLN"] == "6141410000014"


def test_fda_empty_export_header_only(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(epcis_export, "_load_export_rows", lambda *_a, **_k: [])
    response = client.post("/api/v1/export/fda", json={"tenant_id": str(uuid4())})
    assert response.status_code == 200
    assert [ln for ln in response.text.splitlines() if ln] == [FDA_CSV_HEADER]
