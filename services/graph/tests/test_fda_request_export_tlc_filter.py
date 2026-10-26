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
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

from services.graph.app.fsma.queries import query_events_by_range  # noqa: E402
from services.graph.tests.test_fda_request_export_header import TENANT, _build_app, _neo4j_stub  # noqa: E402

URL = "/v1/fsma/compliance/export/fda-request"
DATES = {"start_date": "2026-01-01", "end_date": "2026-12-31"}


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
    client = TestClient(_build_app(), raise_server_exceptions=False)
    with (
        patch("services.graph.app.routers.fsma.compliance.Neo4jClient", _neo4j_stub()),
        patch("services.graph.app.fsma_utils.query_events_by_range", new=query),
    ):
        resp = client.get(URL, params=params)
    return resp, query


def test_route_forwards_exact_tlc_to_query():
    tlc = " Lot-ABC-001 "
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
    await query_events_by_range(client, "2026-01-01", "2026-12-31", TENANT, tlc="LOT-ABC-001")
    args = session.run.await_args
    assert "l.tlc = $tlc" in args.args[0]
    assert args.kwargs["tlc"] == "LOT-ABC-001"


@pytest.mark.asyncio
async def test_query_without_tlc_binds_null():
    client, session = _client_with_session()
    await query_events_by_range(client, "2026-01-01", "2026-12-31", TENANT)
    assert session.run.await_args.kwargs["tlc"] is None
