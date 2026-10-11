"""Edge and error-path tests for services/graph/app/exporters/ (QA pass).

Covers behavior the existing exporter tests do not pin down:

* ``safe_text.header_filename`` truncation must never split a ``%XX``
  escape at the cut point.
* ``safe_text`` helpers accept non-string scalars (quantities and
  confidences arrive as numbers) without crashing.
* ``trace_csv.build_trace_csv_rows`` degraded paths (no events, no lots,
  association without a lot) and tolerance of attribute-less results.
* ``recall_contacts_csv.build_recall_contacts_rows`` first-land-based
  receiving events, one row per receipt, GLN-less name/address matching,
  and tolerance of attribute-less results.
* Builders keep per-result state only: rows built for one tenant result
  never leak into another.
"""

from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.exporters.recall_contacts_csv import (  # noqa: E402
    RECALL_CONTACTS_HEADER,
    build_recall_contacts_rows,
)
from services.graph.app.exporters.safe_text import (  # noqa: E402
    csv_safe,
    header_filename,
    rfc5987_filename,
    xml_escape,
    zpl_safe,
)
from services.graph.app.exporters.trace_csv import (  # noqa: E402
    TRACE_CSV_HEADER,
    build_trace_csv_rows,
)
from services.graph.app.fsma.types import TraceResult  # noqa: E402

_TCOL = {name: idx for idx, name in enumerate(TRACE_CSV_HEADER)}


def _trace_result(**overrides):
    base = dict(
        lot_id="LOT-A",
        direction="forward",
        facilities=[],
        events=[],
        lots=[],
        total_quantity=None,
        query_time_ms=1.0,
        hop_count=1,
    )
    base.update(overrides)
    return TraceResult(**base)


# ---------------------------------------------------------------------------
# header_filename: truncation must not split percent-escapes
# ---------------------------------------------------------------------------


class TestHeaderFilenameTruncation:
    def test_cut_before_escape_is_kept_whole(self):
        # "a b" encodes to "a%20b". Cutting at 4 keeps the full triplet.
        assert header_filename("a b", max_len=4) == "a%20"

    def test_cut_inside_escape_drops_the_fragment(self):
        # Cutting at 3 would leave "a%2"; at 2 it would leave "a%".
        # Both are invalid percent-encoding, so the fragment is dropped.
        assert header_filename("a b", max_len=3) == "a"
        assert header_filename("a b", max_len=2) == "a"

    def test_no_max_len_yields_a_trailing_fragment(self):
        for max_len in range(1, 60):
            out = header_filename("report " * 10 + "final.csv", max_len=max_len)
            assert not out.endswith("%"), f"max_len={max_len}: {out!r}"
            assert not (
                len(out) >= 2
                and out[-2] == "%"
                and out[-1] in "0123456789ABCDEFabcdef"
            ), f"max_len={max_len}: {out!r}"

    def test_truncated_output_still_usable_as_filename(self):
        out = header_filename("a b", max_len=3)
        assert out == "a"
        assert len(out) <= 3

    def test_name_of_only_stripped_chars_yields_default(self):
        assert header_filename('"') == "download"
        assert header_filename("\x00\r\n") == "download"


# ---------------------------------------------------------------------------
# safe_text: non-string scalars
# ---------------------------------------------------------------------------


class TestSafeTextScalars:
    def test_csv_safe_numbers(self):
        assert csv_safe(0) == "0"
        assert csv_safe(40) == "40"
        assert csv_safe(3.5) == "3.5"
        assert csv_safe(True) == "True"
        assert csv_safe(None) == ""

    def test_xml_escape_number(self):
        assert xml_escape(5) == "5"
        assert xml_escape(None) == ""

    def test_zpl_safe_number(self):
        assert zpl_safe(123) == "123"

    def test_rfc5987_round_trip(self):
        out = rfc5987_filename("caf\u00e9.csv")
        assert urllib.parse.unquote(out) == "caf\u00e9.csv"

    def test_rfc5987_empty(self):
        assert rfc5987_filename("") == ""


# ---------------------------------------------------------------------------
# trace_csv degraded and edge paths
# ---------------------------------------------------------------------------


class TestTraceCsvEdges:
    def test_multiple_lots_without_events_yield_one_row_per_lot(self):
        lots = [
            {"tlc": "LOT-A", "product_description": "Romaine"},
            {"tlc": "LOT-B", "product_description": "Spinach"},
        ]
        rows = build_trace_csv_rows(_trace_result(lots=lots), "LOT-A")
        assert len(rows) == 2
        assert {r[_TCOL["Traceability Lot Code (TLC)"]] for r in rows} == {"LOT-A", "LOT-B"}
        for row in rows:
            assert row[_TCOL["Event Type"]] == ""
            assert row[_TCOL["Facility GLN"]] == ""

    def test_no_lots_and_no_events_yields_no_rows(self):
        assert build_trace_csv_rows(_trace_result(), "LOT-A") == []

    def test_association_without_lot_keeps_event_with_blank_tlc(self):
        event = {"event_id": "e1", "type": "SHIPPING", "event_date": "2026-03-04"}
        facility = {"gln": "0614141000005", "name": "Packhouse", "address": "1 Grower Way"}
        rows = build_trace_csv_rows(
            _trace_result(trace_rows=[{"lot": None, "event": event, "facility": facility}]),
            "LOT-A",
        )
        assert len(rows) == 1
        assert rows[0][_TCOL["Traceability Lot Code (TLC)"]] == ""
        assert rows[0][_TCOL["Event Type"]] == "SHIPPING"
        assert rows[0][_TCOL["Facility GLN"]] == "0614141000005"

    def test_event_time_column_is_filled_when_present(self):
        event = {"event_id": "e1", "type": "SHIPPING", "event_date": "2026-03-04", "event_time": "08:15:00"}
        lot = {"tlc": "LOT-A"}
        rows = build_trace_csv_rows(
            _trace_result(trace_rows=[{"lot": lot, "event": event, "facility": None}]),
            "LOT-A",
        )
        assert rows[0][_TCOL["Event Time"]] == "08:15:00"

    def test_none_quantity_and_confidence_are_blank_not_crash(self):
        lot = {"tlc": "LOT-A", "quantity": None}
        event = {"event_id": "e1", "type": "SHIPPING", "confidence": None}
        rows = build_trace_csv_rows(
            _trace_result(trace_rows=[{"lot": lot, "event": event, "facility": None}]),
            "LOT-A",
        )
        assert rows[0][_TCOL["Quantity"]] == ""
        assert rows[0][_TCOL["Confidence Score"]] == ""

    def test_result_without_attributes_yields_no_rows(self):
        assert build_trace_csv_rows(object(), "LOT-A") == []

    def test_rows_match_header_width(self):
        lot = {"tlc": "LOT-A"}
        event = {"event_id": "e1", "type": "SHIPPING"}
        rows = build_trace_csv_rows(
            _trace_result(
                lots=[lot],
                events=[event],
                trace_rows=[{"lot": lot, "event": event, "facility": None}],
            ),
            "LOT-A",
        )
        for row in rows:
            assert len(row) == len(TRACE_CSV_HEADER)


# ---------------------------------------------------------------------------
# recall_contacts_csv edge paths
# ---------------------------------------------------------------------------


def _recall_result(trace_rows, facilities):
    return TraceResult(
        lot_id="LOT-A",
        direction="forward",
        facilities=list(facilities),
        events=[],
        lots=[],
        total_quantity=None,
        query_time_ms=1.0,
        hop_count=1,
        trace_rows=trace_rows,
    )


class TestRecallContactsEdges:
    def test_first_land_based_receiving_counts_as_receipt(self):
        facility = {"gln": "0614141000005", "name": "Port", "address": "Pier 1", "facility_type": "IMPORTER"}
        assoc_facility = {"gln": "0614141000005", "name": "Port", "address": "Pier 1"}
        lot = {"tlc": "LOT-A", "quantity": 10, "unit_of_measure": "cases"}
        event = {"event_id": "e1", "type": "FIRST_LAND_BASED_RECEIVING", "event_date": "2026-03-06"}
        rows = build_recall_contacts_rows(
            _recall_result([{"lot": lot, "event": event, "facility": assoc_facility}], [facility])
        )
        assert len(rows) == 1
        row = dict(zip(RECALL_CONTACTS_HEADER, rows[0]))
        assert row["Traceability Lot Code"] == "LOT-A"
        assert row["Date Received"] == "2026-03-06"
        assert row["Facility Type"] == "IMPORTER"

    def test_two_receipts_same_facility_yield_two_rows(self):
        facility = {"gln": "0614141000005", "name": "DC", "address": "9 Dock St", "facility_type": "DISTRIBUTOR"}
        assoc_facility = {"gln": "0614141000005", "name": "DC", "address": "9 Dock St"}
        rows = build_recall_contacts_rows(
            _recall_result(
                [
                    {
                        "lot": {"tlc": "LOT-A", "quantity": 40, "unit_of_measure": "cases"},
                        "event": {"event_id": "e1", "type": "RECEIVING", "event_date": "2026-03-06"},
                        "facility": assoc_facility,
                    },
                    {
                        "lot": {"tlc": "LOT-B", "quantity": 18, "unit_of_measure": "cases"},
                        "event": {"event_id": "e2", "type": "RECEIVING", "event_date": "2026-03-07"},
                        "facility": assoc_facility,
                    },
                ],
                [facility],
            )
        )
        assert len(rows) == 2
        assert {(dict(zip(RECALL_CONTACTS_HEADER, r)))["Traceability Lot Code"] for r in rows} == {"LOT-A", "LOT-B"}

    def test_gln_less_matching_by_name_and_address(self):
        traversal_facility = {"name": "Corner Store", "address": "3 Main St", "facility_type": "RETAILER"}
        assoc_facility = {"name": "Corner Store", "address": "3 Main St"}
        lot = {"tlc": "LOT-A", "quantity": 5, "unit_of_measure": "cases"}
        event = {"event_id": "e1", "type": "RECEIVING", "event_date": "2026-03-08"}
        rows = build_recall_contacts_rows(
            _recall_result([{"lot": lot, "event": event, "facility": assoc_facility}], [traversal_facility])
        )
        assert len(rows) == 1
        row = dict(zip(RECALL_CONTACTS_HEADER, rows[0]))
        assert row["Facility Name"] == "Corner Store"
        assert row["Date Received"] == "2026-03-08"
        assert row["Facility Type"] == "RETAILER"

    def test_result_without_attributes_yields_no_rows(self):
        assert build_recall_contacts_rows(object()) == []

    def test_rows_match_header_width(self):
        facility = {"gln": "0614141000005", "name": "DC", "address": "9 Dock St", "facility_type": "DISTRIBUTOR"}
        rows = build_recall_contacts_rows(_recall_result(None, [facility]))
        assert len(rows) == 1
        assert len(rows[0]) == len(RECALL_CONTACTS_HEADER)


# ---------------------------------------------------------------------------
# No cross-result state: builders are pure functions of their input
# ---------------------------------------------------------------------------


class TestNoCrossResultLeakage:
    def test_trace_rows_do_not_leak_between_results(self):
        fac_a = {"gln": "GLN-A", "name": "Tenant A Site", "address": "1 A St"}
        fac_b = {"gln": "GLN-B", "name": "Tenant B Site", "address": "2 B St"}
        lot_a = {"tlc": "LOT-A"}
        event = {"event_id": "e1", "type": "SHIPPING", "event_date": "2026-03-04"}
        rows_a = build_trace_csv_rows(
            _trace_result(trace_rows=[{"lot": lot_a, "event": event, "facility": fac_a}]),
            "LOT-A",
        )
        rows_b = build_trace_csv_rows(
            _trace_result(trace_rows=[{"lot": {"tlc": "LOT-B"}, "event": event, "facility": fac_b}]),
            "LOT-B",
        )
        assert "GLN-B" not in {c for r in rows_a for c in r}
        assert "GLN-A" not in {c for r in rows_b for c in r}

    def test_recall_rows_do_not_leak_between_results(self):
        fac_a = {"gln": "GLN-A", "name": "Tenant A Site", "address": "1 A St", "facility_type": "DISTRIBUTOR"}
        fac_b = {"gln": "GLN-B", "name": "Tenant B Site", "address": "2 B St", "facility_type": "RETAILER"}
        recv = {"event_id": "e1", "type": "RECEIVING", "event_date": "2026-03-06"}
        rows_a = build_recall_contacts_rows(
            _recall_result(
                [{"lot": {"tlc": "LOT-A"}, "event": recv, "facility": dict(fac_a)}],
                [fac_a],
            )
        )
        rows_b = build_recall_contacts_rows(_recall_result(None, [fac_b]))
        assert "GLN-B" not in {c for r in rows_a for c in r}
        assert "GLN-A" not in {c for r in rows_b for c in r}
        assert "LOT-A" not in {c for r in rows_b for c in r}
