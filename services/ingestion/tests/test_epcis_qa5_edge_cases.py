"""Edge-case regression tests for ``app/epcis`` (QA5 deep pass).

Covers three real defects found by reading the module:

1. ``GET /api/v1/epcis/export`` with a malformed ``start_date``/``end_date``
   crashed with HTTP 500 (``ValueError`` from ``datetime.fromisoformat`` in
   the in-memory fallback path; a SQL error surfaced as 503 on the DB path).
2. ``GET /api/v1/epcis/export`` with a date-only (timezone-naive)
   ``start_date``/``end_date`` crashed with HTTP 500 (``TypeError`` comparing
   offset-naive and offset-aware datetimes in the fallback filter).
3. ``_ingest_single_event_fallback`` raised ``KeyError`` (HTTP 500) when the
   per-tenant idempotency index referenced an event id that FIFO eviction
   had already dropped from the store.
4. ``POST /api/v1/epcis/validate`` raised an HTTP error for a structurally
   valid event whose ``bizStep`` has no CTE mapping, instead of returning
   ``{"valid": False, ...}`` like every other invalid input.
"""

from __future__ import annotations

import copy
import importlib
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

router_mod = importlib.import_module("app.epcis.router")
persistence_mod = importlib.import_module("app.epcis.persistence")
from app.webhook_compat import _verify_api_key  # noqa: E402

from services.ingestion.tests.tenant_context_overrides import (  # noqa: E402
    install_tenant_context_override,
)

TEST_TENANT_ID = "11111111-2222-3333-4444-555555555555"

_VALID_EPCIS = {
    "type": "ObjectEvent",
    "eventTime": "2026-02-28T09:30:00-05:00",
    "eventTimeZoneOffset": "-05:00",
    "action": "OBSERVE",
    "bizStep": "urn:epcglobal:cbv:bizstep:receiving",
    "bizLocation": {"id": "urn:epc:id:sgln:0614141.00002.0"},
    "ilmd": {
        "cbvmda:lotNumber": "ROM-0042",
        "fsma:traceabilityLotCode": "00012345678901-ROM0042",
    },
    "extension": {
        "quantityList": [
            {
                "epcClass": "urn:epc:class:lgtin:0614141.107346.ROM0042",
                "quantity": 10.0,
                "uom": "CS",
            },
        ],
    },
}

_UNMAPPED_BIZSTEP_EVENT = {
    **_VALID_EPCIS,
    "bizStep": "urn:epcglobal:cbv:bizstep:void_shipping",
}


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(router_mod.router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    install_tenant_context_override(app, default_tenant=TEST_TENANT_ID, enforce_claims=True)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(autouse=True)
def _clear_fallback_stores():
    persistence_mod._epcis_store.clear()
    persistence_mod._epcis_idempotency_index.clear()
    yield
    persistence_mod._epcis_store.clear()
    persistence_mod._epcis_idempotency_index.clear()


def _force_fallback(monkeypatch: pytest.MonkeyPatch, store: dict) -> None:
    monkeypatch.setattr(router_mod, "_list_events_from_db", lambda *a, **kw: [])
    monkeypatch.setattr(router_mod, "_allow_in_memory_fallback", lambda: True)
    monkeypatch.setattr(router_mod, "_fallback_store_for", lambda t: store)


# ── Export date handling ───────────────────────────────────────────────────


class TestExportDateHandling:
    @pytest.mark.parametrize("param", ["start_date", "end_date"])
    def test_malformed_date_returns_400(self, client: TestClient, monkeypatch: pytest.MonkeyPatch, param: str) -> None:
        """Garbage dates are a client error (400), not a crash (500/503)."""
        _force_fallback(monkeypatch, {})
        resp = client.get(f"/api/v1/epcis/export?{param}=not-a-date")
        assert resp.status_code == 400
        assert param in resp.json()["detail"]

    def test_naive_date_only_start_filters_without_crash(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A date-only (naive) start_date must compare cleanly against
        timezone-aware event times instead of raising TypeError."""
        store = {
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
        _force_fallback(monkeypatch, store)
        resp = client.get("/api/v1/epcis/export?start_date=2026-01-01")
        assert resp.status_code == 200
        ids = [e.get("id") for e in resp.json()["epcisBody"]["eventList"]]
        assert ids == ["late"]

    def test_naive_date_only_end_filters_without_crash(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = {
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
        _force_fallback(monkeypatch, store)
        resp = client.get("/api/v1/epcis/export?end_date=2026-01-01")
        assert resp.status_code == 200
        ids = [e.get("id") for e in resp.json()["epcisBody"]["eventList"]]
        assert ids == ["early"]


# ── Fallback idempotency after FIFO eviction ───────────────────────────────


class TestFallbackStaleIdempotency:
    def test_stale_index_entry_is_repaired_not_crashed(self) -> None:
        """An idempotency index entry pointing at an evicted event must be
        treated as a fresh ingest (201), not raise KeyError (500)."""
        tenant = "tenant-1"
        event = copy.deepcopy(_VALID_EPCIS)
        event["eventID"] = "evt-stale-replay"
        persistence_mod._fallback_idempotency_for(tenant)["evt-stale-replay"] = "evicted-id"

        payload, status = persistence_mod._ingest_single_event_fallback(tenant, event)

        assert status == 201
        assert payload.get("idempotent") is False
        repaired = persistence_mod._fallback_idempotency_for(tenant)["evt-stale-replay"]
        assert repaired != "evicted-id"
        assert repaired in persistence_mod._fallback_store_for(tenant)

    def test_index_entry_without_store_record_is_treated_as_fresh(self) -> None:
        """Direct variant: any index entry whose record is gone (however it
        got that way) repairs itself with a fresh ingest, never KeyError."""
        tenant = "tenant-1"
        event = copy.deepcopy(_VALID_EPCIS)
        event["eventID"] = "evt-orphan-key"
        persistence_mod._fallback_idempotency_for(tenant)["evt-orphan-key"] = "no-such-record"

        payload, status = persistence_mod._ingest_single_event_fallback(tenant, event)

        assert status == 201
        assert persistence_mod._fallback_idempotency_for(tenant)["evt-orphan-key"] == payload["cte_id"]


# ── Validate endpoint consistency ──────────────────────────────────────────


class TestValidateEndpoint:
    def test_unmapped_bizstep_returns_valid_false(self, client: TestClient) -> None:
        """A structurally valid event with an unmapped bizStep is invalid
        input (200 + valid:false), not an HTTP error."""
        resp = client.post("/api/v1/epcis/validate", json=_UNMAPPED_BIZSTEP_EVENT)
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert body["errors"]
        assert body["normalized_cte"] is None

    def test_valid_event_still_validates(self, client: TestClient) -> None:
        resp = client.post("/api/v1/epcis/validate", json=_VALID_EPCIS)
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["normalized_cte"]["event_type"] == "receiving"

    def test_structural_errors_still_reported(self, client: TestClient) -> None:
        resp = client.post("/api/v1/epcis/validate", json={"type": "ObjectEvent"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert body["normalized_cte"] is None
