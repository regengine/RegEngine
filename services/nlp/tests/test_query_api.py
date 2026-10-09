from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared.auth import APIKey, require_api_key

from services.nlp.app.routes import router


def _api_key(scopes: list[str]) -> APIKey:
    return APIKey(
        key_id="rge_test",
        key_hash="",
        name="test-key",
        tenant_id="11111111-1111-1111-1111-111111111111",
        created_at=datetime.now(timezone.utc),
        rate_limit_per_minute=120,
        scopes=scopes,
    )


def _build_app(scopes: list[str]) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[require_api_key] = lambda: _api_key(scopes)
    return app


def test_query_api_enforces_graph_query_scope():
    app = _build_app(scopes=["fda.read"])
    client = TestClient(app)

    response = client.post(
        "/api/v1/query/traceability",
        json={"query": "show me all lettuce from Supplier X in the last 30 days"},
        headers={"X-RegEngine-API-Key": "rge_test.secret"},
    )

    assert response.status_code == 403
    assert "graph.query" in response.json()["detail"]


def test_query_api_events_search_contract():
    app = _build_app(scopes=["graph.query"])
    client = TestClient(app)

    graph_payload = {
        "count": 1,
        "events": [
            {
                "event_id": "evt-1",
                "type": "RECEIVING",
                "event_date": "2026-03-01",
                "tlc": "LOT-2026-001",
            }
        ],
        "next_cursor": None,
    }

    with patch("services.nlp.app.routes._graph_get", new_callable=AsyncMock) as mock_graph:
        with patch("services.nlp.app.routes.emit_funnel_event") as mock_emit:
            mock_graph.return_value = graph_payload

            response = client.post(
                "/api/v1/query/traceability",
                json={
                    "query": "show me all lettuce from Supplier X in the last 30 days",
                    "limit": 25,
                },
                headers={"X-RegEngine-API-Key": "rge_test.secret"},
            )
            mock_emit.assert_called_once()
            kwargs = mock_emit.call_args.kwargs
            assert kwargs["tenant_id"] == "11111111-1111-1111-1111-111111111111"
            assert kwargs["event_name"] == "first_nlp_query"

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "events_search"
    assert body["results"][0]["event_id"] == "evt-1"
    assert body["evidence"][0]["endpoint"] == "/api/v1/fsma/traceability/search/events"
    assert body["filters"]["limit"] == 25


def test_query_api_rejects_query_string_tenant_id_override():
    """EPIC-A #1651: query-string ?tenant_id=other must not override the
    authenticated principal's tenant. resolve_tenant_context raises 409
    E_TENANT_MISMATCH when the request claims a different tenant.
    """
    app = _build_app(scopes=["graph.query"])
    client = TestClient(app)

    other_tenant = "22222222-2222-2222-2222-222222222222"

    with patch("services.nlp.app.routes._graph_get", new_callable=AsyncMock):
        response = client.post(
            "/api/v1/query/traceability",
            params={"tenant_id": other_tenant},
            json={"query": "show me all lettuce from Supplier X in the last 30 days"},
            headers={"X-RegEngine-API-Key": "rge_test.secret"},
        )

    assert response.status_code == 409
    body = response.json()
    detail = body.get("detail")
    assert isinstance(detail, dict) and detail.get("code") == "E_TENANT_MISMATCH"


def test_query_api_rejects_x_tenant_id_override_header_mismatch():
    """EPIC-A #1651: a conflicting X-Tenant-ID-Override header must produce
    a 409 E_TENANT_MISMATCH, not a silent override.

    resolve_tenant_context() inspects three caller-supplied surfaces for
    competing tenant claims: path params, query string, and the
    ``x-tenant-id-override`` header. This test exercises the header surface
    so all three claim-channels are covered (the query-string channel is
    covered by ``test_query_api_rejects_query_string_tenant_id_override``).
    """
    app = _build_app(scopes=["graph.query"])
    client = TestClient(app)

    other_tenant = "33333333-3333-3333-3333-333333333333"

    with patch("services.nlp.app.routes._graph_get", new_callable=AsyncMock):
        response = client.post(
            "/api/v1/query/traceability",
            json={"query": "show me all lettuce from Supplier X in the last 30 days"},
            headers={
                "X-RegEngine-API-Key": "rge_test.secret",
                # The mismatch detector reads x-tenant-id-override (lower-case
                # via Starlette's case-insensitive header map).
                "X-Tenant-ID-Override": other_tenant,
            },
        )

    assert response.status_code == 409
    body = response.json()
    detail = body.get("detail")
    assert isinstance(detail, dict) and detail.get("code") == "E_TENANT_MISMATCH"


def test_query_api_funnel_emit_failure_does_not_break_query():
    """Query-path telemetry is best-effort: if the funnel hook raises, the
    query must still return 200 with the normal response body."""
    from services.nlp.app.routes import limiter

    # The endpoint allows 5 requests/minute on shared in-memory storage;
    # reset the budget so this test is independent of sibling tests.
    limiter.reset()
    app = _build_app(scopes=["graph.query"])
    client = TestClient(app, raise_server_exceptions=False)

    graph_payload = {"count": 0, "events": [], "next_cursor": None}

    with patch("services.nlp.app.routes._graph_get", new_callable=AsyncMock) as mock_graph:
        with patch(
            "services.nlp.app.routes.emit_funnel_event",
            side_effect=RuntimeError("funnel db down"),
        ):
            mock_graph.return_value = graph_payload

            response = client.post(
                "/api/v1/query/traceability",
                json={"query": "show me all lettuce from Supplier X in the last 30 days"},
                headers={"X-RegEngine-API-Key": "rge_test.secret"},
            )

    assert response.status_code == 200
    assert response.json()["results"] == []


def test_query_api_trace_backward_route_selection():
    app = _build_app(scopes=["graph.query"])
    client = TestClient(app)

    graph_payload = {
        "lot_id": "LOT-2026-010",
        "facilities": [{"name": "Supplier X"}],
        "source_lots": [{"tlc": "RAW-2026-001"}],
    }

    with patch("services.nlp.app.routes._graph_get", new_callable=AsyncMock) as mock_graph:
        mock_graph.return_value = graph_payload

        response = client.post(
            "/api/v1/query/traceability",
            json={"query": "trace back lot LOT-2026-010 to source supplier"},
            headers={"X-RegEngine-API-Key": "rge_test.secret"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "trace_backward"
    assert "LOT-2026-010" in body["answer"]
    assert body["evidence"][0]["endpoint"].endswith("/trace/backward/LOT-2026-010")
