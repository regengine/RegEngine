"""Malformed CSV structure is a 400 from POST /api/v1/ingest/csv, never a 500.

Three kinds of input crashed ``parse_csv_rows`` and surfaced as HTTP 500:

- a data row with more fields than the header: ``csv.DictReader`` files the
  overflow as a list under the ``None`` restkey and the row normalisation
  called ``.strip()`` on it;
- a file whose first line is blank: the header comes out empty, so every
  field of every row is overflow;
- anything the csv module refuses with ``csv.Error``: carriage-return-only
  line endings, or a field over ``csv.field_size_limit()``.

Extra values are evidence the uploader supplied, so a row that carries a
non-blank one is rejected (listed in the receipt) instead of silently
truncated. Blank overflow cells (a trailing comma) carry no data and are
ignored. The inbound-email route calls the same parser, so it gets the same
behaviour: quarantine with the error instead of a 500 retry loop.
"""

from __future__ import annotations

import csv
import io

import pytest
from app import csv_templates as ct
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.webhook_compat import _verify_api_key
from app.webhook_models import EventResult, IngestResponse
from fastapi import FastAPI
from fastapi.testclient import TestClient

HEADER = (
    "traceability_lot_code,product_description,quantity,unit_of_measure,harvest_date,location_name,reference_document"
)
ROW = "TLC1,Kale,10,lbs,2026-04-17,Farm A,REF"
ROW_2 = "TLC2,Kale,10,lbs,2026-04-17,Farm A,REF"
NO_HEADER = "CSV has no header row: the first line must list the column names"


@pytest.fixture
def upload(monkeypatch):
    """POST a CSV through the real route; ``ingest_events`` is stubbed and records the receipt."""
    captured: dict = {}

    async def _fake_ingest_events(payload, **kwargs):
        captured["source_file"] = kwargs["source_file"]
        return IngestResponse(
            accepted=len(payload.events),
            rejected=0,
            total=len(payload.events),
            events=[
                EventResult(traceability_lot_code=e.traceability_lot_code, cte_type=e.cte_type.value, status="accepted")
                for e in payload.events
            ],
            ingestion_run_id="run-1",
        )

    monkeypatch.setattr(ct, "ingest_events", _fake_ingest_events)
    app = FastAPI()
    app.include_router(ct.router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="key-1", scopes=["*"], tenant_id="t1"
    )
    # raise_server_exceptions=False: a parser crash must show up as a 500
    # response here, exactly as a caller sees it, not as a test error.
    client = TestClient(app, raise_server_exceptions=False)

    def _post(text: str):
        return client.post(
            "/api/v1/ingest/csv",
            files={"file": ("upload.csv", text.encode(), "text/csv")},
            data={"cte_type": "harvesting"},
        )

    return _post, captured


# ---------------------------------------------------------------------------
# More fields than the header
# ---------------------------------------------------------------------------


def test_row_with_extra_value_is_rejected_and_the_file_is_still_retained(upload):
    post, captured = upload
    text = f"{HEADER}\n{ROW}\n{ROW_2},unexpected\n"
    resp = post(text)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] == 1 and body["rejected"] == 1
    error = "Row 3: has more fields than the header (8 fields, header has 7)"
    assert [e["errors"] for e in body["events"] if e["status"] == "rejected"] == [[error]]
    # The rejected row, extra value included, stays in the retained file.
    receipt = captured["source_file"]
    assert receipt.raw_bytes == text.encode()
    assert receipt.parse_errors == [error]
    assert receipt.record_count == 2


def test_every_row_with_extra_values_is_a_400_naming_each_row(upload):
    post, captured = upload
    resp = post(f"{HEADER}\n{ROW},x\n{ROW_2},y,z\n")
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["errors"] == [
        "Row 2: has more fields than the header (8 fields, header has 7)",
        "Row 3: has more fields than the header (9 fields, header has 7)",
    ]
    assert captured == {}


def test_blank_overflow_cells_from_a_trailing_comma_are_ignored(upload):
    post, _ = upload
    resp = post(f"{HEADER}\n{ROW},\n{ROW_2},, \n")
    assert resp.status_code == 200, resp.text
    assert resp.json()["accepted"] == 2 and resp.json()["rejected"] == 0


def test_comment_row_with_extra_commas_is_still_skipped(upload):
    post, _ = upload
    resp = post(f"{HEADER}\n# note, with, more, commas, than, the, header, has\n{ROW}\n")
    assert resp.status_code == 200, resp.text
    assert resp.json()["accepted"] == 1 and resp.json()["rejected"] == 0


# ---------------------------------------------------------------------------
# Empty or blank header row
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [f"\n{HEADER}\n{ROW}\n", f",,,,,,\n{ROW}\n", f" , \n{ROW}\n"],
    ids=["blank-first-line", "only-commas", "only-whitespace-cells"],
)
def test_blank_header_row_is_a_400(upload, text):
    post, captured = upload
    resp = post(text)
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["errors"] == [NO_HEADER]
    assert captured == {}


@pytest.mark.parametrize("duplicate", ["quantity", " Quantity ", "reference document"])
def test_duplicate_normalized_headers_are_rejected_before_reading_data(monkeypatch, duplicate):
    # BE-003: reject the ambiguous header before DictReader can overwrite data.
    def unexpected_row_read(_reader):
        pytest.fail("Duplicate headers reached row dictionary construction")

    monkeypatch.setattr(csv.DictReader, "__next__", unexpected_row_read)
    events, errors, warnings = ct.parse_csv_rows(f"{HEADER},{duplicate}\n{ROW},999\n", "harvesting")
    assert events == [] and warnings == []
    assert len(errors) == 1
    assert "duplicate column" in errors[0]
    assert ct.normalize_csv_header(duplicate) in errors[0]


def test_empty_file_keeps_its_existing_400(upload):
    post, _ = upload
    resp = post("")
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "CSV contained no data rows"


# ---------------------------------------------------------------------------
# csv.Error: the csv module cannot read the file
# ---------------------------------------------------------------------------


def test_carriage_return_only_line_endings_are_a_400_naming_the_line(upload):
    post, captured = upload
    resp = post(f"{HEADER}\r{ROW}\r")
    assert resp.status_code == 400, resp.text
    [error] = resp.json()["detail"]["errors"]
    assert error.startswith("Line 1: CSV could not be read")
    assert "line endings" in error
    assert captured == {}


def test_field_over_the_size_limit_is_a_400_naming_the_line(upload):
    post, captured = upload
    oversized = "x" * (csv.field_size_limit() + 1)
    resp = post(f"{HEADER}\n{ROW}\nTLC2,{oversized},10,lbs,2026-04-17,Farm A,REF\n")
    assert resp.status_code == 400, resp.text
    [error] = resp.json()["detail"]["errors"]
    assert error.startswith("Line 3: CSV could not be read")
    # A file the csv module cannot read is not partially ingested: row 2
    # parsed, but nothing reached ingest_events.
    assert captured == {}


# ---------------------------------------------------------------------------
# Parser contract and negative control
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        f"{HEADER}\n{ROW},unexpected\n",
        f"\n{HEADER}\n{ROW}\n",
        f"{HEADER}\r{ROW}\r",
        f"{HEADER}\nTLC2,{'x' * (csv.field_size_limit() + 1)},10,lbs,2026-04-17,Farm A,REF\n",
    ],
    ids=["extra-fields", "blank-first-line", "cr-only", "oversized-field"],
)
def test_parse_csv_rows_never_raises_on_malformed_input(text):
    """The inbound-email route calls the parser directly; it must get errors back, not an exception."""
    events, parse_errors, _ = ct.parse_csv_rows(text, fallback_cte="harvesting")
    assert events == []
    assert len(parse_errors) == 1


def test_negative_control_pre_fix_row_normalisation_returns_500(upload, monkeypatch):
    """The pre-fix normalisation, run through the same route, is a 500.

    Shows the harness reports a parser crash as a 500, so the 400s above
    come from the fix and not from something else in the route.
    """

    def _pre_fix_parse_csv_rows(text, fallback_cte=None, header_mapping=None):
        for row in csv.DictReader(io.StringIO(text)):
            row = {ct.normalize_csv_header(k): (v or "").strip() for k, v in row.items()}
        return [], [], []

    monkeypatch.setattr(ct, "parse_csv_rows", _pre_fix_parse_csv_rows)
    post, _ = upload
    resp = post(f"{HEADER}\n{ROW},unexpected\n")
    assert resp.status_code == 500


# These tests cover parsing and pipeline flow; location validity is covered by
# test_location_description_complete.py and test_webhook_models.py.
pytestmark = pytest.mark.usefixtures("location_complete_for_pipeline")
