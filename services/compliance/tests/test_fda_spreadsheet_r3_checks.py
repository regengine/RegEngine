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
from datetime import datetime, time
from pathlib import Path

service_dir = Path(__file__).parent.parent
repo_root = service_dir.parent.parent
# Only evict a cached ``app`` package that belongs to a different service;
# never drop this service's own modules (other tests in the session hold them).
_cached_app = sys.modules.get("app")
_own_app = (service_dir / "app").resolve()
if _cached_app is not None and Path(getattr(_cached_app, "__file__", "") or "").resolve().parent != _own_app:
    for key in [k for k in sys.modules if k == "app" or k.startswith("app.")]:
        del sys.modules[key]
if str(service_dir) not in sys.path:
    sys.path.insert(0, str(service_dir))
sys.path.insert(0, str(repo_root / "scripts"))

import check_fda_spreadsheet_headers as hdr
import pytest
from app.fsma_spreadsheet import FDA_HEADERS, _normalise_event, generate_fda_csv

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
        "event_date": ts if ts is not None else _tz_aware_timestamp(row),
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


def _has_valid_offset(t: str) -> bool:
    """True only if ``t`` parses as a time (or datetime) with a real UTC offset."""
    for parse in (time.fromisoformat, datetime.fromisoformat):
        try:
            parsed = parse(t)
        except ValueError:
            continue
        return parsed.utcoffset() is not None
    return False


def _blank_flagged(out) -> bool:
    return not out.get("event_time") and bool(out.get("risk_flag"))


def _zone_ok_or_blank_flagged(out) -> bool:
    """Valid R3-B3 outcome when not rejected: an Event Time with a valid UTC
    offset, or no Event Time plus a flag."""
    t = out.get("event_time")
    if t:
        return _has_valid_offset(t)
    return _blank_flagged(out)


def test_event_time_offset_check_rejects_partial_offsets():
    assert _has_valid_offset("01:11:00+00:00")
    assert _has_valid_offset("01:11:00-07:00")
    assert _has_valid_offset("2026-03-12T01:11:00Z")
    for bad in ("01:11:00-", "01:11:00+", "01:11:00", "Z", "", "01:11:00+99:99"):
        assert not _has_valid_offset(bad), bad


def test_date_only_outcome_rejects_an_invented_zoned_time():
    assert not _blank_flagged({"event_time": "00:00:00Z", "risk_flag": "x"})
    assert not _blank_flagged({"event_time": "", "risk_flag": ""})
    assert _blank_flagged({"event_time": "", "risk_flag": "missing_event_time"})


def test_header_compare_detects_exact_match_and_mismatch():
    tab = hdr.FDA_CTE_TABS[0]
    fda = {tab: list(FDA_HEADERS[:2])}
    assert hdr.compare({tab: FDA_HEADERS[:2]}, fda)["ok"] is True
    bad = hdr.compare({tab: FDA_HEADERS[:3]}, fda)
    assert bad["ok"] is False and bad["tabs"][0]["mismatched_headers"] == [FDA_HEADERS[2]]


def test_header_compare_ignores_body_text_and_fragments():
    tab = hdr.FDA_CTE_TABS[0]
    header = FDA_HEADERS[3]  # "Traceability Lot Code (TLC)"
    fda = {tab: [header]}
    # A header that is not a header cell on the tab does not match.
    assert hdr.compare({tab: [FDA_HEADERS[4]]}, fda)["ok"] is False
    # A fragment of a longer header cell is not a header.
    assert hdr.compare({tab: ["Lot"]}, fda)["ok"] is False
    # A header cell split over two lines still matches as a whole.
    words = header.split(" ")
    assert hdr.compare({tab: [header]}, {tab: [" ".join(words[:2]), " ".join(words[2:])]})["ok"] is True


def test_header_row_is_found_after_a_label_change():
    rows = [["FSMA"], ["Record Count", "0"], [], ["Renamed CTE label", "Event Date"], ["x", "y"]]
    assert hdr._find_header_row(rows) == ["Renamed CTE label", "Event Date"]


def test_regengine_header_row_is_what_the_script_reads():
    assert list(hdr.regengine_tabs().values()) == [FDA_HEADERS]


@pytest.mark.xfail(strict=True, reason="R3-A1: export is one untitled CSV, FDA template has 13 CTE tabs")
def test_every_emitted_tab_is_an_fda_cte_tab():
    assert set(hdr.regengine_tabs()) <= set(hdr.FDA_CTE_TABS)


@pytest.mark.skipif(
    not __import__("os").environ.get("FDA_TEMPLATE_PDF"), reason="set FDA_TEMPLATE_PDF to the FDA template"
)
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


@pytest.mark.xfail(
    strict=True, reason="R3-B2: date-only event_date yields Event Time 00:00:00 with no zone, not a rejection"
)
def test_date_only_event_is_not_emitted_without_time_zone():
    row = _fixture_rows()[0]
    try:
        out = _normalise_event(_event(row, ts=row["harvest_date"]), strict_dates=True)
    except ValueError:
        return  # rejecting the date-only timestamp is a valid fix
    # A date-only input has no time: any emitted time (zoned or not) is invented.
    assert _blank_flagged(out)


@pytest.mark.xfail(strict=True, reason="R3-B3: kdes.event_time is copied verbatim with no zone check")
def test_kde_event_time_without_zone_is_rejected():
    row = _fixture_rows()[0]
    ev = _event(row, ts=_tz_aware_timestamp(row))
    ev["kdes"]["event_time"] = datetime.fromisoformat(ev["event_date"]).strftime("%H:%M:%S")
    try:
        out = _normalise_event(ev, strict_dates=True)
    except ValueError:
        return  # rejecting a zoneless kdes.event_time is a valid fix
    assert _zone_ok_or_blank_flagged(out)


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
