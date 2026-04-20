"""Regression tests for the compliance FDA spreadsheet route.

Covers:

* #1283 — date validation + Content-Disposition filename injection on
  ``/v1/fsma/audit/spreadsheet``.
* #1291 — zero-row exports no longer return a 200 with an empty
  "official" FSMA spreadsheet; they 404.
"""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

service_dir = Path(__file__).parent.parent
# Purge any lingering ``app`` module from another service's test run so
# the compliance service's ``app.routes`` resolves against this tree.
for key in list(sys.modules):
    if key == "app" or key.startswith("app.") or key == "main":
        del sys.modules[key]
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _fresh_routes():
    """Re-import ``app.routes`` on demand.

    Sibling compliance tests (``test_fda_spreadsheet.py``) purge
    ``sys.modules['app.*']`` at import time. When those tests are
    collected before ours, a stale reference to the old ``app.routes``
    module gets bound to this module's imports. Calling this helper at
    fixture setup time guarantees we always work with whichever
    ``app.routes`` is current in sys.modules.
    """
    if "app.routes" in sys.modules:
        return sys.modules["app.routes"]
    return importlib.import_module("app.routes")


@pytest.fixture()
def client(monkeypatch):
    """Return a TestClient with auth bypassed and a fresh router.

    The override returns a stub principal with a ``tenant_id``
    attribute so routes that bind tenant from the authenticated
    principal (e.g. /v1/fsma/audit/spreadsheet, #1106) can read it.
    """
    from shared.auth import require_api_key

    class _StubPrincipal:
        tenant_id = "11111111-1111-1111-1111-111111111111"
        key_id = "test-key"

    routes_mod = _fresh_routes()
    app = FastAPI()
    app.include_router(routes_mod.router)
    app.dependency_overrides[require_api_key] = lambda: _StubPrincipal()

    with TestClient(app) as c:
        # Stash the module handle so tests can patch against the
        # exact same object that the router is dispatching to.
        c._compliance_routes_mod = routes_mod  # type: ignore[attr-defined]
        yield c


def _mock_graph_response(events: list[dict]):
    """Single-page graph response (``has_more=False``).

    The handler drives a cursor-pagination loop even for small result
    sets, so the stub must always return a terminator payload.
    """
    class _Resp:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload
            self.text = "ok"

        def json(self):
            return self._payload

    resp = _Resp({"events": events, "has_more": False, "next_cursor": None})

    class _Ctx:
        async def __aenter__(self_inner):
            client = AsyncMock()
            client.get = AsyncMock(return_value=resp)
            return client

        async def __aexit__(self_inner, *args):
            return None

    return _Ctx()


def _mock_paginated_graph_response(pages: list[dict]):
    """Multi-page graph response. ``pages`` is a list of ``{"events":
    [...], "has_more": bool, "next_cursor": str|None}`` dicts that
    will be returned in order on successive ``client.get`` calls.
    """
    class _Resp:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload
            self.text = "ok"

        def json(self):
            return self._payload

    responses = [_Resp(p) for p in pages]
    response_iter = iter(responses)

    async def _get(*args, **kwargs):
        return next(response_iter)

    class _Ctx:
        async def __aenter__(self_inner):
            client = AsyncMock()
            client.get = _get
            return client

        async def __aexit__(self_inner, *args):
            return None

    return _Ctx()


def _patch_graph(client: TestClient, events: list[dict]):
    """Patch the same ``resilient_client`` attribute that the fixture's
    router module is currently using.
    """
    return patch.object(
        client._compliance_routes_mod,  # type: ignore[attr-defined]
        "resilient_client",
        return_value=_mock_graph_response(events),
    )


def _patch_graph_paginated(client: TestClient, pages: list[dict]):
    return patch.object(
        client._compliance_routes_mod,  # type: ignore[attr-defined]
        "resilient_client",
        return_value=_mock_paginated_graph_response(pages),
    )


# ---------------------------------------------------------------------------
# #1283 — date validation
# ---------------------------------------------------------------------------


def test_1283_rejects_malformed_start_date(client):
    r = client.get(
        "/v1/fsma/audit/spreadsheet",
        params={"start_date": "2026-13-99", "end_date": "2026-04-17"},
    )
    assert r.status_code == 400
    assert "ISO-8601" in r.json()["detail"]


def test_1283_rejects_malformed_end_date(client):
    r = client.get(
        "/v1/fsma/audit/spreadsheet",
        params={"start_date": "2026-04-01", "end_date": "2026-99-99"},
    )
    assert r.status_code == 400
    assert "ISO-8601" in r.json()["detail"]


def test_1283_rejects_inverted_range(client):
    r = client.get(
        "/v1/fsma/audit/spreadsheet",
        params={"start_date": "2026-04-17", "end_date": "2026-04-01"},
    )
    assert r.status_code == 400
    assert "on or after" in r.json()["detail"]


def test_1283_rejects_excessive_range(client):
    """EPIC-L (#1655) caps a synchronous export at 90 days; 10 years
    is not a legit query for the interactive spreadsheet endpoint."""
    r = client.get(
        "/v1/fsma/audit/spreadsheet",
        params={"start_date": "2016-01-01", "end_date": "2026-01-01"},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "exceeds" in detail and "90-day" in detail


def test_1283_rejects_requesting_entity_with_formula_prefix(client):
    r = client.get(
        "/v1/fsma/audit/spreadsheet",
        params={
            "start_date": "2026-04-01",
            "end_date": "2026-04-17",
            "requesting_entity": "=WEBSERVICE(\"http://evil\")",
        },
    )
    assert r.status_code == 400
    assert "requesting_entity" in r.json()["detail"]


def test_1283_rejects_requesting_entity_with_crlf(client):
    """A payload with embedded CRLF would otherwise split the header."""
    r = client.get(
        "/v1/fsma/audit/spreadsheet",
        params={
            "start_date": "2026-04-01",
            "end_date": "2026-04-17",
            "requesting_entity": "Evil\r\nX-Injected: yes",
        },
    )
    assert r.status_code == 400


def test_1283_content_disposition_uses_parsed_dates(client):
    """Even if the query strings include crazy characters, the
    Content-Disposition filename is built from parsed ``date`` objects
    and a sanitized TLC token — no raw user input.
    """
    events = [
        {
            "type": "SHIPPING",
            "tlc": "TLC-001",
            "product_description": "Romaine",
            "quantity": 100,
            "uom": "cases",
            "kdes": {"event_date": "2026-04-10T10:00:00+00:00"},
        }
    ]
    with _patch_graph(client, events):
        r = client.get(
            "/v1/fsma/audit/spreadsheet",
            params={
                "start_date": "2026-04-01",
                "end_date": "2026-04-17",
                "tlc": "../../etc/passwd",
            },
        )
    assert r.status_code == 200
    disp = r.headers["Content-Disposition"]
    # EPIC-L (#1655) stitched via shared.fda_export.safe_filename:
    # prefix → scope → start → end → .csv.
    assert disp.startswith('attachment; filename="fsma_204_audit_')
    assert "2026-04-01" in disp and "2026-04-17" in disp
    assert disp.endswith('.csv"')
    # Path traversal and separator injection must not survive the
    # token sanitizer.
    assert ".." not in disp
    assert "/" not in disp.split("filename=", 1)[1]


# ---------------------------------------------------------------------------
# #1291 — zero-row exports 404 instead of 200 + empty cover block
# ---------------------------------------------------------------------------


def test_1291_zero_events_returns_404(client):
    with _patch_graph(client, []):
        r = client.get(
            "/v1/fsma/audit/spreadsheet",
            params={"start_date": "2026-04-01", "end_date": "2026-04-17"},
        )
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert "No FSMA 204 events" in detail
    # No Content-Disposition / CSV body should be returned.
    assert "Content-Disposition" not in r.headers
    assert r.headers["content-type"].startswith("application/json")


def test_1291_zero_events_still_records_empty_audit_line(client, caplog):
    caplog.set_level(logging.INFO, logger="compliance-audit")
    with _patch_graph(client, []):
        r = client.get(
            "/v1/fsma/audit/spreadsheet",
            params={"start_date": "2026-04-01", "end_date": "2026-04-17"},
        )
    assert r.status_code == 404
    # An ``fda_export_empty`` audit line must have been emitted so a
    # spike in zero-result queries is observable.
    empties = [
        r for r in caplog.records
        if r.name == "compliance-audit" and r.msg == "fda_export_empty"
    ]
    assert empties


# ---------------------------------------------------------------------------
# #1108 — malformed event_date in graph response must 400, not truncate
# ---------------------------------------------------------------------------


def test_1108_malformed_event_date_in_graph_response_returns_400(client):
    """When the graph service returns an event with a non-ISO-8601
    ``event_date``, the handler must 400 rather than emit an FDA
    submission with a truncated 8-char string in the date column.
    """
    bad_events = [
        {
            "type": "SHIPPING",
            "tlc": "TLC-001",
            "product_description": "Romaine",
            "quantity": 100,
            "uom": "cases",
            "kdes": {"event_date": "yesterday"},  # unparseable
        }
    ]
    with _patch_graph(client, bad_events):
        r = client.get(
            "/v1/fsma/audit/spreadsheet",
            params={"start_date": "2026-04-01", "end_date": "2026-04-17"},
        )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "malformed event_date" in detail or "event_date" in detail


# ---------------------------------------------------------------------------
# #1038 — cursor pagination replaces single-page truncation
# ---------------------------------------------------------------------------


def _make_event(i: int) -> dict:
    return {
        "type": "SHIPPING",
        "tlc": f"TLC-{i:04d}",
        "product_description": "Romaine",
        "quantity": 100,
        "uom": "cases",
        "kdes": {"event_date": f"2026-04-{(i % 28) + 1:02d}T10:00:00+00:00"},
    }


def test_1038_walks_all_pages_until_has_more_false(client):
    """A 2-page result set must be fully consumed; the CSV contains
    every row, not just the first page.
    """
    page_1 = [_make_event(i) for i in range(500)]
    page_2 = [_make_event(i + 500) for i in range(123)]
    pages = [
        {"events": page_1, "has_more": True, "next_cursor": "cursor-abc"},
        {"events": page_2, "has_more": False, "next_cursor": None},
    ]
    with _patch_graph_paginated(client, pages):
        r = client.get(
            "/v1/fsma/audit/spreadsheet",
            params={"start_date": "2026-04-01", "end_date": "2026-04-17"},
        )
    assert r.status_code == 200
    # Record Count metadata row appears in the CSV cover block.
    body = r.text
    assert "Record Count" in body
    # All 623 events should be represented. Count the data-row TLCs
    # (the TLCs are unique per event).
    data_rows = [line for line in body.splitlines() if "TLC-" in line]
    assert len(data_rows) == 623, f"expected 623 data rows, got {len(data_rows)}"


def test_1038_exceeding_hard_cap_returns_413(client):
    """When accumulated events exceed ``_MAX_EXPORT_EVENTS``, the
    handler must 413 (Payload Too Large) rather than silently
    producing a partial CSV.
    """
    # Build 101 pages of 500 → 50,500 events, just over the default cap.
    pages = []
    for i in range(101):
        pages.append(
            {
                "events": [_make_event(i * 500 + j) for j in range(500)],
                "has_more": i < 100,
                "next_cursor": f"cursor-{i}" if i < 100 else None,
            }
        )
    with _patch_graph_paginated(client, pages):
        r = client.get(
            "/v1/fsma/audit/spreadsheet",
            params={"start_date": "2026-04-01", "end_date": "2026-04-17"},
        )
    assert r.status_code == 413
    assert "hard cap" in r.json()["detail"] or "narrow" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Positive case: valid inputs still produce a CSV
# ---------------------------------------------------------------------------


def test_valid_request_returns_csv(client):
    events = [
        {
            "type": "SHIPPING",
            "tlc": "TLC-001",
            "product_description": "Romaine",
            "quantity": 100,
            "uom": "cases",
            "kdes": {"event_date": "2026-04-10T10:00:00+00:00"},
        }
    ]
    with _patch_graph(client, events):
        r = client.get(
            "/v1/fsma/audit/spreadsheet",
            params={
                "start_date": "2026-04-01",
                "end_date": "2026-04-17",
                "requesting_entity": "FDA District Office",
            },
        )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "TLC-001" in r.text
