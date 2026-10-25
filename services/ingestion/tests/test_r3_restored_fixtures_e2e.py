"""End-to-end runs of the restored CSV and EDI fixtures.

Each fixture goes through: ingest -> KDE/CTE checks -> data gap flags
(``shared.data_gap_tracking``) -> FDA sortable spreadsheet. The run must
finish within the 24 hours allowed by 21 CFR 1.1455(c)(1). The spreadsheet
format is covered by 21 CFR 1.1455(c)(3)(ii).

Fixtures were restored byte-for-byte under C.Lee's scoped exception to the
real-data-only rule:
- ``sample_data/01_harvesting.csv`` (from a0911dc6^)
- ``services/ingestion/tests/fixtures/edi_corpus/asn_856.edi`` and
  ``asn_856.expected.json`` (from 2a8f4887^)

No fixture values are invented or edited here. The EDI 856 carries no lot
number (LIN/LT) and no ship date KDE, so it is expected to be rejected with
open gaps and to contribute no spreadsheet rows.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SERVICE = Path(__file__).resolve().parents[1]
REPO = SERVICE.parents[1]
sys.path.insert(0, str(SERVICE))

from app.csv_templates import parse_csv_rows  # noqa: E402
from app.edi_ingestion import routes as edi_routes  # noqa: E402
from app.edi_ingestion.extractors import _extract_fields_for_set  # noqa: E402
from app.edi_ingestion.parser import _parse_x12_segments  # noqa: E402
from app.edi_ingestion.validation import _validate_edi_as_fsma_event  # noqa: E402
from app.fda_export_service import FDA_COLUMNS, _generate_csv  # noqa: E402
from app.webhook_router_v2 import _validate_event_kdes  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from shared.data_gap_tracking import (  # noqa: E402
    GAP_KIND_MISSING_KDE,
    decide_transition,
    gaps_from_kde_errors,
)

CSV_FIXTURE = REPO / "sample_data" / "01_harvesting.csv"
EDI_DIR = SERVICE / "tests" / "fixtures" / "edi_corpus"
SLA = timedelta(hours=24)  # 21 CFR 1.1455(c)(1)


def _export_row(event, ingested_at: datetime) -> dict:
    """Shape an accepted IngestEvent like a stored row for ``_generate_csv``."""
    return {
        "traceability_lot_code": event.traceability_lot_code,
        "product_description": event.product_description,
        "quantity": event.quantity,
        "unit_of_measure": event.unit_of_measure,
        "event_type": event.cte_type.value,
        "event_timestamp": event.timestamp,
        "location_gln": event.location_gln,
        "location_name": event.location_name,
        "kdes": dict(event.kdes),
        "source": "fixture",
        "ingested_at": ingested_at.isoformat(),
    }


def _run_pipeline(events):
    """KDE check -> gap flags -> spreadsheet. Returns (gaps_by_tlc, csv_text)."""
    ingested_at = datetime.now(timezone.utc)
    gaps_by_tlc, accepted = {}, []
    for event in events:
        errors = _validate_event_kdes(event)
        gaps = gaps_from_kde_errors(errors)
        gaps_by_tlc[event.traceability_lot_code] = (decide_transition(gaps), gaps)
        if not errors:
            accepted.append(_export_row(event, ingested_at))
    return gaps_by_tlc, _generate_csv(accepted), ingested_at


def _parse_sheet(text: str):
    reader = csv.DictReader(io.StringIO(text))
    return reader.fieldnames, list(reader)


def test_csv_harvesting_fixture_end_to_end():
    """21 CFR 1.1455(c)(1): CSV harvest records reach the FDA spreadsheet within 24h."""
    started = datetime.now(timezone.utc)
    source = list(csv.DictReader(io.StringIO(CSV_FIXTURE.read_text(encoding="utf-8"))))

    events, parse_errors, kde_warnings = parse_csv_rows(
        CSV_FIXTURE.read_text(encoding="utf-8"), fallback_cte="harvesting"
    )
    assert parse_errors == [] and kde_warnings == []
    assert len(events) == len(source)
    assert {e.cte_type.value for e in events} == {"harvesting"}

    gaps_by_tlc, sheet, _ = _run_pipeline(events)
    assert all(state == ("close", ()) for state in gaps_by_tlc.values())

    headers, rows = _parse_sheet(sheet)
    assert headers == FDA_COLUMNS
    assert [r["Traceability Lot Code (TLC)"] for r in rows] == [
        s["traceability_lot_code"] for s in source
    ]
    for row, src in zip(rows, source):
        assert row["Event Type (CTE)"].lower() == "harvesting"
        assert row["Product Description"] == src["product_description"]
        assert row["Location GLN"] == src["location_gln"]
        assert row["Harvest Date"] == src["harvest_date"]
        assert row["System Entry Timestamp"]

    assert datetime.now(timezone.utc) - started <= SLA


def test_edi_856_fixture_end_to_end():
    """21 CFR 1.1455(c)(1): the EDI 856 run completes within 24h with its gaps flagged."""
    started = datetime.now(timezone.utc)
    raw = (EDI_DIR / "asn_856.edi").read_text(encoding="utf-8")
    expected = json.loads((EDI_DIR / "asn_856.expected.json").read_text(encoding="utf-8"))

    segments = _parse_x12_segments(raw)
    extracted = _extract_fields_for_set("856", segments)
    assert extracted == expected

    # Same header/line merge as ingest_edi_document. The document's own
    # identifier is the only TLC-like value it carries (no LIN/LT lot).
    header = {k: v for k, v in extracted.items() if k != "line_items"}
    lines = extracted["line_items"]
    assert len(lines) == 1 and lines[0]["lot_number"] is None
    merged = {**header, **lines[0], "edi_line_index": 1}
    tlc = extracted["asn_number"]

    with pytest.raises(ValidationError):
        _validate_edi_as_fsma_event(merged, "856", tlc, None)

    event = edi_routes._build_ingest_event_for_set(
        "856", merged, tlc, None, None, None, None, segments=segments
    )
    assert event.cte_type.value == "shipping"
    assert event.quantity == lines[0]["quantity"]
    assert event.kdes["ship_from_gln"] == expected["ship_from_gln"]
    assert event.kdes["ship_to_gln"] == expected["ship_to_gln"]

    gaps_by_tlc, sheet, _ = _run_pipeline([event])
    transition, gaps = gaps_by_tlc[tlc]
    assert transition == "open"
    assert {g.gap_kind for g in gaps} == {GAP_KIND_MISSING_KDE}
    assert {"ship_date", "tlc_source_reference"} <= {g.gap_key for g in gaps}

    headers, rows = _parse_sheet(sheet)
    assert headers == FDA_COLUMNS
    assert rows == []

    assert datetime.now(timezone.utc) - started <= SLA
