"""SEL-519: Event Time is normalised to UTC with a Z suffix."""

import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.fsma_spreadsheet import _parse_timestamp, generate_fda_csv  # noqa: E402


def test_offset_timestamp_converted_to_utc_with_z():
    assert _parse_timestamp("2026-03-15T09:00:00-08:00") == ("2026-03-15", "17:00:00Z")


def test_offset_can_roll_the_utc_date():
    assert _parse_timestamp("2026-03-15T20:00:00-08:00") == ("2026-03-16", "04:00:00Z")


def test_naive_timestamp_is_not_falsely_labelled():
    assert _parse_timestamp("2026-03-15T09:00:00") == ("2026-03-15", "09:00:00")


def _event(ts, tlc):
    return {
        "event_type": "shipping",
        "traceability_lot_code": tlc,
        "kdes": {"event_date": ts},
    }


def _tlc_and_time_order(out):
    rows = list(csv.reader(io.StringIO(out.lstrip("\ufeff"))))
    hi = next(i for i, r in enumerate(rows) if "Event Time" in r)
    header = rows[hi]
    tlc = header.index("Traceability Lot Code (TLC)")
    t = header.index("Event Time")
    data = [r for r in rows[hi + 1 :] if len(r) > tlc and r[tlc].startswith("LOT-")]
    return [r[tlc] for r in data], [r[t] for r in data]


def test_mixed_naive_and_zoned_rows_sort_on_utc_instant():
    # Fixed timestamps only. Policy: a naive time is taken as UTC for
    # ordering only and stays unlabelled in the output, so the naive
    # 15:00 row and the 10:00 at UTC-5 row (15:00:00Z) are the same
    # instant and keep their input order instead of being split by the
    # lexical "Z" suffix. The naive 09:00 row comes first.
    events = [
        _event("2026-03-15T10:00:00-05:00", "LOT-ZONED-15"),
        _event("2026-03-15T15:00:00", "LOT-NAIVE-15"),
        _event("2026-03-15T09:00:00", "LOT-NAIVE-09"),
    ]
    tlcs, times = _tlc_and_time_order(generate_fda_csv(events))
    assert tlcs == ["LOT-NAIVE-09", "LOT-ZONED-15", "LOT-NAIVE-15"]
    assert times == ["09:00:00", "15:00:00Z", "15:00:00"]


def test_two_zone_repro_sorts_in_real_order():
    # 09:00 at UTC-8 is 17:00Z; 10:00 at UTC-5 is 15:00Z, so it comes first.
    out = generate_fda_csv([_event("2026-03-15T09:00:00-08:00", "LOT-A"), _event("2026-03-15T10:00:00-05:00", "LOT-B")])
    rows = list(csv.reader(io.StringIO(out.lstrip("\ufeff"))))
    hi = next(i for i, r in enumerate(rows) if "Event Time" in r)
    header = rows[hi]
    tlc = header.index("Traceability Lot Code (TLC)")
    data = [r for r in rows[hi + 1 :] if len(r) > tlc and r[tlc].startswith("LOT-")]
    t = header.index("Event Time")
    assert [r[tlc] for r in data] == ["LOT-B", "LOT-A"]
    assert [r[t] for r in data] == ["15:00:00Z", "17:00:00Z"]
