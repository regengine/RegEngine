"""Tests for webhook ingest funnel instrumentation."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import app.webhook_router_v2 as webhook_router_v2  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.webhook_router_v2 import _verify_api_key, _get_db_session  # noqa: E402


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
            event_id="00000000-0000-0000-0000-000000000001",
            sha256_hash="abc123",
            chain_hash="def456",
            idempotent=False,
        )

    def store_events_batch(self, **_kwargs):
        events = _kwargs.get("events", [])
        return [
            SimpleNamespace(
                event_id=f"00000000-0000-0000-0000-{i + 1:012d}",
                sha256_hash="abc123",
                chain_hash="def456",
                idempotent=False,
            )
            for i in range(len(events))
        ]


class _FakeCanonical:
    def __init__(self, tlc: str):
        self.event_id = UUID("00000000-0000-0000-0000-00000000cafe")
        self.event_type = SimpleNamespace(value="shipping")
        self.traceability_lot_code = tlc
        self.product_reference = "prod-ref"
        self.quantity = 10
        self.unit_of_measure = "cases"
        self.from_facility_reference = None
        self.to_facility_reference = None
        self.from_entity_reference = None
        self.to_entity_reference = None
        self.kdes = {}

    def prepare_for_persistence(self):
        return self


class _FakeCanonicalStore:
    def __init__(self, *_args, **_kwargs):
        pass

    def persist_event(self, *_args, **_kwargs):
        return None


class _FakeRulesSummary:
    compliant = True
    results = []


class _FakeRulesEngine:
    def __init__(self, *_args, **_kwargs):
        pass

    def evaluate_event(self, *_args, **_kwargs):
        return _FakeRulesSummary()


class _FakeExceptionQueue:
    def __init__(self, *_args, **_kwargs):
        pass

    def create_exceptions_from_evaluation(self, *_args, **_kwargs):
        return None


def test_ingest_events_emits_first_ingest_funnel_event(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(webhook_router_v2.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key",
        scopes=["*"],
        auth_mode="test",
    )
    app.dependency_overrides[_verify_api_key] = lambda: None
    def _fake_get_db_session():
        yield _FakeDBSession()

    app.dependency_overrides[_get_db_session] = _fake_get_db_session
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
    monkeypatch.setitem(
        sys.modules,
        "shared.canonical_persistence",
        SimpleNamespace(CanonicalEventStore=_FakeCanonicalStore),
    )
    monkeypatch.setitem(sys.modules, "shared.rules_engine", SimpleNamespace(RulesEngine=_FakeRulesEngine))
    monkeypatch.setitem(
        sys.modules,
        "shared.exception_queue",
        SimpleNamespace(ExceptionQueueService=_FakeExceptionQueue),
    )
    monkeypatch.setattr(
        webhook_router_v2,
        "normalize_webhook_event",
        lambda event, tenant_id, **_kwargs: _FakeCanonical(event.traceability_lot_code),
    )

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
                    "reference_document": "BOL-2026-001",
                    "tlc_source_reference": "REF-LOT-001",
                },
            }
        ],
    }

    with TestClient(app) as client:
        # #1232: /webhooks/ingest requires a tenant-scoped Idempotency-Key.
        response = client.post(
            "/api/v1/webhooks/ingest",
            json=payload,
            headers={"Idempotency-Key": "test-funnel-idem-1"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] == 1
    assert captured["tenant_id"] == payload["tenant_id"]
    assert captured["event_name"] == "first_ingest"
