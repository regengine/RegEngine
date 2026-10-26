"""Data-free EPCIS export checks."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
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
    digits = str(uuid4().int).zfill(13)[:13]
    mapping = {
        "event_type": "receiving",
        "epc_class": f"urn:epc:class:lgtin:{digits[:7]}.{digits[7:]}.{uuid4().hex}",
        "traceability_lot_code": None,
        "quantity": None,
        "unit_of_measure": None,
        "event_timestamp": datetime.now(timezone.utc),
        "location_gln": None,
        "sha256_hash": None,
        "epcis_event_type": None,
        "epcis_action": None,
        "epcis_biz_step": None,
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

        assert _query_tenant_events(str(uuid4()), None, None, None) == []

    def test_db_error_raises_instead_of_empty_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # SEL-508: a storage failure must never look like an empty tenant.
        session = _FakeSession(execute_queue=[RuntimeError("db down")])
        monkeypatch.setattr(epcis_export, "get_db_safe", lambda: session)
        with pytest.raises(epcis_export.ExportStorageUnavailable):
            _query_tenant_events(str(uuid4()), None, None, None)
        assert session.closed

    def test_query_is_bounded_by_cap_plus_one_not_5000(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # SEL-506: the old LIMIT 5000 silently dropped the oldest events.
        session = _FakeSession(execute_queue=[[]])
        monkeypatch.setattr(epcis_export, "get_db_safe", lambda: session)
        _query_tenant_events(str(uuid4()), None, None, None)
        sql, params = session.calls[0][1]
        assert "LIMIT 5000" not in sql
        assert params["row_limit"] == epcis_export._MAX_EXPORT_EVENTS + 1


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
            tenant_id=tenant_id or str(uuid4()),
            principal_kind="test",
            principal_id=uuid4().hex,
        )

    app.dependency_overrides[_verify_api_key] = lambda: None
    app.dependency_overrides[require_tenant_context] = _tenant_ctx
    return TestClient(app)


class TestExportEpcisEndpoint:
    def test_returns_empty_events_when_no_tenant_rows(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(epcis_export, "_query_tenant_events", lambda *a, **k: [])
        response = client.post(
            "/api/v1/export/epcis",
            json={"tenant_id": str(uuid4()), "format": "epcis"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["type"] == "EPCISDocument"
        assert body["schemaVersion"] == "2.0"
        assert body["epcisBody"]["eventList"] == []
        metadata = body["regengine:exportMetadata"]
        assert metadata["eventsCount"] == 0
        assert metadata["dataSource"] == "empty"
        assert metadata["integrityVerified"] is False
        assert metadata["chainHashVerified"] is False
        assert metadata["regengine:message"] == "No data yet"
        assert "regengine:disclaimer" not in metadata
        assert response.headers["X-RegEngine-Data-Source"] == "empty"
        assert response.headers["X-RegEngine-Integrity-Verified"] == "false"
        assert response.headers["X-RegEngine-Events-Count"] == "0"
        assert "X-RegEngine-Schema-Valid" not in response.headers

    def test_returns_tenant_events_when_db_has_rows(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        row = dict(_event_row()._mapping)
        monkeypatch.setattr(epcis_export, "_query_tenant_events", lambda *a, **k: [row])
        response = client.post(
            "/api/v1/export/epcis",
            json={"tenant_id": str(uuid4()), "format": "epcis"},
        )
        assert response.status_code == 200
        body = response.json()
        metadata = body["regengine:exportMetadata"]
        assert metadata["dataSource"] == "tenant"
        assert metadata["integrityVerified"] is True
        assert metadata["chainHashVerified"] is True
        assert metadata["eventsCount"] == 1
        assert "regengine:disclaimer" not in metadata
        events = body["epcisBody"]["eventList"]
        assert isinstance(events, list)
        assert len(events) == 1
        event = events[0]
        for key in ("type", "action", "bizStep", "eventTime"):
            assert isinstance(event[key], str) and event[key]
        assert event["quantityList"][0]["epcClass"] == row["epc_class"]
        assert metadata["skippedEventsCount"] == 0
        assert response.headers["X-RegEngine-Data-Source"] == "tenant"
        assert response.headers["X-RegEngine-Integrity-Verified"] == "true"
        assert response.headers["X-RegEngine-Events-Count"] == "1"

    def test_fills_defaults_when_row_fields_are_null(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        row = dict(_event_row(event_timestamp=None)._mapping)
        monkeypatch.setattr(epcis_export, "_query_tenant_events", lambda *a, **k: [row])
        response = client.post(
            "/api/v1/export/epcis",
            json={"tenant_id": str(uuid4())},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["epcisBody"]["eventList"] == []
        assert body["regengine:exportMetadata"]["eventsCount"] == 0
        assert body["regengine:exportMetadata"]["skippedEventsCount"] == 1
        assert body["regengine:exportMetadata"]["regengine:message"] == "No data yet"
        assert response.headers["X-RegEngine-Events-Count"] == "0"

    def test_validate_flag_emits_validation_block_and_header(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(epcis_export, "_query_tenant_events", lambda *a, **k: [])
        response = client.post(
            "/api/v1/export/epcis?validate=true",
            json={"tenant_id": str(uuid4())},
        )
        assert response.status_code == 200
        body = response.json()
        validation = body["regengine:validation"]
        assert validation["valid"] is False
        assert validation["errors"] == ["epcisBody.eventList is empty or missing"]
        assert "checkedAt" in validation
        assert response.headers["X-RegEngine-Schema-Valid"] == "false"


class TestExportFdaEndpoint:
    def test_header_only_when_no_rows(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(epcis_export, "_query_tenant_events", lambda *a, **k: [])
        response = client.post(
            "/api/v1/export/fda",
            json={"tenant_id": str(uuid4())},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert response.headers["X-RegEngine-Data-Source"] == "empty"
        assert response.headers["X-RegEngine-Events-Count"] == "0"
        assert response.headers["X-RegEngine-Message"] == "No data yet"
        assert "X-RegEngine-Disclaimer" not in response.headers
        assert [line for line in response.text.splitlines() if line] == [epcis_export.FDA_CSV_HEADER]


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


def _raise_storage(*_a: Any, **_k: Any) -> list[dict]:
    raise epcis_export.ExportStorageUnavailable("db down")


class TestExportFailsLoudly:
    """SEL-506 / SEL-508: partial or failed reads are never reported as complete."""

    @pytest.mark.parametrize("path", ["/api/v1/export/epcis", "/api/v1/export/fda"])
    def test_storage_error_returns_503_not_no_data_yet(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        session = _FakeSession(execute_queue=[RuntimeError("db down")])
        monkeypatch.setattr(epcis_export, "get_db_safe", lambda: session)
        response = client.post(path, json={"tenant_id": str(uuid4())})
        assert response.status_code == 503
        assert "No data yet" not in response.text
        assert response.headers.get("X-RegEngine-Data-Source") != "empty"

    def test_5001_events_export_5001(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        rows = [_event_row() for _ in range(5001)]
        session = _FakeSession(execute_queue=[rows])
        monkeypatch.setattr(epcis_export, "get_db_safe", lambda: session)
        response = client.post("/api/v1/export/epcis", json={"tenant_id": str(uuid4())})
        assert response.status_code == 200
        assert len(response.json()["epcisBody"]["eventList"]) == 5001
        assert response.headers["X-RegEngine-Events-Count"] == "5001"

    @pytest.mark.parametrize("path", ["/api/v1/export/epcis", "/api/v1/export/fda"])
    def test_over_cap_returns_413_not_truncated(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        monkeypatch.setattr(epcis_export, "_MAX_EXPORT_EVENTS", 3)
        session = _FakeSession(execute_queue=[[_event_row() for _ in range(4)]])
        monkeypatch.setattr(epcis_export, "get_db_safe", lambda: session)
        response = client.post(path, json={"tenant_id": str(uuid4())})
        assert response.status_code == 413
        assert session.calls[0][1][1]["row_limit"] == 4
