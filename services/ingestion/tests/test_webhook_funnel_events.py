"""Tests for webhook ingest funnel instrumentation."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import app.webhook_router_v2 as webhook_router_v2
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.webhook_router_v2 import _verify_api_key, _get_db_session


class _FakeDBSession:
    def execute(self, *_args, **_kwargs):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


class _FakePersistence:
    def __init__(self, _db_session):
        self._db_session = _db_session

    def store_event(self, **_kwargs):
        return SimpleNamespace(
            event_id="evt-1",
            sha256_hash="abc123",
            chain_hash="def456",
            idempotent=False,
        )


def test_ingest_events_emits_first_ingest_funnel_event(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(webhook_router_v2.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key",
        scopes=["*"],
        auth_mode="test",
    )
    app.dependency_overrides[_verify_api_key] = lambda: None
    app.dependency_overrides[_get_db_session] = lambda: _FakeDBSession()
    captured: dict[str, object] = {}

    monkeypatch.setattr(webhook_router_v2, "_check_rate_limit", lambda _tenant_id: None)
    monkeypatch.setattr(webhook_router_v2, "_check_obligations", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(webhook_router_v2, "_publish_graph_sync", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        webhook_router_v2,
        "emit_funnel_event",
        lambda **kwargs: captured.update(kwargs) or True,
    )

    monkeypatch.setitem(sys.modules, "shared.database", SimpleNamespace(SessionLocal=lambda: _FakeDBSession()))
    monkeypatch.setitem(sys.modules, "shared.cte_persistence", SimpleNamespace(CTEPersistence=_FakePersistence))

    payload = {
        "tenant_id": "00000000-0000-0000-0000-000000000111",
        "source": "api_test",
        "events": [
            {
                "cte_type": "shipping",
                "traceability_lot_code": "LOT-2026-TEST-001",
                "product_description": "Romaine Lettuce",
                "quantity": 10,
                "unit_of_measure": "cases",
                "location_name": "Dock 1",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "kdes": {
                    "ship_date": datetime.now(timezone.utc).date().isoformat(),
                    "ship_from_location": "Warehouse A",
                    "ship_to_location": "Retail DC",
                },
            }
        ],
    }

    with TestClient(app) as client:
        response = client.post("/api/v1/webhooks/ingest", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] == 1
    assert captured["tenant_id"] == payload["tenant_id"]
    assert captured["event_name"] == "first_ingest"
