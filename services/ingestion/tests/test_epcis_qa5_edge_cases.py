"""Edge-case checks that do not need an EPCIS record.

Stale idempotency repair and a structurally valid unmapped bizStep need a
real event. Malformed dates, empty-document date filters, and ``{}`` on
``/validate`` do not.
"""

from __future__ import annotations

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


def _timestamp_store() -> dict:
    return {
        "early": {
            "normalized_cte": {"event_time": "2020-01-01T00:00:00+00:00"},
            "epcis_document": {},
        },
        "late": {
            "normalized_cte": {"event_time": "2026-06-01T00:00:00+00:00"},
            "epcis_document": {},
        },
    }


class TestExportDateHandling:
    @pytest.mark.parametrize("param", ["start_date", "end_date"])
    def test_malformed_date_returns_400(self, client: TestClient, monkeypatch: pytest.MonkeyPatch, param: str) -> None:
        _force_fallback(monkeypatch, {})
        resp = client.get(f"/api/v1/epcis/export?{param}=not-a-date")
        assert resp.status_code == 400
        assert param in resp.json()["detail"]
        assert "Traceback" not in resp.text

    def test_naive_date_only_start_filters_without_crash(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _force_fallback(monkeypatch, _timestamp_store())
        resp = client.get("/api/v1/epcis/export?start_date=2026-01-01")
        assert resp.status_code == 200
        events = resp.json()["epcisBody"]["eventList"]
        assert len(events) == 1
        assert "Traceback" not in resp.text

    def test_naive_date_only_end_filters_without_crash(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _force_fallback(monkeypatch, _timestamp_store())
        resp = client.get("/api/v1/epcis/export?end_date=2026-01-01")
        assert resp.status_code == 200
        events = resp.json()["epcisBody"]["eventList"]
        assert len(events) == 1
        assert "Traceback" not in resp.text


class TestValidateEndpoint:
    def test_unmapped_bizstep_returns_valid_false(self, client: TestClient) -> None:
        resp = client.post("/api/v1/epcis/validate", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert body["errors"]
        assert body["normalized_cte"] is None
        assert "Traceback" not in resp.text

    def test_structural_errors_still_reported(self, client: TestClient) -> None:
        resp = client.post("/api/v1/epcis/validate", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert body["normalized_cte"] is None
        assert "Traceback" not in resp.text
