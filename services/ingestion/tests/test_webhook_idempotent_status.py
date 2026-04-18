"""Tests for #1248 — idempotent-success status in webhook responses.

Before the fix:
  - An in-memory ``seen_in_batch`` set rejected within-request duplicates
    as ``status="rejected"`` using a strictly narrower dedup key
    (omitted ``source`` and ``kdes``) than ``compute_idempotency_key``.
  - Cross-request duplicates could silently both persist because the
    in-memory set was bounded to the current request and no DB-level
    composite UNIQUE on ``(tenant_id, idempotency_key)`` existed.
  - Events that DID match an existing row via the persistence layer's
    pre-flight idempotency SELECT were still reported as
    ``status="accepted"`` — indistinguishable from new events.

After the fix:
  - No in-memory seen_in_batch: dedup lives at the DB layer.
  - Events whose content matches an existing row come back from
    ``store_events_batch`` as ``idempotent=True`` and are surfaced to
    the caller as ``status="idempotent"`` — a distinct, retry-safe
    success signal.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import app.webhook_router_v2 as webhook_router_v2
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.webhook_router_v2 import _get_db_session, _verify_api_key


class _FakeDBSession:
    def execute(self, *_args, **_kwargs):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


def _make_persistence_class(idempotent_flags: list[bool]):
    """Build a ``_FakePersistence`` subclass that returns results with
    the given ``idempotent`` flags in order, one per input event."""

    class _FakePersistence:
        def __init__(self, _db_session):
            self._db_session = _db_session

        def store_events_batch(self, **kwargs):
            events = kwargs.get("events", [])
            return [
                SimpleNamespace(
                    event_id=f"evt-{i+1}",
                    sha256_hash="a" * 64,
                    chain_hash="b" * 64,
                    idempotent=bool(idempotent_flags[i % len(idempotent_flags)]),
                )
                for i in range(len(events))
            ]

    return _FakePersistence


def _build_app(monkeypatch, persistence_cls) -> FastAPI:
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

    monkeypatch.setattr(webhook_router_v2, "_check_rate_limit", lambda _tid: None)
    monkeypatch.setattr(
        webhook_router_v2, "_check_obligations", lambda *a, **kw: []
    )
    monkeypatch.setattr(
        webhook_router_v2, "_publish_graph_sync", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        webhook_router_v2,
        "emit_funnel_event",
        lambda **kwargs: True,
    )

    monkeypatch.setitem(
        sys.modules,
        "shared.database",
        SimpleNamespace(SessionLocal=lambda: _FakeDBSession()),
    )
    monkeypatch.setitem(
        sys.modules,
        "shared.cte_persistence",
        SimpleNamespace(CTEPersistence=persistence_cls),
    )

    # Canonical + rules path is best-effort in the router and we don't
    # need to exercise it for the status-mapping assertions.
    monkeypatch.setitem(
        sys.modules,
        "shared.canonical_persistence",
        SimpleNamespace(CanonicalEventStore=_NoopCanonicalStore),
    )
    monkeypatch.setitem(
        sys.modules,
        "shared.rules_engine",
        SimpleNamespace(RulesEngine=_NoopRulesEngine),
    )
    return app


class _NoopCanonicalStore:
    def __init__(self, *_a, **_kw):
        pass

    def persist_event(self, *_a, **_kw):
        return SimpleNamespace(
            event_id="canon-1",
            sha256_hash="c" * 64,
            chain_hash="c" * 64,
            idempotent=False,
        )


class _NoopRulesEngine:
    def __init__(self, *_a, **_kw):
        pass

    def evaluate(self, *_a, **_kw):
        return SimpleNamespace(compliant=True, violations=[])


def _sample_event(lot: str = "LOT-1") -> dict:
    return {
        "cte_type": "shipping",
        "traceability_lot_code": lot,
        "product_description": "Romaine Lettuce",
        "quantity": 10,
        "unit_of_measure": "cases",
        "location_name": "Dock 1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kdes": {
            "ship_date": datetime.now(timezone.utc).date().isoformat(),
            "ship_from_location": "Warehouse A",
            "ship_to_location": "Retail DC",
            "reference_document": f"BOL-{lot}",
            "tlc_source_reference": f"REF-{lot}",
        },
    }


class TestIdempotentStatus_Issue1248:
    def test_idempotent_persistence_result_surfaces_as_status_idempotent(
        self, monkeypatch
    ):
        """When persistence reports idempotent=True, the API must set
        ``status="idempotent"`` on the returned EventResult, not
        ``"accepted"``. Clients can then distinguish a retry from a
        newly-persisted event."""
        app = _build_app(
            monkeypatch,
            _make_persistence_class(idempotent_flags=[True]),
        )
        payload = {
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "source": "api_test",
            "events": [_sample_event()],
        }

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/webhooks/ingest",
                json=payload,
                headers={"Idempotency-Key": "test-batch-1"},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["events"]) == 1
        assert body["events"][0]["status"] == "idempotent", (
            f"expected idempotent status, got {body['events'][0]['status']!r}"
        )
        # Idempotent events still count as not-rejected — the body's
        # accepted counter reflects that.
        assert body["accepted"] == 1
        assert body["rejected"] == 0

    def test_new_event_surfaces_as_status_accepted(self, monkeypatch):
        """Guard against over-aggressive idempotent tagging: a
        ``idempotent=False`` result must stay ``status="accepted"``."""
        app = _build_app(
            monkeypatch,
            _make_persistence_class(idempotent_flags=[False]),
        )
        payload = {
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "source": "api_test",
            "events": [_sample_event()],
        }

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/webhooks/ingest",
                json=payload,
                headers={"Idempotency-Key": "test-batch-1"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["events"][0]["status"] == "accepted"

    def test_within_batch_duplicate_no_longer_rejected(self, monkeypatch):
        """Before #1248 two identical events in the same payload
        produced [accepted, rejected]. After: the DB layer dedups; the
        first lands (accepted), the second is reported idempotent —
        NEVER rejected. No user-observable data loss."""
        app = _build_app(
            monkeypatch,
            # Two events in batch: first is new, second is a dupe.
            _make_persistence_class(idempotent_flags=[False, True]),
        )
        evt = _sample_event()
        payload = {
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "source": "api_test",
            "events": [evt, evt],
        }

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/webhooks/ingest",
                json=payload,
                headers={"Idempotency-Key": "test-batch-1"},
            )

        assert response.status_code == 200
        body = response.json()
        statuses = [e["status"] for e in body["events"]]
        assert statuses == ["accepted", "idempotent"], (
            f"duplicate must surface as idempotent, not rejected; got {statuses}"
        )
        # Both counted as accepted (idempotent is a success, not a reject).
        assert body["rejected"] == 0
