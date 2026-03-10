import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.graph.app.routers.fsma.traceability import router as traceability_router
from shared.auth import require_api_key
from shared.middleware import get_current_tenant_id


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(traceability_router, prefix="/v1/fsma/traceability")
    app.dependency_overrides[require_api_key] = lambda: {
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "key_id": "test-key",
    }
    app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID(
        "11111111-1111-1111-1111-111111111111"
    )
    return app


def test_search_events_with_filters_and_cursor_pagination():
    app = _build_app()
    client = TestClient(app)

    mocked_events = [
        {"event_id": "evt-1", "type": "RECEIVING"},
        {"event_id": "evt-2", "type": "RECEIVING"},
        {"event_id": "evt-3", "type": "RECEIVING"},
    ]

    with patch("services.graph.app.routers.fsma.traceability.Neo4jClient") as mock_client_cls, patch(
        "services.graph.app.routers.fsma.traceability.query_events_by_range",
        new_callable=AsyncMock,
    ) as mock_query:
        mock_client = MagicMock()
        mock_client.close = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client_cls.get_tenant_database_name.return_value = "test-db"
        mock_query.return_value = mocked_events

        response = client.get(
            (
                "/v1/fsma/traceability/search/events?"
                "start_date=2026-02-01&end_date=2026-03-10&"
                "product_contains=lettuce&facility_contains=Supplier%20X&"
                "cte_type=receiving&limit=2"
            ),
            headers={"X-RegEngine-API-Key": "test-key"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["has_more"] is True
    assert body["next_cursor"] == "evt-2"
    assert len(body["events"]) == 2
    assert body["filters"]["cte_type"] == "RECEIVING"

    _, kwargs = mock_query.await_args
    assert kwargs["product_contains"] == "lettuce"
    assert kwargs["facility_contains"] == "Supplier X"
    assert kwargs["cte_type"] == "RECEIVING"
    assert kwargs["limit"] == 3
