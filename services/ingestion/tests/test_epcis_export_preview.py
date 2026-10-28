"""H5 Preview labels for EPCIS export (spec section 6 / section 7 test 10).

Synthetic fixtures only. No partner data. EPCIS stays Preview.
"""

from __future__ import annotations

import json
import sys
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
from app.epcis_export import router as epcis_export_router
from app.webhook_compat import _verify_api_key, require_tenant_context
from shared.tenant_context import TenantContext

FIXTURES = Path(__file__).resolve().parent / "fixtures"
HARVEST_CSV = FIXTURES / "01_harvesting.csv"
PREVIEW_NOTICE = (
    "EPCIS export is in Preview. Validate with your trading partner "
    "before relying on it for compliance."
)
NAMED_RETAILERS = ("Walmart", "Kroger", "Costco", "Target")


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(epcis_export_router)

    async def _tenant_ctx(request: Request) -> TenantContext:
        tenant_id = request.path_params.get("tenant_id")
        if not tenant_id and request.method in {"POST", "PUT", "PATCH"}:
            try:
                body = await request.json()
            except Exception:
                body = {}
            if isinstance(body, dict):
                tenant_id = body.get("tenant_id") or body.get("tenantId")
        return TenantContext(
            tenant_id=tenant_id or str(uuid4()),
            principal_kind="test",
            principal_id=uuid4().hex,
        )

    app.dependency_overrides[_verify_api_key] = lambda: None
    app.dependency_overrides[require_tenant_context] = _tenant_ctx
    return TestClient(app)


def _empty_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epcis_export, "_load_export_rows", lambda *_a, **_k: [])


class TestPreviewHeaderAndMetadata:
    """Spec section 7 test 10: Preview header and metadata on every response."""

    def test_preview_header_on_empty_export(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _empty_rows(monkeypatch)
        response = client.post(
            "/api/v1/export/epcis",
            json={"tenant_id": str(uuid4())},
        )
        assert response.status_code == 200
        assert response.headers.get("X-RegEngine-Preview") == "true"
        meta = response.json()["regengine:exportMetadata"]
        assert meta["preview"] is True
        assert meta["previewNotice"] == PREVIEW_NOTICE
        assert meta["eventsCount"] == 0

    def test_preview_header_on_success(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Synthetic harvest lot string only (fixture path under tests/fixtures).
        assert HARVEST_CSV.is_file()
        lot = HARVEST_CSV.read_text().splitlines()[1].split(",")[0]
        assert lot.startswith("LOT-")

        def _one_row(*_a: object, **_k: object) -> list[dict]:
            return [
                {
                    "event_type": "harvesting",
                    "epc_class": "https://id.gs1.org/01/00614141999996/10/" + lot,
                    "traceability_lot_code": lot,
                    "quantity": 5000,
                    "unit_of_measure": "lbs",
                    "event_timestamp": "2026-03-12T12:00:00+00:00",
                    "location_gln": "0061414100014",
                    "sha256_hash": None,
                    "epcis_event_type": "ObjectEvent",
                    "epcis_action": "ADD",
                    "epcis_biz_step": None,
                }
            ]

        monkeypatch.setattr(epcis_export, "_load_export_rows", _one_row)
        response = client.post(
            "/api/v1/export/epcis",
            json={"tenant_id": str(uuid4())},
        )
        assert response.status_code == 200
        assert response.headers.get("X-RegEngine-Preview") == "true"
        body = response.json()
        meta = body["regengine:exportMetadata"]
        assert meta["preview"] is True
        assert meta["previewNotice"] == PREVIEW_NOTICE
        assert meta["eventsCount"] >= 1
        # preview keys registered in @context
        ctx = body["@context"]
        assert isinstance(ctx, list) and len(ctx) >= 2
        assert ctx[1].get("preview") == "regengine:preview"
        assert ctx[1].get("previewNotice") == "regengine:previewNotice"

    def test_preview_header_on_fda_empty(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _empty_rows(monkeypatch)
        response = client.post(
            "/api/v1/export/fda",
            json={"tenant_id": str(uuid4())},
        )
        assert response.status_code == 200
        assert response.headers.get("X-RegEngine-Preview") == "true"


class TestFormatsPreviewStatus:
    def test_formats_epcis_status_preview(self, client: TestClient) -> None:
        response = client.get("/api/v1/export/formats")
        assert response.status_code == 200
        formats = {f["id"]: f for f in response.json()["formats"]}
        epcis = formats["epcis"]
        assert epcis["status"] == "preview"
        assert "Preview" in epcis["description"]
        assert epcis["retailers"] == []

    def test_formats_has_no_named_retailers(self, client: TestClient) -> None:
        response = client.get("/api/v1/export/formats")
        blob = json.dumps(response.json())
        for name in NAMED_RETAILERS:
            assert name not in blob
