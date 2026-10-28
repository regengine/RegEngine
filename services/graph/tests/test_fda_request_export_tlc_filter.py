"""Regression tests: the FDA-request export honours an exact ``tlc`` filter.

``RegEngineClient.export_fda`` (``regengine/client.py``) sends ``tlc`` to
``GET /v1/fsma/compliance/export/fda-request``. The route used to accept only
``start_date`` and ``end_date`` and called ``query_events_by_range`` without a
lot, so the CSV held every tenant event in the date range, other lots
included. The route now forwards ``tlc`` unchanged and the query filters on
``l.tlc = $tlc`` as a bound parameter.
"""

from __future__ import annotations

import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

from datetime import datetime, timezone  # noqa: E402

from shared.auth import APIKey, require_api_key  # noqa: E402
from shared.middleware import get_current_tenant_id  # noqa: E402

from services.graph.app.fsma.queries import query_events_by_range  # noqa: E402
from services.graph.tests.test_fda_request_export_header import _build_app, _neo4j_stub  # noqa: E402

URL = "/v1/fsma/compliance/export/fda-request"
_TODAY = date.today()
START_DATE = (_TODAY - timedelta(days=30)).isoformat()
END_DATE = _TODAY.isoformat()
DATES = {"start_date": START_DATE, "end_date": END_DATE}


def _lot_code() -> str:
    """A lot code made at runtime, mixed case so case handling is visible."""
    return f"Lot-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _clean_slowapi_bucket():
    """Keep this file's GETs out of the shared 10/min export quota."""
    from shared.rate_limit import limiter

    reset = getattr(limiter._storage, "reset", None)
    if callable(reset):
        reset()
    yield
    reset = getattr(limiter._storage, "reset", None)
    if callable(reset):
        reset()


def _call_route(params):
    query = AsyncMock(return_value=[])
    tenant = uuid.uuid4()
    app = _build_app()
    app.dependency_overrides[require_api_key] = lambda: APIKey(
        key_id="preshared-master",
        key_hash="",
        name="test",
        tenant_id=str(tenant),
        created_at=datetime.now(timezone.utc),
    )
    app.dependency_overrides[get_current_tenant_id] = lambda: tenant
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("services.graph.app.routers.fsma.compliance.Neo4jClient", _neo4j_stub()),
        patch("services.graph.app.fsma_utils.query_events_by_range", new=query),
    ):
        resp = client.get(URL, params=params)
    return resp, query


def test_route_forwards_exact_tlc_to_query():
    tlc = f" {_lot_code()} "
    resp, query = _call_route({**DATES, "tlc": tlc})
    assert resp.status_code == 200, resp.text
    assert query.await_args.kwargs["tlc"] == tlc


def test_route_without_tlc_keeps_date_range_export():
    resp, query = _call_route(DATES)
    assert resp.status_code == 200, resp.text
    assert query.await_args.kwargs["tlc"] is None


def test_route_rejects_empty_tlc():
    resp, _ = _call_route({**DATES, "tlc": ""})
    assert resp.status_code == 422


def _client_with_session():
    session = MagicMock()
    result = MagicMock()
    result.__aiter__.return_value = iter([])
    session.run = AsyncMock(return_value=result)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    client = MagicMock()
    client.session.return_value = ctx
    return client, session


@pytest.mark.asyncio
async def test_query_binds_tlc_as_exact_lot_filter():
    client, session = _client_with_session()
    lot = _lot_code()
    upper = lot.upper()
    assert upper != lot
    await query_events_by_range(client, START_DATE, END_DATE, str(uuid.uuid4()), tlc=upper)
    args = session.run.await_args
    assert "l.tlc = $tlc" in args.args[0]
    assert args.kwargs["tlc"] == upper
    assert args.kwargs["tlc"] != lot


@pytest.mark.asyncio
async def test_query_without_tlc_binds_null():
    client, session = _client_with_session()
    await query_events_by_range(client, START_DATE, END_DATE, str(uuid.uuid4()))
    assert session.run.await_args.kwargs["tlc"] is None
