from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.nlp.app.routes import router
from shared.auth import APIKey, require_api_key


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
