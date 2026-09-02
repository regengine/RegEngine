"""Streaming state must survive route materialization (#3036 follow-up).

``include_owned_router`` flattens fastapi's lazy ``_IncludedRouter``
entries into per-app ``APIRoute`` copies. The copy passes the original
route's *resolved* ``response_model`` (``None`` for streaming generator
endpoints), which short-circuits ``stream_item_type`` derivation inside
``APIRoute.__init__`` — so without the explicit restore in
``_materialized_api_route`` a JSONL/SSE streaming route would silently
lose stream-item validation and OpenAPI schema after inclusion.

No production route streams today; this guards the materializer's
faithfulness for the first one that does.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from pydantic import BaseModel

from server.route_ownership import include_owned_router


class _StreamItem(BaseModel):
    value: int


def _streaming_app() -> FastAPI:
    router = APIRouter()

    @router.get("/stream")
    async def stream_items() -> AsyncIterator[_StreamItem]:
        yield _StreamItem(value=1)

    app = FastAPI()
    include_owned_router(app, router, owner="test", prefix="/api")
    return app


def _get_route(app: FastAPI, path: str) -> APIRoute:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path:
            return route
    raise AssertionError(f"no APIRoute at {path}")


def test_materialized_route_keeps_stream_item_state():
    app = _streaming_app()
    route = _get_route(app, "/api/stream")

    assert route.stream_item_type is _StreamItem, (
        "materialized copy lost stream_item_type — JSONL/SSE item validation and schema silently disabled"
    )
    assert route.stream_item_field is not None
    assert route.is_json_stream is True


def test_materialized_streaming_route_still_streams():
    from fastapi.testclient import TestClient

    app = _streaming_app()
    with TestClient(app) as client:
        response = client.get("/api/stream")
    assert response.status_code == 200
    assert '"value":1' in response.text.replace(" ", "")
