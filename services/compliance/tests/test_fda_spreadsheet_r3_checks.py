"""R3 checks for the FDA sortable spreadsheet (SEL-504, SEL-519).

The spreadsheet answers FDA's 24-hour records request,
21 CFR 1.1455(c)(1). Three checks:

(a) every tab RegEngine emits matches the same tab of FDA's template
    (scripts/check_fda_spreadsheet_headers.py);
(b) every Event Time carries its time zone (SEL-519);
(c) only real GTIN / GLN codes, no placeholders (SEL-504).

Inputs come only from the repo fixture
services/ingestion/tests/fixtures/01_harvesting.csv (C.Lee's R3
exception) or are derived from it / generated at runtime. ``xfail``
marks cases the export does not meet yet; see
docs/handoffs/r3-fda-spreadsheet-handoff.md for the fix list.
"""

import csv
import io
import sys
from datetime import datetime
from pathlib import Path

service_dir = Path(__file__).parent.parent
repo_root = service_dir.parent.parent
for key in [k for k in sys.modules if k == "app" or k.startswith("app.") or k == "main"]:
    del sys.modules[key]
sys.path.insert(0, str(service_dir))
sys.path.insert(0, str(repo_root / "scripts"))

import pytest
from app.fsma_spreadsheet import FDA_HEADERS, _normalise_event, generate_fda_csv

import check_fda_spreadsheet_headers as hdr

FIXTURE = repo_root / "services" / "ingestion" / "tests" / "fixtures" / "01_harvesting.csv"


def _fixture_rows():
    with FIXTURE.open(newline="") as fh:
        return list(csv.DictReader(fh))


def _gs1_check_digit_ok(code: str) -> bool:
    if not code.isdigit() or len(code) not in (13, 14):
        return False
    body, check = code[:-1], int(code[-1])
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def _event(row, *, ts=None, gln=None):
    return {
        "type": "harvesting",
        "tlc": row["traceability_lot_code"],
        "product_description": row["product_description"],
        "quantity": row["quantity"],
        "uom": row["unit_of_measure"],
        "event_date": ts if ts is not None else row["harvest_date"],
        "facility_gln": row["location_gln"] if gln is None else gln,
        "facility_name": row["location_name"],
        "kdes": {"reference_document_number": row["reference_document"]},
    }


def _tz_aware_timestamp(row) -> str:
    # Fixture date plus the runtime's local offset: no invented value.
    local = datetime.now().astimezone()
    day = datetime.fromisoformat(row["harvest_date"])
    return day.replace(hour=local.hour, minute=local.minute, tzinfo=local.tzinfo).isoformat()


def _data_rows(csv_text):
    rows = list(csv.reader(io.StringIO(csv_text)))
    start = next(i for i, r in enumerate(rows) if r and r[0] == FDA_HEADERS[0])
    return [dict(zip(rows[start], r)) for r in rows[start + 1 :] if r]


# ─── (a) tabs and headers ───────────────────────────────────────────────


def test_header_compare_detects_exact_match_and_mismatch():
    tab = hdr.FDA_CTE_TABS[0]
    fda = {tab: " ".join(FDA_HEADERS[:2])}
    assert hdr.compare({tab: FDA_HEADERS[:2]}, fda)["ok"] is True
    bad = hdr.compare({tab: FDA_HEADERS[:3]}, fda)
    assert bad["ok"] is False and bad["tabs"][0]["mismatched_headers"] == [FDA_HEADERS[2]]


def test_regengine_header_row_is_what_the_script_reads():
    assert list(hdr.regengine_tabs().values()) == [FDA_HEADERS]


@pytest.mark.xfail(strict=True, reason="R3-A1: export is one untitled CSV, FDA template has 13 CTE tabs")
def test_every_emitted_tab_is_an_fda_cte_tab():
    assert set(hdr.regengine_tabs()) <= set(hdr.FDA_CTE_TABS)


@pytest.mark.skipif(not __import__("os").environ.get("FDA_TEMPLATE_PDF"), reason="set FDA_TEMPLATE_PDF to the FDA template")
@pytest.mark.xfail(strict=True, reason="R3-A2: 29/29 headers do not match an FDA tab")
def test_headers_match_fda_template_pdf():
    import os

    data = Path(os.environ["FDA_TEMPLATE_PDF"]).read_bytes()
    assert hdr.compare(hdr.regengine_tabs(), hdr.fda_tab_text(data))["ok"]


# ─── (b) Event Time carries its time zone (SEL-519) ─────────────────────


@pytest.mark.xfail(strict=True, reason="R3-B1: _parse_timestamp drops the UTC offset (strftime %H:%M:%S)")
def test_event_time_keeps_time_zone_offset():
    row = _fixture_rows()[0]
    ts = _tz_aware_timestamp(row)
    out = _normalise_event(_event(row, ts=ts), strict_dates=True)
    offset = datetime.fromisoformat(ts).strftime("%z")
    assert offset[:3] in out["event_time"]


@pytest.mark.xfail(strict=True, reason="R3-B2: date-only event_date yields Event Time 00:00:00 with no zone, not a rejection")
def test_date_only_event_is_not_emitted_without_time_zone():
    row = _fixture_rows()[0]
    out = _normalise_event(_event(row), strict_dates=True)
    assert out["event_time"] and any(c in out["event_time"] for c in "+-Z")


@pytest.mark.xfail(strict=True, reason="R3-B3: kdes.event_time is copied verbatim with no zone check")
def test_kde_event_time_without_zone_is_rejected():
    row = _fixture_rows()[0]
    ev = _event(row, ts=_tz_aware_timestamp(row))
    ev["kdes"]["event_time"] = datetime.fromisoformat(ev["event_date"]).strftime("%H:%M:%S")
    out = _normalise_event(ev, strict_dates=True)
    assert any(c in out["event_time"] for c in "+-Z")


# ─── (c) real GTIN / GLN only (SEL-504) ─────────────────────────────────


def test_fixture_glns_are_valid_and_pass_through_unchanged():
    rows = _fixture_rows()
    assert all(_gs1_check_digit_ok(r["location_gln"]) for r in rows)
    out = _data_rows(generate_fda_csv([_event(r) for r in rows]))
    assert {o["Origin GLN"] for o in out} == {r["location_gln"] for r in rows}


@pytest.mark.xfail(strict=True, reason="R3-C1: a GLN failing the GS1 check digit is exported as-is")
# Deliberate negative case: the GLN below is NOT a real code. It is derived
# from the fixture's real GLN 0061414100014 (01_harvesting.csv) by changing
# only its GS1 check digit, under C.Lee's R3 fixture exception.
def test_gln_with_bad_check_digit_is_rejected():
    """Deliberate bad-check-digit negative case (R3-C1).

    Derived from the fixture's real GLN 0061414100014 under C.Lee's R3
    fixture exception; the export must reject a GLN whose GS1 check digit
    fails.
    """
    row = _fixture_rows()[0]
    good = row["location_gln"]
    bad = good[:-1] + str((int(good[-1]) + 1) % 10)
    with pytest.raises(ValueError):
        generate_fda_csv([_event(row, gln=bad)])


@pytest.mark.xfail(strict=True, reason="R3-C2: a missing GLN is exported as an empty cell with no flag")
def test_missing_gln_is_rejected_or_flagged():
    row = _fixture_rows()[0]
    try:
        out = _data_rows(generate_fda_csv([_event(row, gln="")]))
    except ValueError:
        return
    assert out[0]["Risk Flag"]


@pytest.mark.xfail(strict=True, reason="R3-C3: the spreadsheet has no GTIN column")
def test_spreadsheet_has_gtin_column():
    assert any("GTIN" in h for h in FDA_HEADERS)


def test_spreadsheet_does_not_share_epcis_code_path():
    src = (service_dir / "app" / "fsma_spreadsheet.py").read_text()
    assert "epcis" not in src.lower()
