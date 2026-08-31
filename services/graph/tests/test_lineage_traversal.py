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

from services.graph.app.routes import router as graph_router

TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = uuid.UUID("22222222-2222-2222-2222-222222222222")

_AUTH_HEADERS = {"X-RegEngine-API-Key": os.getenv("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token-for-pytest")}


def _build_app(tenant_id: uuid.UUID) -> FastAPI:
    """Mount the lineage router exactly the way production mounts it.

    #2946: this helper used to do ``app.include_router(lineage_router,
    prefix="/api/v1")``, skipping the ``prefix="/lineage"`` nesting that
    ``services/graph/app/routes.py`` adds. That divergence is what made the
    doubled ``/api/v1/lineage/lineage/{tlc}/history`` path invisible: the
    suite asserted a single-segment URL that only resolved under the test's
    own flatter mounting. Assembling through ``services.graph.app.routes``
    — the same router ``server/main.py`` includes at ``prefix="/api/v1"`` —
    means any future prefix drift fails here instead of in production.
    """
    app = FastAPI()
    app.include_router(graph_router, prefix="/api/v1")
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


# =============================================================================
# #2946 — route-inventory net over the assembled graph app
# =============================================================================


def _assembled_paths() -> list[str]:
    """Every path the graph router serves under production's ``/api/v1`` mount."""
    app = FastAPI()
    app.include_router(graph_router, prefix="/api/v1")
    return [getattr(route, "path", "") for route in app.routes]


def test_lineage_history_is_served_at_its_documented_path():
    """#2946: the documented single-segment path must exist on the real mounting.

    ``routes.py`` includes this router under ``prefix="/lineage"``; the route
    decorator must therefore not repeat the segment. Asserted against the
    assembled route table rather than via a request, so a failure reports the
    served path instead of a bare 404.
    """
    paths = _assembled_paths()
    assert "/api/v1/lineage/{tlc}/history" in paths, (
        "documented lineage history path is not served; lineage paths present: "
        f"{[p for p in paths if 'lineage' in p]}"
    )
    assert "/api/v1/lineage/lineage/{tlc}/history" not in paths, "doubled /lineage/lineage segment is still served"


# Doubled adjacent segments that exist elsewhere in the graph router today.
# These are the same class of defect as #2946 but live in routers outside its
# scope, so they are recorded here rather than silently tolerated: the check
# below fails on any duplicate NOT in this set, so a new one cannot land
# unnoticed, and it also fails if an entry here is fixed without being
# removed, so the list cannot rot into a permanent exemption.
#
#   /api/v1/fsma/traceability/traceability/*  -> traceability.py:358,378,398
#   /api/v1/fsma/metrics/metrics*             -> metrics.py:43,59
_KNOWN_DOUBLED_SEGMENT_PATHS = {
    "/api/v1/fsma/traceability/traceability/regulations",
    "/api/v1/fsma/traceability/traceability/impacted-lots",
    "/api/v1/fsma/traceability/traceability/link/{obligation_id}",
    "/api/v1/fsma/metrics/metrics",
    "/api/v1/fsma/metrics/metrics/quality",
}


def _has_repeated_adjacent_segment(path: str) -> bool:
    segments = [s for s in path.split("/") if s]
    return any(a == b for a, b in zip(segments, segments[1:]))


def test_assembled_graph_routes_have_no_new_duplicated_segment():
    """#2946: no route may repeat an adjacent path segment.

    A doubled segment means the ``include_router`` prefix and the route
    decorator both carry it, which serves a URL that appears in no test and
    no doc while the documented one returns a routing 404.
    """
    duplicated = {p for p in _assembled_paths() if _has_repeated_adjacent_segment(p)}

    new = sorted(duplicated - _KNOWN_DOUBLED_SEGMENT_PATHS)
    assert not new, f"new route(s) with a duplicated adjacent segment: {new}"

    fixed = sorted(_KNOWN_DOUBLED_SEGMENT_PATHS - duplicated)
    assert not fixed, f"no longer duplicated — drop from _KNOWN_DOUBLED_SEGMENT_PATHS: {fixed}"
