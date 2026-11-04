"""Edge-case checks that do not need an EPCIS record.

Stale idempotency repair and a structurally valid unmapped bizStep need a
real event. Malformed dates, empty-document date filters, and ``{}`` on
``/validate`` do not.
"""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timezone
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
    monkeypatch.setattr(
        router_mod,
        "_list_events_from_db_detailed",
        lambda *a, **kw: persistence_mod.EpcisExportPage(
            events=[], truncated=False, limit=persistence_mod.EXPORT_EVENT_LIMIT
        ),
    )
    monkeypatch.setattr(router_mod, "_allow_in_memory_fallback", lambda: True)
    monkeypatch.setattr(router_mod, "_fallback_store_for", lambda t: store)


def _date_only_export_case() -> tuple[dict, str]:
    """One stored clock reading and the date-only form of that same reading.

    An untimed record stays in every export. The timed record is kept or
    dropped by comparison with its own calendar date, not a separate offset.
    """
    moment = datetime.now(timezone.utc)
    return {
        "untimed": {"normalized_cte": {}, "epcis_document": {}},
        "timed": {
            "normalized_cte": {"event_time": moment.isoformat()},
            "epcis_document": {},
        },
    }, moment.date().isoformat()


def _assert_bound_orders_stored_time(store: dict, bound: str) -> datetime:
    stored = datetime.fromisoformat(store["timed"]["normalized_cte"]["event_time"])
    bound_dt = router_mod._parse_export_bound(bound, "start_date")
    assert bound_dt is not None and stored.tzinfo is not None and bound_dt.tzinfo is not None
    assert bound_dt <= stored
    return stored


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
        store, bound = _date_only_export_case()
        stored = _assert_bound_orders_stored_time(store, bound)
        _force_fallback(monkeypatch, store)
        resp = client.get(f"/api/v1/epcis/export?start_date={bound}")
        assert resp.status_code == 200
        body = resp.json()
        created = datetime.fromisoformat(body["creationDate"])
        assert created.tzinfo is not None
        assert stored <= created
        assert len(body["epcisBody"]["eventList"]) == 2
        assert "Traceback" not in resp.text

    def test_naive_date_only_end_filters_without_crash(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store, bound = _date_only_export_case()
        stored = _assert_bound_orders_stored_time(store, bound)
        _force_fallback(monkeypatch, store)
        resp = client.get(f"/api/v1/epcis/export?end_date={bound}")
        assert resp.status_code == 200
        body = resp.json()
        created = datetime.fromisoformat(body["creationDate"])
        assert created.tzinfo is not None
        assert stored <= created
        assert len(body["epcisBody"]["eventList"]) == 1
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
