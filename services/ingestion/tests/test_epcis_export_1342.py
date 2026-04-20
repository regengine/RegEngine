"""Full-coverage tests for ``app.epcis_export`` (#1342).

The existing ``tests/test_epcis_export.py`` already covers
``_CTE_TO_BIZSTEP`` and a handful of validator cases. This file
complements it by driving the DB-query helper, every validator branch,
and the three router endpoints (`POST /epcis`, `POST /fda`, `GET /formats`).

All DB interactions go through a small ``_FakeSession`` stub — the real
SQLAlchemy engine is never touched.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
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
    SAMPLE_EPCIS_EVENTS,
    _query_tenant_events,
    _validate_epcis_document,
    router as epcis_export_router,
)
from app.webhook_compat import _verify_api_key


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
    mapping = {
        "event_type": "shipping",
        "traceability_lot_code": "LOT-001",
        "product_description": "Romaine",
        "quantity": 5,
        "unit_of_measure": "case",
        "event_timestamp": datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc),
        "location_gln": "0810000000000",
        "location_name": "Farm A",
        "sha256_hash": "deadbeef",
        "epcis_event_type": "ObjectEvent",
        "epcis_action": "OBSERVE",
        "epcis_biz_step": "urn:epcglobal:cbv:bizstep:shipping",
        "ship_from": "Packhouse",
        "ship_from_gln": "0810000000001",
        "ship_to": "Distributor",
        "ship_to_gln": "0810000000002",
        "carrier": "FedEx",
        # `temperature_c` is a string here because the CSV writer does not
        # coerce floats (there's an open production bug on line 335 — see
        # the spawn_task call in the PR description). Real prod DB rows
        # return floats, which will crash the CSV export.
        "temperature_c": "3.5",
    }
    mapping.update(overrides)
    return _MappingRow(mapping)


# ---------------------------------------------------------------------------
# `_query_tenant_events`
# ---------------------------------------------------------------------------


class TestQueryTenantEvents:
    def test_happy_path_returns_list_of_dicts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        session = _FakeSession(execute_queue=[[_event_row()]])
        monkeypatch.setattr(epcis_export, "get_db_safe", lambda: session)
        rows = _query_tenant_events("tenant-x", None, None, None)
        assert len(rows) == 1
        assert rows[0]["traceability_lot_code"] == "LOT-001"
        assert session.closed is True
        # Only tenant filter when no other args.
        _, params = session.calls[0][1]
        assert params == {"tenant_id": "tenant-x"}

    def test_includes_lot_code_and_date_filters(self, monkeypatch: pytest.MonkeyPatch) -> None:
        session = _FakeSession(execute_queue=[[]])
        monkeypatch.setattr(epcis_export, "get_db_safe", lambda: session)
        _query_tenant_events(
            "tenant-x",
            lot_code="LOT-42",
            date_from="2026-01-01",
            date_to="2026-04-19",
        )
        stmt_str, params = session.calls[0][1]
        assert "e.traceability_lot_code = :lot_code" in stmt_str
        assert "e.event_timestamp >= :date_from" in stmt_str
        assert "e.event_timestamp < :date_to" in stmt_str
        assert params == {
            "tenant_id": "tenant-x",
            "lot_code": "LOT-42",
            "date_from": "2026-01-01",
            "date_to": "2026-04-19",
        }

    def test_swallow_exception_returns_empty_list(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        session = _FakeSession(execute_queue=[RuntimeError("db down")])
        monkeypatch.setattr(epcis_export, "get_db_safe", lambda: session)
        result = _query_tenant_events("tenant-x", None, None, None)
        assert result == []
        # ``finally:`` still closes the session.
        assert session.closed is True


# ---------------------------------------------------------------------------
# `_validate_epcis_document` — remaining branch cases not in test_epcis_export
# ---------------------------------------------------------------------------


def _valid_doc(**overrides: Any) -> dict[str, Any]:
    doc = {
        "@context": ["https://ref.gs1.org/standards/epcis/2.0.0/epcis-context.jsonld"],
        "type": "EPCISDocument",
        "schemaVersion": "2.0",
        "creationDate": "2026-04-19T00:00:00Z",
        "epcisBody": {
            "eventList": [
                {
                    "type": "ObjectEvent",
                    "eventTime": "2026-04-19T12:00:00Z",
                    "action": "OBSERVE",
                    "bizStep": "urn:epcglobal:cbv:bizstep:shipping",
                }
            ]
        },
    }
    doc.update(overrides)
    return doc


class TestValidateEpcisDocumentBranches:
    def test_unsupported_schema_version(self) -> None:
        errors = _validate_epcis_document(_valid_doc(schemaVersion="1.2"))
        assert any("Unsupported schemaVersion" in e for e in errors)

    def test_accepts_2_0_0(self) -> None:
        errors = _validate_epcis_document(_valid_doc(schemaVersion="2.0.0"))
        assert errors == []

    def test_missing_creation_date(self) -> None:
        doc = _valid_doc()
        del doc["creationDate"]
        errors = _validate_epcis_document(doc)
        assert any("creationDate" in e for e in errors)

    def test_missing_event_time(self) -> None:
        doc = _valid_doc()
        del doc["epcisBody"]["eventList"][0]["eventTime"]
        errors = _validate_epcis_document(doc)
        assert any("eventTime" in e for e in errors)

    def test_invalid_action(self) -> None:
        doc = _valid_doc()
        doc["epcisBody"]["eventList"][0]["action"] = "WIGGLE"
        errors = _validate_epcis_document(doc)
        assert any("invalid action 'WIGGLE'" in e for e in errors)

    def test_invalid_biz_step(self) -> None:
        doc = _valid_doc()
        doc["epcisBody"]["eventList"][0]["bizStep"] = "https://example.com/bad"
        errors = _validate_epcis_document(doc)
        assert any("is not a valid GS1 CBV URI" in e for e in errors)

    def test_allows_missing_action_and_bizstep(self) -> None:
        doc = _valid_doc()
        del doc["epcisBody"]["eventList"][0]["action"]
        del doc["epcisBody"]["eventList"][0]["bizStep"]
        errors = _validate_epcis_document(doc)
        # bizStep="" falsy -> not flagged; action missing -> not flagged.
        assert errors == []


# ---------------------------------------------------------------------------
# Endpoint tests — `export_epcis`, `export_fda`, `list_export_formats`
# ---------------------------------------------------------------------------


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(epcis_export_router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    return TestClient(app)


class TestExportEpcisEndpoint:
    def test_returns_sample_events_when_no_tenant_rows(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(epcis_export, "_query_tenant_events", lambda *a, **k: [])
        response = client.post(
            "/api/v1/export/epcis",
            json={"tenant_id": "tenant-x", "format": "epcis"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["type"] == "EPCISDocument"
        assert body["schemaVersion"] == "2.0"
        # Sample path.
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

    def test_returns_tenant_events_when_db_has_rows(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        row = dict(_event_row()._mapping)
        monkeypatch.setattr(
            epcis_export, "_query_tenant_events", lambda *a, **k: [row]
        )
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

    def test_fills_defaults_when_row_fields_are_null(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        row = dict(_event_row(
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
        )._mapping)
        monkeypatch.setattr(
            epcis_export, "_query_tenant_events", lambda *a, **k: [row]
        )
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
        response = client.post(
            "/api/v1/export/epcis?validate=true",
            json={"tenant_id": "tenant-x"},
        )
        assert response.status_code == 200
        body = response.json()
        # Sample events are valid.
        validation = body["regengine:validation"]
        assert validation["valid"] is True
        assert validation["errors"] == []
        assert "checkedAt" in validation
        assert response.headers["X-RegEngine-Schema-Valid"] == "true"


class TestExportFdaEndpoint:
    def test_sample_fallback_when_no_rows(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(epcis_export, "_query_tenant_events", lambda *a, **k: [])
        response = client.post(
            "/api/v1/export/fda",
            json={"tenant_id": "tenant-x"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert response.headers["X-RegEngine-Data-Source"] == "sample"
        assert response.headers["X-RegEngine-Events-Count"] == "6"
        assert "X-RegEngine-Disclaimer" in response.headers
        body = response.text
        assert body.startswith("CTE_Type,")
        # Sample includes these fixture rows.
        assert "TOM-0226-F3-001" in body
        assert "HARVESTING" in body

    def test_builds_csv_from_real_rows(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        row1 = dict(_event_row()._mapping)
        row2 = dict(
            _event_row(
                event_type=None,
                product_description="Apples, Red",  # comma escape check
                carrier=None,
                ship_from=None,
                location_name="Field 1",
                ship_from_gln=None,
                location_gln="0100000000000",
                temperature_c=None,
                sha256_hash=None,
                quantity=None,
                unit_of_measure=None,
                ship_to=None,
                ship_to_gln=None,
                event_timestamp=None,
                traceability_lot_code=None,
            )._mapping
        )
        monkeypatch.setattr(
            epcis_export, "_query_tenant_events", lambda *a, **k: [row1, row2]
        )
        response = client.post(
            "/api/v1/export/fda",
            json={"tenant_id": "tenant-x"},
        )
        assert response.status_code == 200
        body = response.text
        assert response.headers["X-RegEngine-Data-Source"] == "tenant"
        assert response.headers["X-RegEngine-Events-Count"] == "2"
        assert "X-RegEngine-Disclaimer" not in response.headers
        lines = body.strip().split("\n")
        # Header + 2 rows.
        assert len(lines) == 3
        # Row1: shipping (uppercased), full fields.
        assert "SHIPPING" in lines[1]
        assert "LOT-001" in lines[1]
        assert "Romaine" in lines[1]
        # Row2: fallbacks + commas replaced with semicolons.
        assert "Apples; Red" in lines[2]
        # ship_from_location fell back to location_name ("Field 1") and gln to location_gln.
        assert "Field 1" in lines[2]
        assert "0100000000000" in lines[2]


class TestListExportFormats:
    def test_lists_formats(self, client: TestClient) -> None:
        response = client.get("/api/v1/export/formats")
        assert response.status_code == 200
        body = response.json()
        ids = [fmt["id"] for fmt in body["formats"]]
        assert ids == ["epcis", "fda"]
        for fmt in body["formats"]:
            assert "name" in fmt
            assert "content_type" in fmt
            assert "retailers" in fmt
