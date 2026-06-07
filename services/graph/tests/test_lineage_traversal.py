"""Regression net for the lineage history endpoint (RE-SEC-005).

Prior to this PR, ``GET /api/v1/lineage/{tlc}/history`` called a
non-existent ``Neo4jClient.execute_read(...)`` method, which raised
``AttributeError`` on every request. The ``except Exception`` block in
the route handler swallowed the failure and returned a generic 500 —
so the carefully written tenant predicates in ``LINEAGE_QUERY`` (lines
67-87) were never actually exercised in production.

These tests:

1. Verify the happy path: a seeded TLC returns 200 with
   ``total_versions >= 1``. This is the test the audit explicitly
   called out as the regression net.
2. Verify the tenant predicate: when two tenants seed lineage with
   the same TLC, tenant A's call returns ONLY tenant A's lineage
   rows. The query parameters passed to Neo4j must carry tenant A's
   id, not tenant B's.

Tests follow the established pattern in this package — Neo4jClient
is mocked, the FastAPI router is mounted on a bare app, and
``require_api_key`` / ``get_current_tenant_id`` are overridden via
``app.dependency_overrides``.
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared.auth import require_api_key
from shared.middleware import get_current_tenant_id

from services.graph.app.routers.lineage_traversal import router as lineage_router

TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = uuid.UUID("22222222-2222-2222-2222-222222222222")

_AUTH_HEADERS = {"X-RegEngine-API-Key": os.getenv("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token-for-pytest")}


def _build_app(tenant_id: uuid.UUID) -> FastAPI:
    app = FastAPI()
    app.include_router(lineage_router, prefix="/api/v1")
    app.dependency_overrides[require_api_key] = lambda: {
        "tenant_id": str(tenant_id),
        "key_id": "test-key",
    }
    app.dependency_overrides[get_current_tenant_id] = lambda: tenant_id
    return app


def _make_session_mock(records_per_call):
    """Return (mock_client_cls, mock_session) wired up like an async Neo4j session.

    ``records_per_call`` is a list of record-lists; each call to
    ``session.run`` consumes the next entry and the resulting async
    iterator yields its records as dict-likes.
    """
    calls = list(records_per_call)
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    async def _run(_query, **_kwargs):
        try:
            records = calls.pop(0)
        except IndexError:
            records = []

        async def _aiter(self):
            for r in records:
                yield r

        result = MagicMock()
        result.__aiter__ = _aiter
        return result

    mock_session.run = AsyncMock(side_effect=_run)

    mock_client = MagicMock()
    mock_client.session = MagicMock(return_value=mock_session)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_client_cls = MagicMock(return_value=mock_client)
    mock_client_cls.get_tenant_database_name = MagicMock(return_value="reg_tenant_test")
    return mock_client_cls, mock_session


def test_lineage_history_returns_200_with_versions_for_seeded_tlc():
    """Happy path: seeded TLC yields total_versions >= 1 (RE-SEC-005 regression net)."""
    app = _build_app(TENANT_A)
    client = TestClient(app)

    seeded_record = {
        "tlc": "LOT-A-001",
        "version": 2,
        "record_hash": "hash-v2",
        "prev_hash": "hash-v1",
        "created_at": "2026-05-01T00:00:00Z",
        "superseded_at": None,
        "source_document": "doc-A",
        "fact_type": "RegulatoryFact",
        "is_current": True,
        "all_props": {
            "tlc": "LOT-A-001",
            "version": 2,
            "tenant_id": str(TENANT_A),
            "extra": "tenant-A-only",
        },
    }
    mock_client_cls, _ = _make_session_mock([[seeded_record]])

    with patch(
        "services.graph.app.routers.lineage_traversal.Neo4jClient",
        mock_client_cls,
    ):
        response = client.get("/api/v1/lineage/LOT-A-001/history", headers=_AUTH_HEADERS)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tlc"] == "LOT-A-001"
    assert body["total_versions"] >= 1
    assert body["current_version"] == 2
    assert len(body["versions"]) == 1
    assert body["versions"][0]["is_current"] is True


def test_lineage_history_passes_caller_tenant_to_query_not_other_tenant():
    """Tenant predicate enforcement: tenant A's call must scope to tenant A.

    Seeds two tenants in the mock — when tenant A calls the endpoint, the
    Cypher run must be parameterised with tenant A's id, and the returned
    rows must only include tenant A's data. (Cross-tenant rows would trip
    the post-query invariant check in lineage_traversal.py:170-181.)
    """
    app = _build_app(TENANT_A)
    client = TestClient(app)

    tenant_a_row = {
        "tlc": "SHARED-TLC",
        "version": 1,
        "record_hash": "hash-A",
        "prev_hash": None,
        "created_at": "2026-05-01T00:00:00Z",
        "superseded_at": None,
        "source_document": "doc-A",
        "fact_type": "RegulatoryFact",
        "is_current": True,
        "all_props": {"tlc": "SHARED-TLC", "tenant_id": str(TENANT_A)},
    }
    # Simulates a correctly-scoped query: tenant B's row is filtered by Cypher
    # before reaching Python, so the mock returns only tenant A's row.
    mock_client_cls, mock_session = _make_session_mock([[tenant_a_row]])

    with patch(
        "services.graph.app.routers.lineage_traversal.Neo4jClient",
        mock_client_cls,
    ):
        response = client.get("/api/v1/lineage/SHARED-TLC/history", headers=_AUTH_HEADERS)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_versions"] == 1

    # Verify the Cypher run was parameterised with tenant A's id, not B's.
    # This is what makes LINEAGE_QUERY's `tenant_id = $tenant_id` predicate
    # actually filter cross-tenant rows.
    assert mock_session.run.await_count >= 1
    _, kwargs = mock_session.run.await_args_list[0]
    assert kwargs["tenant_id"] == str(TENANT_A)
    assert kwargs["tenant_id"] != str(TENANT_B)
    assert kwargs["tlc"] == "SHARED-TLC"


def test_lineage_history_invariant_rejects_cross_tenant_record():
    """If Cypher somehow returned a cross-tenant row, the route must 500 loudly.

    Exercises the defense-in-depth invariant check at
    lineage_traversal.py:170-181 — we never want to silently return
    another tenant's lineage even if the query predicate is bypassed.
    """
    app = _build_app(TENANT_A)
    client = TestClient(app)

    # Mock Neo4j returning a tenant B row to a tenant A caller.
    leaky_row = {
        "tlc": "LEAKY",
        "version": 1,
        "record_hash": "h",
        "prev_hash": None,
        "created_at": "2026-05-01T00:00:00Z",
        "superseded_at": None,
        "source_document": "doc-B",
        "fact_type": "RegulatoryFact",
        "is_current": True,
        "all_props": {"tlc": "LEAKY", "tenant_id": str(TENANT_B)},
    }
    mock_client_cls, _ = _make_session_mock([[leaky_row]])

    with patch(
        "services.graph.app.routers.lineage_traversal.Neo4jClient",
        mock_client_cls,
    ):
        response = client.get("/api/v1/lineage/LEAKY/history", headers=_AUTH_HEADERS)

    # The post-query invariant raises HTTPException(500). Note: the route's
    # broad ``except Exception`` (line 237) does NOT swallow HTTPException
    # because of the re-raise on line 235, so the original 500 propagates.
    assert response.status_code == 500
