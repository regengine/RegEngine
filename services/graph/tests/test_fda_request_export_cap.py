"""The FDA and EPCIS range exports must not silently stop at the search page size.

``query_events_by_range`` defaults to 500 rows and clamps search callers at
1,000. The spreadsheet and EPCIS handlers used that default and returned
HTTP 200, so the 501st event in the window was omitted from a file that
looked complete. They now request one row past the hard cap and answer 413
when the window does not fit.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

from shared.auth import APIKey, require_api_key  # noqa: E402
from shared.middleware import get_current_tenant_id  # noqa: E402

from services.graph.app.fsma.queries import (  # noqa: E402
    EXPORT_EVENT_CAP,
    SEARCH_LIMIT_CEILING,
    query_events_by_range,
)
from services.graph.tests.test_fda_request_export_header import _build_app, _neo4j_stub  # noqa: E402

FDA_URL = "/v1/fsma/compliance/export/fda-request"
EPCIS_URL = "/v1/fsma/compliance/export/epcis"
DATES = {"start_date": "2026-01-01", "end_date": "2026-12-31"}


@pytest.fixture(autouse=True)
def _clean_slowapi_bucket():
    from shared.rate_limit import limiter

    reset = getattr(limiter._storage, "reset", None)
    if callable(reset):
        reset()
    yield
    reset = getattr(limiter._storage, "reset", None)
    if callable(reset):
        reset()


def _client_with_session():
    session = MagicMock()
    result = MagicMock()
    result.__aiter__.return_value = iter(())
    session.run = AsyncMock(return_value=result)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    client = MagicMock()
    client.session.return_value = ctx
    return client, session


def _call(url: str, events: list, params: dict | None = None):
    query = AsyncMock(return_value=events)
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
        patch("services.graph.app.routers.fsma.compliance.query_events_by_range", new=query),
    ):
        resp = client.get(url, params=params or DATES)
    return resp, query


@pytest.mark.asyncio
async def test_search_limit_stays_clamped_when_a_caller_asks_for_the_export_cap():
    client, session = _client_with_session()
    await query_events_by_range(
        client,
        DATES["start_date"],
        DATES["end_date"],
        str(uuid.uuid4()),
        limit=EXPORT_EVENT_CAP + 1,
    )
    assert session.run.await_args.kwargs["limit"] == SEARCH_LIMIT_CEILING


@pytest.mark.asyncio
async def test_export_cap_requests_one_past_the_hard_cap():
    client, session = _client_with_session()
    await query_events_by_range(
        client,
        DATES["start_date"],
        DATES["end_date"],
        str(uuid.uuid4()),
        limit=EXPORT_EVENT_CAP + 1,
        export_cap=True,
    )
    assert session.run.await_args.kwargs["limit"] == EXPORT_EVENT_CAP + 1


def test_fda_export_of_a_full_window_is_not_the_search_page():
    resp, query = _call(FDA_URL, [{}])
    assert resp.status_code == 200, resp.text
    assert query.await_args.kwargs["limit"] == EXPORT_EVENT_CAP + 1
    assert query.await_args.kwargs["export_cap"] is True


def test_fda_export_over_the_cap_is_413_not_a_partial_csv():
    resp, _query = _call(FDA_URL, [{}] * (EXPORT_EVENT_CAP + 1))
    assert resp.status_code == 413, resp.text
    assert "hard cap" in resp.json()["detail"]
    assert b"Traceability Lot Code" not in resp.content


def test_epcis_export_over_the_cap_is_413():
    resp, query = _call(EPCIS_URL, [{}] * (EXPORT_EVENT_CAP + 1))
    assert resp.status_code == 413, resp.text
    assert query.await_args.kwargs["export_cap"] is True
    assert b"EPCISDocument" not in resp.content


def _call_with_cap(url: str, events: list, cap: int, params: dict | None = None):
    """Exercise the export routes against a monkeypatched hard cap.

    Prefer a small ``cap`` over building tens of thousands of fixture rows:
    the refusal is ``len(events) > EXPORT_EVENT_CAP``, so the exact and
    exact-plus-one boundaries are the same at any positive ceiling.
    """
    query = AsyncMock(return_value=events)
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
        patch("services.graph.app.routers.fsma.compliance.EXPORT_EVENT_CAP", cap),
        patch("services.graph.app.routers.fsma.compliance.Neo4jClient", _neo4j_stub()),
        patch("services.graph.app.routers.fsma.compliance.query_events_by_range", new=query),
    ):
        resp = client.get(url, params=params or DATES)
    return resp, query


def test_fda_export_at_exact_cap_succeeds():
    """Exactly EXPORT_EVENT_CAP rows must download (strict > refuses only past the cap)."""
    cap = 3
    resp, query = _call_with_cap(FDA_URL, [{}] * cap, cap)
    assert resp.status_code == 200, resp.text
    assert b"Traceability Lot Code" in resp.content
    assert query.await_args.kwargs["limit"] == cap + 1
    assert query.await_args.kwargs["export_cap"] is True


def test_fda_export_one_past_exact_cap_is_413():
    cap = 3
    resp, query = _call_with_cap(FDA_URL, [{}] * (cap + 1), cap)
    assert resp.status_code == 413, resp.text
    assert "hard cap" in resp.json()["detail"]
    assert b"Traceability Lot Code" not in resp.content
    assert query.await_args.kwargs["limit"] == cap + 1


def test_epcis_export_at_exact_cap_succeeds():
    """Exactly EXPORT_EVENT_CAP rows must download for EPCIS too."""
    cap = 3
    resp, query = _call_with_cap(EPCIS_URL, [{}] * cap, cap)
    assert resp.status_code == 200, resp.text
    assert b"EPCISDocument" in resp.content
    assert b"epcisBody" in resp.content
    assert query.await_args.kwargs["limit"] == cap + 1
    assert query.await_args.kwargs["export_cap"] is True


def test_epcis_export_one_past_exact_cap_is_413():
    cap = 3
    resp, query = _call_with_cap(EPCIS_URL, [{}] * (cap + 1), cap)
    assert resp.status_code == 413, resp.text
    assert "hard cap" in resp.json()["detail"]
    assert b"epcisBody" not in resp.content
    assert query.await_args.kwargs["limit"] == cap + 1
