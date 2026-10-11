"""API tests for B2B exchange endpoints."""

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.authz as authz
import app.exchange_api as exchange_api
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.exchange_api import _exchange_store, router as exchange_router


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app = FastAPI()
    app.include_router(exchange_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key",
        scopes=["*"],
        auth_mode="test",
    )

    _exchange_store.clear()
    monkeypatch.setenv("ALLOW_EXCHANGE_IN_MEMORY_FALLBACK", "true")

    def _db_unavailable():
        raise RuntimeError("db unavailable in unit test")

    # exchange_api calls ``get_db_safe()`` directly (not via Depends),
    # so the seam for forcing the in-memory fallback path is to swap
    # the function at module scope.
    monkeypatch.setattr(exchange_api, "get_db_safe", _db_unavailable)

    with TestClient(app) as test_client:
        yield test_client

    _exchange_store.clear()


def test_send_receive_and_mark_received(client: TestClient) -> None:
    sender_tenant_id = "00000000-0000-0000-0000-000000000111"
    receiver_tenant_id = "00000000-0000-0000-0000-000000000222"

    send_response = client.post(
        "/api/v1/exchange/send",
        params={"tenant_id": sender_tenant_id},
        json={
            "receiver_tenant_id": receiver_tenant_id,
            "event_ids": ["evt-1", "evt-2"],
            "traceability_lot_code": "LOT-2026-001",
            "receiver_email": "receiving@example.com",
        },
    )
    assert send_response.status_code == 200

    send_payload = send_response.json()
    package_id = send_payload["package_id"]
    assert send_payload["status"] == "queued"
    assert send_payload["event_count"] == 2
    assert send_payload["traceability_lot_codes"] == ["LOT-2026-001"]
    assert send_payload["notification"]["status"] == "queued"

    receive_response = client.get(
        "/api/v1/exchange/receive",
        params={
            "tenant_id": receiver_tenant_id,
            "include_payload": False,
        },
    )
    assert receive_response.status_code == 200
    receive_payload = receive_response.json()
    assert receive_payload["count"] == 1
    package_summary = receive_payload["packages"][0]
    assert package_summary["package_id"] == package_id
    assert package_summary["status"] == "pending"
    assert "payload" not in package_summary

    mark_received_response = client.get(
        "/api/v1/exchange/receive",
        params={
            "tenant_id": receiver_tenant_id,
            "package_id": package_id,
            "mark_received": True,
        },
    )
    assert mark_received_response.status_code == 200
    mark_payload = mark_received_response.json()
    assert mark_payload["count"] == 1
    received_package = mark_payload["packages"][0]
    assert received_package["package_id"] == package_id
    assert received_package["status"] == "received"
    assert received_package["received_at"] is not None
    assert len(received_package["payload"]["records"]) == 2


def test_send_requires_sender_tenant_context(client: TestClient) -> None:
    response = client.post(
        "/api/v1/exchange/send",
        json={
            "receiver_tenant_id": "00000000-0000-0000-0000-000000000222",
            "event_ids": ["evt-1"],
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Tenant context required"


def test_receive_requires_receiver_tenant_context(client: TestClient) -> None:
    response = client.get("/api/v1/exchange/receive")
    assert response.status_code == 400
    assert response.json()["detail"] == "Tenant context required"


def test_send_fallback_lot_codes_only_carries_records(client: TestClient) -> None:
    """Fallback sends keyed only by lot_codes must carry one record per lot.

    Before the fix the fallback loop only read ``event_ids``, so a valid
    lot_codes-only request queued a package whose summary claimed lots but
    whose records list was empty.
    """
    sender_tenant_id = "00000000-0000-0000-0000-000000000111"
    receiver_tenant_id = "00000000-0000-0000-0000-000000000222"

    send_response = client.post(
        "/api/v1/exchange/send",
        params={"tenant_id": sender_tenant_id},
        json={
            "receiver_tenant_id": receiver_tenant_id,
            "lot_codes": ["LOT-2026-002", "LOT-2026-001"],
        },
    )
    assert send_response.status_code == 200
    send_payload = send_response.json()
    assert send_payload["event_count"] == 2
    assert send_payload["traceability_lot_codes"] == ["LOT-2026-001", "LOT-2026-002"]

    receive_response = client.get(
        "/api/v1/exchange/receive",
        params={"tenant_id": receiver_tenant_id, "package_id": send_payload["package_id"]},
    )
    assert receive_response.status_code == 200
    package = receive_response.json()["packages"][0]
    record_lots = sorted(record["traceability_lot_code"] for record in package["payload"]["records"])
    assert record_lots == ["LOT-2026-001", "LOT-2026-002"]


def test_send_fallback_without_filters_returns_400(client: TestClient) -> None:
    """The fallback must enforce the same filter contract as the DB path."""
    response = client.post(
        "/api/v1/exchange/send",
        params={"tenant_id": "00000000-0000-0000-0000-000000000111"},
        json={"receiver_tenant_id": "00000000-0000-0000-0000-000000000222"},
    )
    assert response.status_code == 400
    assert "traceability_lot_code" in response.json()["detail"]


def test_send_sender_override_mismatch_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tenant-bound principal cannot send as another tenant via the body override."""
    app = FastAPI()
    app.include_router(exchange_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="tenant-a-key",
        tenant_id="00000000-0000-0000-0000-000000000111",
        scopes=["exchange.write"],
        auth_mode="test",
    )
    _exchange_store.clear()
    monkeypatch.setenv("ALLOW_EXCHANGE_IN_MEMORY_FALLBACK", "true")

    def _db_unavailable():
        raise RuntimeError("db unavailable in unit test")

    monkeypatch.setattr(exchange_api, "get_db_safe", _db_unavailable)

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/exchange/send",
            json={
                "receiver_tenant_id": "00000000-0000-0000-0000-000000000222",
                "sender_tenant_id": "00000000-0000-0000-0000-000000000999",
                "event_ids": ["evt-1"],
            },
        )

    assert response.status_code == 403
    assert "Tenant mismatch" in response.json()["detail"]


def test_send_conflicting_tenant_query_and_header_returns_400(client: TestClient) -> None:
    response = client.post(
        "/api/v1/exchange/send",
        params={"tenant_id": "00000000-0000-0000-0000-000000000111"},
        headers={"X-Tenant-ID": "00000000-0000-0000-0000-000000000999"},
        json={
            "receiver_tenant_id": "00000000-0000-0000-0000-000000000222",
            "event_ids": ["evt-1"],
        },
    )
    assert response.status_code == 400
    assert "Conflicting tenant context" in response.json()["detail"]


def test_send_denied_without_exchange_write_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.include_router(exchange_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="limited-key",
        scopes=["exchange.read"],
        auth_mode="test",
    )
    _exchange_store.clear()
    monkeypatch.setenv("ALLOW_EXCHANGE_IN_MEMORY_FALLBACK", "true")

    def _db_unavailable():
        raise RuntimeError("db unavailable in unit test")

    # exchange_api calls ``get_db_safe()`` directly (not via Depends),
    # so the seam for forcing the in-memory fallback path is to swap
    # the function at module scope.
    monkeypatch.setattr(exchange_api, "get_db_safe", _db_unavailable)

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/exchange/send",
            params={"tenant_id": "00000000-0000-0000-0000-000000000111"},
            json={
                "receiver_tenant_id": "00000000-0000-0000-0000-000000000222",
                "event_ids": ["evt-1"],
            },
        )

    assert response.status_code == 403
    assert "requires 'exchange.write'" in response.json()["detail"]


def test_send_rate_limited_returns_429(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.include_router(exchange_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="tenant-limited-key",
        tenant_id="00000000-0000-0000-0000-000000000111",
        scopes=["exchange.write"],
        auth_mode="test",
    )

    monkeypatch.setattr(
        authz,
        "consume_tenant_rate_limit",
        lambda **_kwargs: (False, 0),
    )

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/exchange/send",
            params={"tenant_id": "00000000-0000-0000-0000-000000000111"},
            json={
                "receiver_tenant_id": "00000000-0000-0000-0000-000000000222",
                "event_ids": ["evt-1"],
            },
        )

    assert response.status_code == 429
    assert "Rate limit exceeded" in response.json()["detail"]
    assert response.headers["x-ratelimit-scope"] == "exchange.write"
