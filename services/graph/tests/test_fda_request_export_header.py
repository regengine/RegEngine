"""Header + CTE-column regression tests for the graph FDA-request export.

``GET /v1/fsma/compliance/export/fda-request``
(``services/graph/app/routers/fsma/compliance.py``) emits an 11-column FDA
sortable spreadsheet. Column index 1 used to be headed "Traceability Lot
Code Description" — a header FSMA 204 defines no KDE for — and its cell was
a hardcoded empty string, so the sheet carried a permanently blank,
mislabeled column and no event-type column at all.

It is now headed "Event Type (CTE)" and populated from the event's ``type``
(returned by ``query_events_by_range`` in
``services/graph/app/fsma/queries.py``).

The header is asserted as a *literal list* on purpose: a future cross-repo
column-shape change must pass through code review rather than being
absorbed silently.
"""

from __future__ import annotations

import csv
import io
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

from shared.auth import APIKey, require_api_key  # noqa: E402
from shared.middleware import get_current_tenant_id  # noqa: E402

TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

EXPECTED_HEADER = [
    "Traceability Lot Code",
    "Event Type (CTE)",
    "Product Description",
    "Quantity",
    "Unit of Measure",
    "Location Description",
    "Location Identifier (GLN)",
    "Date",
    "Time",
    "Reference Document Type",
    "Reference Document Number",
]

FABRICATED_EVENT = {
    "event_id": "evt-1",
    "type": "SHIPPING",
    "event_date": "2026-03-04",
    "event_time": "09:15:00 UTC",
    "risk_flag": None,
    "tlc": "LOT-ABC-001",
    "product_description": "Fresh Leafy Greens, bagged",
    "quantity": "40",
    "unit_of_measure": "CASE",
    "location_description": "Valley Fresh Packhouse",
    "location_gln": "0614141000005",
    "reference_doc_type": "Invoice",
    "reference_doc_num": "INV-9001",
}


def _api_key():
    return APIKey(
        key_id="preshared-master",
        key_hash="",
        name="test",
        tenant_id=TENANT,
        created_at=datetime.now(timezone.utc),
    )


def _build_app():
    from services.graph.app.routers.fsma import compliance_router

    app = FastAPI()
    app.include_router(compliance_router, prefix="/v1/fsma/compliance")
    # Middleware tenant and API-key tenant agree, so the #2511 reconcile
    # passes and the handler reaches the CSV writer.
    app.dependency_overrides[require_api_key] = lambda: _api_key()
    app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID(TENANT)
    return app


def _neo4j_stub():
    """A Neo4jClient double whose instance is an async context manager."""
    cls = MagicMock()
    cls.get_tenant_database_name.return_value = "tenant-db"
    instance = MagicMock()
    instance.__aenter__ = AsyncMock(return_value=MagicMock())
    instance.__aexit__ = AsyncMock(return_value=False)
    cls.return_value = instance
    return cls


def _export_rows(events):
    """Call the endpoint with ``events`` and return the parsed CSV rows."""
    app = _build_app()
    client = TestClient(app, raise_server_exceptions=False)

    with (
        patch("services.graph.app.routers.fsma.compliance.Neo4jClient", _neo4j_stub()),
        patch(
            "services.graph.app.routers.fsma.compliance.query_events_by_range",
            new=AsyncMock(return_value=events),
        ),
    ):
        resp = client.get(
            "/v1/fsma/compliance/export/fda-request",
            params={"start_date": "2026-01-01", "end_date": "2026-12-31"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.content
    # The handler prefixes a UTF-8 BOM for Excel (compliance.py).
    assert body.startswith(b"\xef\xbb\xbf")
    text = body[3:].decode("utf-8")
    return list(csv.reader(io.StringIO(text)))


def test_fda_request_export_header_is_exact_11_column_shape():
    rows = _export_rows([])
    assert rows[0] == EXPECTED_HEADER


def test_fda_request_export_has_no_tlc_description_column():
    """The FSMA-undefined "Traceability Lot Code Description" header is gone."""
    rows = _export_rows([])
    assert "Traceability Lot Code Description" not in rows[0]


def test_column_one_carries_the_cte_type_not_a_blank():
    rows = _export_rows([FABRICATED_EVENT])
    assert rows[0][1] == "Event Type (CTE)"
    assert len(rows) == 2
    data = rows[1]
    assert len(data) == len(EXPECTED_HEADER)
    assert data[1] == "SHIPPING"
    assert data[1] != ""
    # Neighbours are unshifted — this was a rename, not an insertion.
    assert data[0] == "LOT-ABC-001"
    assert data[2] == "Fresh Leafy Greens, bagged"


@pytest.mark.parametrize("cte", ["SHIPPING", "RECEIVING", "HARVESTING", "TRANSFORMATION"])
def test_cte_type_round_trips_for_each_event_type(cte):
    event = dict(FABRICATED_EVENT, type=cte)
    rows = _export_rows([event])
    assert rows[1][1] == cte


def test_missing_type_degrades_to_empty_not_an_error():
    """Legacy nodes without ``type`` must not 500 the export."""
    event = {k: v for k, v in FABRICATED_EVENT.items() if k != "type"}
    rows = _export_rows([event])
    assert rows[1][1] == ""
