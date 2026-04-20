"""Focused coverage for ``app/epcis/router.py`` — #1342.

Companion to the existing ``test_epcis_ingestion_api.py`` which covers
the happy paths of each endpoint.  This file targets the error &
edge-case branches that bring ``app/epcis/router.py`` to 100%:

- 78: ``_resolve_authenticated_tenant`` → HTTP 400 when resolution fails.
- 122-125: batch ingest rejects invalid ``mode=`` query parameter.
- 131-146: atomic-mode batch happy path (response shape + 201).
- 173-175: partial-mode batch — mixed success/failure → 207, all-failure → 400.
- 193: GET event DB error with production-safe fallback disabled → 503.
- 204: GET event → 404 when neither DB nor fallback finds the id.
- 225: Export DB error with fallback disabled → 503.
- 248, 250: Export fallback honors ``start_date`` / ``end_date`` filters
  (start: event before start is dropped; end: event at/after end is dropped).
- 334-339: XML atomic-mode happy path response shape.
- 359-361: XML partial-mode per-event success aggregation.
- 377, 380: XML partial-mode — mixed → 207, all-success → 201.

Issue: #1342
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Optional

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

# NB: ``from app.epcis import router as router_mod`` would resolve to the
# APIRouter instance re-exported in ``app/epcis/__init__.py``. We want the
# module itself, so import the submodule explicitly via importlib.
import importlib  # noqa: E402

router_mod = importlib.import_module("app.epcis.router")
from app.webhook_compat import _verify_api_key  # noqa: E402


TEST_TENANT_ID = "11111111-2222-3333-4444-555555555555"


# ── Harness ────────────────────────────────────────────────────────────────


@pytest.fixture
def app() -> FastAPI:
    """Mount the EPCIS router with api-key auth bypassed."""
    app = FastAPI()
    app.include_router(router_mod.router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def stub_resolve_tenant(monkeypatch: pytest.MonkeyPatch) -> Callable[..., str | None]:
    """Replace ``_resolve_tenant_id`` with a user-controlled stub.

    Returning ``None`` forces the 'tenant context required' 400 branch.
    """
    holder: dict[str, Any] = {"return": TEST_TENANT_ID}

    def _fake_resolve(
        _explicit: Optional[str],
        x_tenant_id: Optional[str],
        x_regengine_api_key: Optional[str],
    ) -> Optional[str]:
        return holder["return"]

    monkeypatch.setattr(router_mod, "_resolve_tenant_id", _fake_resolve)
    return holder


# ── _resolve_authenticated_tenant: missing tenant ──────────────────────────


class TestResolveAuthenticatedTenantFailure:
    def test_no_resolvable_tenant_returns_400(
        self, client: TestClient, stub_resolve_tenant: dict[str, Any]
    ) -> None:
        """Line 78: ``_resolve_tenant_id`` returns None → 400 with
        ``'Tenant context required'`` detail."""
        stub_resolve_tenant["return"] = None
        resp = client.post("/api/v1/epcis/events", json={"type": "ObjectEvent"})
        assert resp.status_code == 400
        assert "Tenant context required" in resp.json()["detail"]


# ── Batch: bad mode + atomic happy path + partial variations ──────────────


class TestBatchIngest:
    @pytest.fixture(autouse=True)
    def _stub_tenant(self, stub_resolve_tenant: dict[str, Any]) -> None:
        stub_resolve_tenant["return"] = TEST_TENANT_ID

    def test_invalid_mode_returns_400(self, client: TestClient) -> None:
        """Line 122-125: mode != 'atomic'/'partial' → 400."""
        resp = client.post(
            "/api/v1/epcis/events/batch?mode=weird",
            json={"events": [{"type": "ObjectEvent"}]},
        )
        assert resp.status_code == 400
        assert "Invalid mode" in resp.json()["detail"]

    def test_empty_events_list_returns_400(self, client: TestClient) -> None:
        """Line 119: empty events → 400."""
        resp = client.post(
            "/api/v1/epcis/events/batch",
            json={"events": []},
        )
        assert resp.status_code == 400
        assert "at least one event" in resp.json()["detail"]

    def test_atomic_mode_success_shape(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 131-146: atomic happy path returns 201 with the full
        response shape (total, created, failed, results, errors, mode)."""
        def _fake_atomic(
            tenant_id: str, events: list[dict]
        ) -> list[tuple[dict, int]]:
            assert tenant_id == TEST_TENANT_ID
            return [
                ({"cte_id": "evt1", "validation_status": "valid"}, 201),
                ({"cte_id": "evt2", "validation_status": "valid"}, 201),
            ]

        monkeypatch.setattr(
            router_mod, "_ingest_batch_events_db_atomic", _fake_atomic
        )

        resp = client.post(
            "/api/v1/epcis/events/batch?mode=atomic",
            json={"events": [{"type": "ObjectEvent"}, {"type": "ObjectEvent"}]},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["total"] == 2
        assert body["created"] == 2
        assert body["failed"] == 0
        assert body["mode"] == "atomic"
        assert body["errors"] == []
        assert len(body["results"]) == 2
        assert body["results"][0]["status_code"] == 201

    def test_partial_mode_mixed_returns_207(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Line 172: partial mode with BOTH successes and failures → 207."""
        call = {"i": 0}

        def _fake_single(
            tenant_id: str, event: dict
        ) -> tuple[dict, int]:
            call["i"] += 1
            if call["i"] == 1:
                return ({"cte_id": "ok1", "validation_status": "valid"}, 201)
            raise HTTPException(status_code=422, detail="bad event")

        monkeypatch.setattr(router_mod, "_ingest_single_event", _fake_single)

        resp = client.post(
            "/api/v1/epcis/events/batch?mode=partial",
            json={"events": [{"type": "ObjectEvent"}, {"type": "ObjectEvent"}]},
        )
        assert resp.status_code == 207
        body = resp.json()
        assert body["mode"] == "partial"
        assert body["created"] == 1
        assert body["failed"] == 1
        assert body["errors"] == [{"index": 1, "detail": "bad event"}]

    def test_partial_mode_all_failures_returns_400(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 173-174: partial mode with ONLY failures → 400."""
        def _always_fail(
            tenant_id: str, event: dict
        ) -> tuple[dict, int]:
            raise HTTPException(status_code=422, detail="nope")

        monkeypatch.setattr(router_mod, "_ingest_single_event", _always_fail)

        resp = client.post(
            "/api/v1/epcis/events/batch?mode=partial",
            json={"events": [{"type": "ObjectEvent"}]},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["created"] == 0
        assert body["failed"] == 1

    def test_partial_mode_all_success_returns_201(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Line 175: partial mode with ONLY successes → 201."""
        monkeypatch.setattr(
            router_mod,
            "_ingest_single_event",
            lambda t, e: ({"cte_id": "o", "validation_status": "valid"}, 201),
        )

        resp = client.post(
            "/api/v1/epcis/events/batch?mode=partial",
            json={"events": [{"type": "ObjectEvent"}]},
        )
        assert resp.status_code == 201


# ── GET event: DB failure + 404 ────────────────────────────────────────────


class TestGetEpcisEvent:
    @pytest.fixture(autouse=True)
    def _stub_tenant(self, stub_resolve_tenant: dict[str, Any]) -> None:
        stub_resolve_tenant["return"] = TEST_TENANT_ID

    def test_db_error_without_fallback_returns_503(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Line 193: DB error + fallback disabled → 503."""
        def _boom(tenant_id: str, event_id: str) -> Optional[dict]:
            raise RuntimeError("pg down")

        monkeypatch.setattr(router_mod, "_fetch_event_from_db", _boom)
        monkeypatch.setattr(
            router_mod, "_allow_in_memory_fallback", lambda: False
        )

        resp = client.get("/api/v1/epcis/events/some-id")
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Database unavailable"

    def test_not_found_when_db_and_fallback_miss_returns_404(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Line 204: DB returned None AND fallback has nothing → 404."""
        monkeypatch.setattr(
            router_mod, "_fetch_event_from_db", lambda t, eid: None
        )
        monkeypatch.setattr(
            router_mod, "_allow_in_memory_fallback", lambda: True
        )
        monkeypatch.setattr(
            router_mod, "_fallback_store_for", lambda t: {}
        )

        resp = client.get("/api/v1/epcis/events/missing")
        assert resp.status_code == 404
        assert "missing" in resp.json()["detail"]

    def test_fallback_hit_logs_warning(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Lines 191-196: DB exception with fallback enabled logs the
        warning and proceeds to the fallback lookup."""
        def _boom(tenant_id: str, event_id: str) -> Optional[dict]:
            raise RuntimeError("pg flaked")

        monkeypatch.setattr(router_mod, "_fetch_event_from_db", _boom)
        monkeypatch.setattr(
            router_mod, "_allow_in_memory_fallback", lambda: True
        )
        monkeypatch.setattr(
            router_mod,
            "_fallback_store_for",
            lambda t: {"found-id": {"cte_id": "found-id", "status": "ok"}},
        )

        with caplog.at_level("WARNING"):
            resp = client.get("/api/v1/epcis/events/found-id")
        assert resp.status_code == 200
        assert resp.json()["cte_id"] == "found-id"
        assert any(
            "epcis_get_db_failed_using_fallback" in m for m in caplog.messages
        )


# ── Export: DB failure + filter branches ──────────────────────────────────


class TestExportEpcis:
    @pytest.fixture(autouse=True)
    def _stub_tenant(self, stub_resolve_tenant: dict[str, Any]) -> None:
        stub_resolve_tenant["return"] = TEST_TENANT_ID

    def test_db_error_without_fallback_returns_503(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Line 225: DB error + fallback disabled → 503."""
        def _boom(*_: Any, **__: Any) -> list[dict]:
            raise RuntimeError("pg offline")

        monkeypatch.setattr(router_mod, "_list_events_from_db", _boom)
        monkeypatch.setattr(
            router_mod, "_allow_in_memory_fallback", lambda: False
        )

        resp = client.get("/api/v1/epcis/export")
        assert resp.status_code == 503

    def test_fallback_start_date_filters_out_earlier_events(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Line 248: event_time < start_date → excluded from fallback export."""
        monkeypatch.setattr(
            router_mod, "_list_events_from_db", lambda *a, **kw: []
        )
        monkeypatch.setattr(
            router_mod, "_allow_in_memory_fallback", lambda: True
        )

        fake_store = {
            "early": {
                "normalized_cte": {
                    "event_time": "2020-01-01T00:00:00+00:00",
                    "product_id": "p1",
                },
                "epcis_document": {"type": "ObjectEvent", "id": "early"},
            },
            "late": {
                "normalized_cte": {
                    "event_time": "2026-06-01T00:00:00+00:00",
                    "product_id": "p1",
                },
                "epcis_document": {"type": "ObjectEvent", "id": "late"},
            },
        }
        monkeypatch.setattr(
            router_mod, "_fallback_store_for", lambda t: fake_store
        )

        resp = client.get(
            "/api/v1/epcis/export?start_date=2025-01-01T00:00:00Z"
        )
        assert resp.status_code == 200
        events = resp.json()["epcisBody"]["eventList"]
        assert len(events) == 1
        assert events[0]["id"] == "late"

    def test_fallback_end_date_filters_out_later_events(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Line 250: event_time >= end_date → excluded from fallback export."""
        monkeypatch.setattr(
            router_mod, "_list_events_from_db", lambda *a, **kw: []
        )
        monkeypatch.setattr(
            router_mod, "_allow_in_memory_fallback", lambda: True
        )

        fake_store = {
            "early": {
                "normalized_cte": {
                    "event_time": "2020-01-01T00:00:00+00:00",
                    "product_id": "p1",
                },
                "epcis_document": {"type": "ObjectEvent", "id": "early"},
            },
            "late": {
                "normalized_cte": {
                    "event_time": "2030-06-01T00:00:00+00:00",
                    "product_id": "p1",
                },
                "epcis_document": {"type": "ObjectEvent", "id": "late"},
            },
        }
        monkeypatch.setattr(
            router_mod, "_fallback_store_for", lambda t: fake_store
        )

        resp = client.get(
            "/api/v1/epcis/export?end_date=2025-01-01T00:00:00Z"
        )
        assert resp.status_code == 200
        events = resp.json()["epcisBody"]["eventList"]
        assert len(events) == 1
        assert events[0]["id"] == "early"


# ── XML ingest: atomic + partial ───────────────────────────────────────────


_MINIMAL_EPCIS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<epcis:EPCISDocument
    xmlns:epcis="urn:epcglobal:epcis:xsd:2"
    schemaVersion="2.0"
    creationDate="2026-03-01T00:00:00Z">
  <EPCISBody>
    <EventList>
      <ObjectEvent>
        <eventTime>2026-02-28T09:30:00-05:00</eventTime>
        <eventTimeZoneOffset>-05:00</eventTimeZoneOffset>
        <epcList><epc>urn:epc:id:sgtin:0614141.107346.2017</epc></epcList>
        <action>OBSERVE</action>
        <bizStep>urn:epcglobal:cbv:bizstep:receiving</bizStep>
        <disposition>urn:epcglobal:cbv:disp:in_progress</disposition>
        <ilmd>
          <fsma:traceabilityLotCode xmlns:fsma="urn:fsma:food:traceability">00012345678901-MIN</fsma:traceabilityLotCode>
          <cbvmda:lotNumber xmlns:cbvmda="urn:epcglobal:cbv:mda">MIN-001</cbvmda:lotNumber>
        </ilmd>
      </ObjectEvent>
    </EventList>
  </EPCISBody>
</epcis:EPCISDocument>"""


class TestIngestEpcisXml:
    @pytest.fixture(autouse=True)
    def _stub_tenant(self, stub_resolve_tenant: dict[str, Any]) -> None:
        stub_resolve_tenant["return"] = TEST_TENANT_ID

    def test_invalid_mode_returns_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/epcis/events/xml?mode=weird",
            content=_MINIMAL_EPCIS_XML,
            headers={"Content-Type": "application/xml"},
        )
        assert resp.status_code == 400
        assert "Invalid mode" in resp.json()["detail"]

    def test_atomic_happy_path_response_shape(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 334-339: atomic XML ingest returns 201 with the
        EPCIS-XML response shape."""
        monkeypatch.setattr(
            router_mod,
            "_ingest_batch_events_db_atomic",
            lambda t, e: [({"cte_id": "xml1"}, 201)],
        )

        resp = client.post(
            "/api/v1/epcis/events/xml?mode=atomic",
            content=_MINIMAL_EPCIS_XML,
            headers={"Content-Type": "application/xml"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["total"] == 1
        assert body["created"] == 1
        assert body["failed"] == 0
        assert body["format"] == "EPCIS_XML_2.0"
        assert body["mode"] == "atomic"

    def test_partial_mixed_returns_207(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Line 377: partial XML mode with both successes and failures → 207."""
        # Force parser to return two events so we can get mixed results.
        monkeypatch.setattr(
            router_mod,
            "_parse_epcis_xml",
            lambda raw: [{"type": "ObjectEvent"}, {"type": "ObjectEvent"}],
        )

        call = {"i": 0}

        def _flip(t: str, e: dict) -> tuple[dict, int]:
            call["i"] += 1
            if call["i"] == 1:
                return ({"cte_id": "xml-ok"}, 201)
            raise HTTPException(status_code=422, detail="bad xml event")

        monkeypatch.setattr(router_mod, "_ingest_single_event", _flip)

        resp = client.post(
            "/api/v1/epcis/events/xml?mode=partial",
            content=_MINIMAL_EPCIS_XML,
            headers={"Content-Type": "application/xml"},
        )
        assert resp.status_code == 207
        body = resp.json()
        assert body["mode"] == "partial"
        assert body["format"] == "EPCIS_XML_2.0"
        assert body["created"] == 1
        assert body["failed"] == 1

    def test_partial_all_success_returns_201(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 359-361 + 380: partial XML mode with all-success → 201."""
        monkeypatch.setattr(
            router_mod,
            "_parse_epcis_xml",
            lambda raw: [{"type": "ObjectEvent"}],
        )
        monkeypatch.setattr(
            router_mod,
            "_ingest_single_event",
            lambda t, e: ({"cte_id": "x-ok"}, 201),
        )

        resp = client.post(
            "/api/v1/epcis/events/xml?mode=partial",
            content=_MINIMAL_EPCIS_XML,
            headers={"Content-Type": "application/xml"},
        )
        assert resp.status_code == 201

    def test_partial_all_fail_returns_400(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Line 379 (partial-xml all-failure branch): only HTTPException
        raises reach 'failed' — we still want the 400 arm, confirmed via
        the response status_code."""
        monkeypatch.setattr(
            router_mod,
            "_parse_epcis_xml",
            lambda raw: [{"type": "ObjectEvent"}],
        )

        def _always_fail(t: str, e: dict) -> tuple[dict, int]:
            raise HTTPException(status_code=422, detail="bad")

        monkeypatch.setattr(router_mod, "_ingest_single_event", _always_fail)

        resp = client.post(
            "/api/v1/epcis/events/xml?mode=partial",
            content=_MINIMAL_EPCIS_XML,
            headers={"Content-Type": "application/xml"},
        )
        assert resp.status_code == 400

    def test_empty_body_returns_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/epcis/events/xml",
            content=b"",
            headers={"Content-Type": "application/xml"},
        )
        assert resp.status_code == 400
        assert "Empty XML payload" in resp.json()["detail"]

    def test_non_xml_body_returns_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/epcis/events/xml",
            content=b"not xml at all",
            headers={"Content-Type": "application/xml"},
        )
        assert resp.status_code == 400
        assert "does not appear to be XML" in resp.json()["detail"]

    def test_xml_with_no_events_returns_422(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(router_mod, "_parse_epcis_xml", lambda raw: [])
        resp = client.post(
            "/api/v1/epcis/events/xml",
            content=_MINIMAL_EPCIS_XML,
            headers={"Content-Type": "application/xml"},
        )
        assert resp.status_code == 422
        assert "No EPCIS events found" in resp.json()["detail"]


# ── Tenant query-param guard + /validate happy path for completeness ──────


class TestTenantQueryParamGuard:
    def test_tenant_id_query_param_rejected_with_403(
        self, client: TestClient, stub_resolve_tenant: dict[str, Any]
    ) -> None:
        """Line 53-60: supplying ``?tenant_id=`` is rejected with 403."""
        stub_resolve_tenant["return"] = TEST_TENANT_ID
        resp = client.post(
            "/api/v1/epcis/events?tenant_id=other",
            json={"type": "ObjectEvent"},
        )
        assert resp.status_code == 403
        assert "query parameter is not accepted" in resp.json()["detail"]


class TestValidateEndpoint:
    """The /validate endpoint is simple enough that we just cover its
    happy path alongside error branches to keep the file self-sufficient."""

    def test_invalid_payload_reports_errors_and_no_normalized(
        self, client: TestClient
    ) -> None:
        # Missing required EPCIS fields → errors list, normalized None.
        resp = client.post("/api/v1/epcis/validate", json={"type": "ObjectEvent"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert body["errors"]
        assert body["normalized_cte"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
