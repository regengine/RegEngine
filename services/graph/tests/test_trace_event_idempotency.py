"""Retry safety for POST /event (Pattern 1: idempotency keys).

A retried mobile capture carrying the same caller-stable
``Idempotency-Key`` must resolve to the same TraceEvent node (MERGE on
the derived stable id) instead of duplicating compliance evidence.
Different keys, and requests without a key, keep the old behavior.
"""

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

_AUTH_HEADERS = {"X-RegEngine-API-Key": os.getenv("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token-for-pytest")}
_TENANT = uuid.UUID("00000000-0000-0000-0000-000000000001")

_PAYLOAD = {
    "event_type": "RECEIVING",
    "event_date": "2026-02-22",
    "tlc": "TLC-2024-001",
    "location_identifier": "0614141000036",
    "responsible_party_contact": "Jane Doe, 555-0100, jane@example.com",
    "product_description": "Green Spinach 10oz",
    "gtin": "10614141000019",
    "quantity": 24,
    "uom": "cases",
}


@pytest.fixture
def mock_neo4j_client():
    with patch("services.graph.app.routers.fsma.traceability.Neo4jClient") as mock:
        mock_instance = MagicMock()
        mock_instance.close = AsyncMock()
        mock_instance.session.return_value.__aenter__.return_value.run = AsyncMock()
        mock.return_value = mock_instance
        mock.get_tenant_database_name.return_value = "test-db"
        yield mock_instance


@pytest.fixture
def mock_validation():
    with (
        patch("services.graph.app.routers.fsma.traceability.validate_tlc") as mock_tlc,
        patch("services.graph.app.routers.fsma.traceability.validate_gln") as mock_gln,
        patch("services.graph.app.routers.fsma.traceability.validate_gtin") as mock_gtin,
    ):
        mock_tlc.return_value = MagicMock(is_valid=True)
        mock_gln.return_value = MagicMock(is_valid=True)
        mock_gtin.return_value = MagicMock(is_valid=True)
        yield mock_tlc, mock_gln, mock_gtin


@pytest.fixture(autouse=True)
def _clean_slowapi_bucket():
    """Keep this file's POSTs out of other files' rate-limit quota.

    The shared slowapi limiter keeps one in-process 10/min bucket for
    ``POST /event`` keyed by client host, so without this the 7 POSTs
    below plus the 6 in ``test_mobile_ingestion.py`` exceed the quota
    when both files run in one pytest process. Reset before and after
    each test so pass/fail does not depend on file order. Best effort:
    if the storage backend ever stops offering ``reset()``, the tests
    themselves still pass standalone and only the combined run can 429.
    """
    from shared.rate_limit import limiter

    reset = getattr(limiter._storage, "reset", None)
    if callable(reset):
        reset()
    yield
    reset = getattr(limiter._storage, "reset", None)
    if callable(reset):
        reset()


def _client():
    from shared.auth import require_api_key
    from shared.middleware import get_current_tenant_id
    from shared.rate_limit import add_rate_limiting

    from services.graph.app.routers.fsma.traceability import router

    app = FastAPI()
    add_rate_limiting(app)
    app.include_router(router)
    app.dependency_overrides[require_api_key] = lambda: {"tenant_id": "test-tenant"}
    app.dependency_overrides[get_current_tenant_id] = lambda: _TENANT
    return TestClient(app)


def _post(client, headers=None):
    with (
        patch("shared.canonical_persistence.CanonicalEventStore"),
        patch("shared.database.SessionLocal"),
    ):
        return client.post("/event", json=_PAYLOAD, headers={**_AUTH_HEADERS, **(headers or {})})


def test_same_key_twice_returns_same_event_id(mock_neo4j_client, mock_validation):
    """The core retry case: same key plus same body is one logical write."""
    client = _client()
    headers = {"Idempotency-Key": "field-capture-0001"}

    first = _post(client, headers)
    second = _post(client, headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["event_id"] == second.json()["event_id"]


def test_same_key_uses_merge_not_create(mock_neo4j_client, mock_validation):
    """The stable id is only safe because the write MERGEs on it."""
    from services.graph.app.routers.fsma.traceability import idempotent_event_id

    client = _client()
    key = "field-capture-0002"
    response = _post(client, {"Idempotency-Key": key})
    assert response.status_code == 200

    run = mock_neo4j_client.session.return_value.__aenter__.return_value.run
    cypher_statements = [call.args[0] for call in run.call_args_list]
    trace_write = cypher_statements[0]
    assert "MERGE" in trace_write
    assert "CREATE (e:TraceEvent" not in trace_write
    assert response.json()["event_id"] == idempotent_event_id(str(_TENANT), key)


def test_different_keys_create_different_events(mock_neo4j_client, mock_validation):
    """Distinct user actions must not collapse onto one node."""
    client = _client()
    first = _post(client, {"Idempotency-Key": "field-capture-A"})
    second = _post(client, {"Idempotency-Key": "field-capture-B"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["event_id"] != second.json()["event_id"]


def test_no_key_keeps_legacy_create_path(mock_neo4j_client, mock_validation):
    """Callers that send no key get the old behavior: fresh id, CREATE."""
    client = _client()
    first = _post(client)
    second = _post(client)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["event_id"] != second.json()["event_id"]

    run = mock_neo4j_client.session.return_value.__aenter__.return_value.run
    cypher_statements = [call.args[0] for call in run.call_args_list]
    assert "CREATE (e:TraceEvent" in cypher_statements[0]


def test_derived_ids_are_tenant_scoped():
    """Same key under different tenants must never name the same node."""
    from services.graph.app.routers.fsma.traceability import idempotent_document_id, idempotent_event_id

    assert idempotent_event_id("tenant-a", "k") != idempotent_event_id("tenant-b", "k")
    assert idempotent_event_id("tenant-a", "k") != idempotent_event_id("tenant-a", "other")
    assert idempotent_event_id("tenant-a", "k") == idempotent_event_id("tenant-a", "k")
    assert idempotent_document_id("tenant-a", "k") != idempotent_event_id("tenant-a", "k")
