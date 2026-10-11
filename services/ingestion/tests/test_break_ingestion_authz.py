"""Adversarial regression tests for ingestion authz surface.

Covers services/ingestion/app/auditor_router.py (pagination bounds),
services/ingestion/app/canonical_router.py (history endpoint existence
check), and services/ingestion/app/csv_templates.py (row-cap drop
reporting, template formula safety).

Each test fails on the pre-fix code and passes after the fix.
"""

import csv
import io
import sys
from pathlib import Path
from typing import Any, List, Optional

_ingestion_dir = Path(__file__).resolve().parent.parent
if str(_ingestion_dir) not in sys.path:
    sys.path.insert(0, str(_ingestion_dir))

_services_dir = _ingestion_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytest.importorskip("fastapi")

from app.auditor_router import router as auditor_router
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.canonical_router import _get_db_session, router as canonical_router
from app.csv_templates import CTE_COLUMNS, MAX_CSV_ROWS, _generate_csv_template, parse_csv_rows
from app.shared.csv_safety import sanitize_cell
from shared.database import get_db_session

TENANT_ID = "tenant-a"
OTHER_TENANT_ID = "tenant-victim"


class _Result:
    def __init__(self, *, row: Any = None, rows: Any = None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _FakeSession:
    def __init__(self, results: Optional[List[_Result]] = None):
        self._results = list(results or [])
        self._i = 0

    def execute(self, *_args, **_kwargs):
        if self._i < len(self._results):
            r = self._results[self._i]
            self._i += 1
            return r
        return _Result()


def _principal() -> IngestionPrincipal:
    return IngestionPrincipal(key_id="k", scopes=["*"], tenant_id=TENANT_ID, auth_mode="test")


def _audit_client(session: _FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(auditor_router)
    app.dependency_overrides[get_ingestion_principal] = _principal
    app.dependency_overrides[get_db_session] = lambda: session
    return TestClient(app)


def _canon_client(session: _FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(canonical_router)
    app.dependency_overrides[get_ingestion_principal] = _principal
    app.dependency_overrides[_get_db_session] = lambda: session
    return TestClient(app)


# ---------------------------------------------------------------------------
# Auditor pagination bounds: negative limit/offset must be rejected at the
# API boundary (422), never forwarded to SQL where Postgres raises and the
# caller sees a 500.
# ---------------------------------------------------------------------------


class TestAuditorPaginationBounds:
    def test_events_negative_offset_rejected(self) -> None:
        resp = _audit_client(_FakeSession()).get("/api/v1/audit/events", params={"tenant_id": TENANT_ID, "offset": -1})
        assert resp.status_code == 422

    def test_events_negative_limit_rejected(self) -> None:
        resp = _audit_client(_FakeSession()).get("/api/v1/audit/events", params={"tenant_id": TENANT_ID, "limit": -5})
        assert resp.status_code == 422

    def test_exceptions_negative_limit_rejected(self) -> None:
        resp = _audit_client(_FakeSession()).get(
            "/api/v1/audit/exceptions", params={"tenant_id": TENANT_ID, "limit": -5}
        )
        assert resp.status_code == 422

    def test_export_log_negative_limit_rejected(self) -> None:
        resp = _audit_client(_FakeSession()).get(
            "/api/v1/audit/export-log", params={"tenant_id": TENANT_ID, "limit": -5}
        )
        assert resp.status_code == 422

    def test_events_zero_limit_still_allowed(self) -> None:
        resp = _audit_client(_FakeSession()).get("/api/v1/audit/events", params={"tenant_id": TENANT_ID, "limit": 0})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Canonical history: an event id that does not exist under the caller's
# tenant must return 404 like get_record does, not 200 with an empty
# chain that is indistinguishable from "exists, no amendments".
# ---------------------------------------------------------------------------


class TestRecordHistoryNotFound:
    def test_missing_event_returns_404(self) -> None:
        client = _canon_client(_FakeSession([_Result(row=None)]))
        resp = client.get("/api/v1/records/evt-nope/history", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 404

    def test_other_tenant_event_returns_404(self) -> None:
        # Existence check is scoped by resolved tenant, so a foreign id
        # reads exactly like a missing id: 404, no oracle.
        client = _canon_client(_FakeSession([_Result(row=None)]))
        resp = client.get("/api/v1/records/evt-foreign/history", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# CSV row cap: rows past the cap were silently dropped (a 505-row file
# ingested 500 rows with one error that named no count). The parser must
# report how many rows were skipped.
# ---------------------------------------------------------------------------

_CSV_HEADER = (
    "traceability_lot_code,product_description,quantity,unit_of_measure,harvest_date,location_name,reference_document\n"
)


def _big_csv(n_rows: int) -> str:
    return _CSV_HEADER + "".join(f"LOT-{i:05d},Kale,100,cases,2026-04-01,Farm A,REF-{i}\n" for i in range(n_rows))


class TestCsvOverflowReporting:
    def test_skipped_rows_are_counted(self) -> None:
        events, errors, _ = parse_csv_rows(_big_csv(MAX_CSV_ROWS + 5), "harvesting")
        assert len(events) == MAX_CSV_ROWS
        assert any("4 more row(s)" in err for err in errors), errors

    def test_cap_message_kept_verbatim(self) -> None:
        # Pinned by test_scan_stops_exactly_where_the_parser_stops: the
        # last error must still end with the exact cap message.
        events, errors, _ = parse_csv_rows(_big_csv(MAX_CSV_ROWS + 5), "harvesting")
        assert errors[-1].endswith(f"CSV exceeds maximum row limit of {MAX_CSV_ROWS}")

    def test_exactly_at_cap_plus_one_reports_no_extra_rows(self) -> None:
        events, errors, _ = parse_csv_rows(_big_csv(MAX_CSV_ROWS + 1), "harvesting")
        assert len(events) == MAX_CSV_ROWS
        assert errors == [f"Row {MAX_CSV_ROWS + 2}: CSV exceeds maximum row limit of {MAX_CSV_ROWS}"]


# ---------------------------------------------------------------------------
# CSV template formula safety: every example cell in a downloaded template
# must survive the project's own sanitize_cell unchanged, so opening the
# template in Excel cannot turn an example into a live formula.
# ---------------------------------------------------------------------------


class TestTemplateFormulaSafety:
    def test_example_rows_are_spreadsheet_safe(self) -> None:
        bad = []
        for cte_type in CTE_COLUMNS:
            rows = list(csv.reader(io.StringIO(_generate_csv_template(cte_type))))
            for cell in rows[1]:
                if sanitize_cell(cell) != cell:
                    bad.append((cte_type, cell))
        assert bad == [], f"template example cells need formula sanitization: {bad}"
