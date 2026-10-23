"""Data-free export checks outside the two protected row-based tests."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
from app.epcis_export import (
    _query_tenant_events,
    router as epcis_export_router,
)
from app.webhook_compat import _verify_api_key, require_tenant_context
from shared.tenant_context import TenantContext

# ---------------------------------------------------------------------------
# Fake SQLAlchemy helpers
# ---------------------------------------------------------------------------


class _MappingRow:
    """Mimics a SQLAlchemy row with ``._mapping`` dict conversion."""

    def __init__(self, mapping: dict[str, Any]) -> None:
        self._mapping = mapping


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def fetchall(self) -> list[Any]:
        return list(self._rows)


class _FakeSession:
    def __init__(self, execute_queue: list[Any] | None = None) -> None:
        self.execute_queue = list(execute_queue or [])
        self.calls: list[tuple[str, Any]] = []
        self.closed = False

    def execute(self, stmt: Any, params: Any | None = None) -> _FakeResult:
        self.calls.append(("execute", (str(stmt), params)))
        if not self.execute_queue:
            return _FakeResult([])
        nxt = self.execute_queue.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        if nxt is None:
            return _FakeResult([])
        if isinstance(nxt, list):
            return _FakeResult(nxt)
        return _FakeResult([nxt])

    def close(self) -> None:
        self.calls.append(("close", None))
        self.closed = True


def _event_row(**overrides: Any) -> _MappingRow:
    # The two protected endpoint tests still require this timestamp and hash.
    mapping = {
        "event_type": "",
        "traceability_lot_code": "",
        "product_description": "",
        "quantity": None,
        "unit_of_measure": "",
        "event_timestamp": datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc),
        "location_gln": "",
        "location_name": "",
        "sha256_hash": "deadbeef",
        "epcis_event_type": "ObjectEvent",
        "epcis_action": "OBSERVE",
        "epcis_biz_step": "urn:epcglobal:cbv:bizstep:shipping",
        "ship_from": "",
        "ship_from_gln": "",
        "ship_to": "",
        "ship_to_gln": "",
        "carrier": "",
        "temperature_c": None,
    }
    mapping.update(overrides)
    return _MappingRow(mapping)


# ---------------------------------------------------------------------------
# `_query_tenant_events`
# ---------------------------------------------------------------------------


class TestQueryTenantEvents:
    def test_no_rows_returns_empty_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        session = _FakeSession(execute_queue=[[]])
        monkeypatch.setattr(epcis_export, "get_db_safe", lambda: session)

        assert _query_tenant_events("t", None, None, None) == []

    def test_swallow_exception_returns_empty_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        session = _FakeSession(execute_queue=[RuntimeError("db down")])
        monkeypatch.setattr(epcis_export, "get_db_safe", lambda: session)
        result = _query_tenant_events("t", None, None, None)
        assert result == []


# ---------------------------------------------------------------------------
# Endpoint tests — `export_epcis`, `export_fda`, `list_export_formats`
# ---------------------------------------------------------------------------


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
            tenant_id=tenant_id or "t",
            principal_kind="test",
            principal_id="t",
        )

    app.dependency_overrides[_verify_api_key] = lambda: None
    app.dependency_overrides[require_tenant_context] = _tenant_ctx
    return TestClient(app)


class TestExportEpcisEndpoint:
    def test_returns_empty_event_list_when_no_tenant_rows(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        SAMPLE_EPCIS_EVENTS = []
        monkeypatch.setattr(epcis_export, "SAMPLE_EPCIS_EVENTS", SAMPLE_EPCIS_EVENTS)
        monkeypatch.setattr(epcis_export, "_query_tenant_events", lambda *a, **k: [])
        response = client.post(
            "/api/v1/export/epcis",
            json={"tenant_id": "t", "format": "epcis"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["type"] == "EPCISDocument"
        assert body["schemaVersion"] == "2.0"
        assert body["epcisBody"]["eventList"] == SAMPLE_EPCIS_EVENTS
        metadata = body["regengine:exportMetadata"]
        assert metadata["dataSource"] == "sample"
        assert metadata["integrityVerified"] is False
        assert metadata["chainHashVerified"] is False
        assert "regengine:disclaimer" in metadata
        assert response.headers["X-RegEngine-Data-Source"] == "sample"
        assert response.headers["X-RegEngine-Integrity-Verified"] == "false"
        assert response.headers["X-RegEngine-Events-Count"] == str(len(SAMPLE_EPCIS_EVENTS))
        assert "X-RegEngine-Schema-Valid" not in response.headers

    def test_returns_tenant_events_when_db_has_rows(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        row = dict(_event_row()._mapping)
        monkeypatch.setattr(epcis_export, "_query_tenant_events", lambda *a, **k: [row])
        response = client.post(
            "/api/v1/export/epcis",
            json={"tenant_id": "tenant-x", "format": "epcis"},
        )
        assert response.status_code == 200
        body = response.json()
        metadata = body["regengine:exportMetadata"]
        assert metadata["dataSource"] == "tenant"
        assert metadata["integrityVerified"] is True
        assert metadata["chainHashVerified"] is True
        assert "regengine:disclaimer" not in metadata
        event = body["epcisBody"]["eventList"][0]
        assert event["type"] == "ObjectEvent"
        assert event["action"] == "OBSERVE"
        assert event["bizStep"] == "urn:epcglobal:cbv:bizstep:shipping"
        assert event["regengine:sha256"] == "deadbeef"
        # eventTime came from the real timestamp.
        assert event["eventTime"].startswith("2026-04-19T12:00:00")
        assert response.headers["X-RegEngine-Data-Source"] == "tenant"
        assert response.headers["X-RegEngine-Integrity-Verified"] == "true"

    def test_fills_defaults_when_row_fields_are_null(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        row = dict(
            _event_row(
                event_type=None,
                epcis_event_type=None,
                epcis_action=None,
                epcis_biz_step=None,
                event_timestamp=None,
                location_gln=None,
                traceability_lot_code=None,
                quantity=None,
                unit_of_measure=None,
                sha256_hash=None,
            )._mapping
        )
        monkeypatch.setattr(epcis_export, "_query_tenant_events", lambda *a, **k: [row])
        response = client.post(
            "/api/v1/export/epcis",
            json={"tenant_id": "tenant-x"},
        )
        assert response.status_code == 200
        event = response.json()["epcisBody"]["eventList"][0]
        # Fallbacks all fired.
        assert event["type"] == "ObjectEvent"
        assert event["action"] == "OBSERVE"
        # event_type is None -> empty-string key lookup -> default bizstep.
        assert event["bizStep"] == "urn:epcglobal:cbv:bizstep:observing"
        assert event["readPoint"]["id"].endswith("0000000000000.0")
        extension = event["extension"]["quantityList"][0]
        assert extension["epcClass"].endswith("UNKNOWN")
        assert extension["quantity"] == 0
        assert extension["uom"] == "EA"
        assert event["regengine:sha256"] == ""

    def test_validate_flag_emits_validation_block_and_header(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(epcis_export, "_query_tenant_events", lambda *a, **k: [])
        monkeypatch.setattr(epcis_export, "SAMPLE_EPCIS_EVENTS", [])
        response = client.post(
            "/api/v1/export/epcis?validate=true",
            json={"tenant_id": "t"},
        )
        assert response.status_code == 200
        body = response.json()
        validation = body["regengine:validation"]
        assert validation["valid"] is False
        assert any("eventList" in error for error in validation["errors"])
        assert "checkedAt" in validation
        assert response.headers["X-RegEngine-Schema-Valid"] == "false"

    def test_missing_tenant_id_is_rejected(self, client: TestClient) -> None:
        response = client.post("/api/v1/export/epcis", json={})

        assert response.status_code == 422


class TestExportFdaEndpoint:
    def test_missing_tenant_id_is_rejected(self, client: TestClient) -> None:
        response = client.post("/api/v1/export/fda", json={})

        assert response.status_code == 422


class TestListExportFormats:
    def test_lists_formats(self, client: TestClient) -> None:
        response = client.get("/api/v1/export/formats")
        assert response.status_code == 200
        body = response.json()
        assert "formats" in body
        assert isinstance(body["formats"], list)
        for fmt in body["formats"]:
            assert "id" in fmt
            assert "name" in fmt
            assert "content_type" in fmt
            assert "retailers" in fmt
