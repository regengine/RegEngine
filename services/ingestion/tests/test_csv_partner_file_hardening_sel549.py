"""SEL-549: an unseen partner CSV fails clearly and never loses a row silently.

Uses only synthetic data: the repo fixture ``tests/fixtures/01_harvesting.csv``
and small inline CSVs built here (C.Lee's scoped exception to real-data-only).
"""

from __future__ import annotations

from pathlib import Path

from app import csv_templates as ct

FIXTURE = Path(__file__).parent / "fixtures" / "01_harvesting.csv"

HEADER = "traceability_lot_code,product_description,quantity,unit_of_measure,harvest_date,location_name"


def _parse(text: str, cte: str | None = "harvesting", mapping=None):
    log: list = []
    events, errors, warnings = ct.parse_csv_rows(text, cte, header_mapping=mapping, row_log=log)
    return events, errors, warnings, log


def _data_rows(log):
    return {e.row_number for e in log if e.row_number >= 2 and e.disposition in {"accepted", "rejected", "skipped"}}


def test_fixture_rows_are_all_accepted_and_logged():
    text = FIXTURE.read_text()
    events, errors, _warnings, log = _parse(text)
    data_lines = len([line for line in text.splitlines()[1:] if line.strip()])
    assert errors == []
    assert len(events) == data_lines
    accepted = [e for e in log if e.disposition == "accepted"]
    assert [e.row_number for e in accepted] == list(range(2, 2 + data_lines))


def test_missing_required_columns_named_in_one_clear_error():
    text = "traceability_lot_code,product_description,harvest_date\nLOT-SYN-1,Synthetic Kale,2026-03-12\n"
    events, errors, _warnings, log = _parse(text)
    assert events == []
    assert len(errors) == 1
    assert "Missing required columns" in errors[0]
    assert "quantity (accepted column names: quantity, qty)" in errors[0]
    assert "unit_of_measure" in errors[0]
    missing = {e.field for e in log if e.reason == "missing_column"}
    assert missing == {"quantity", "unit_of_measure"}


def test_missing_cte_type_rejects_each_row_and_logs_it():
    text = f"{HEADER}\nLOT-SYN-1,Synthetic Kale,10,lbs,2026-03-12,Synthetic Farm\n"
    _e, errors, _w, log = _parse(text, cte=None)
    assert errors and "No CTE type" in errors[0]
    assert [e.reason for e in log if e.disposition == "rejected"] == ["missing_cte_type"]
    events, errors, _w, log = _parse(text, cte="harvesting")
    assert errors == [] and len(events) == 1
    assert any(e.reason == "cte_type_from_upload" for e in log)


def test_every_row_accounted_for_none_silent():
    rows = [
        "LOT-SYN-1,Synthetic Kale,10,lbs,2026-03-12,Synthetic Farm",  # 2 accepted
        "# synthetic comment row,,,,,",  # 3 skipped comment
        ",,,,,",  # 4 skipped blank
        "LOT-SYN-2,Synthetic Kale,abc,lbs,2026-03-12,Synthetic Farm",  # 5 bad quantity
        "LOT-SYN-3,Synthetic Kale,10,,2026-03-12,Synthetic Farm",  # 6 missing unit
        "LOT-SYN-4,Synthetic Kale,10,lbs,not-a-date,Synthetic Farm",  # 7 bad date
        "LOT-SYN-5,Synthetic Kale,10,lbs,2026-03-12,Synthetic Farm,EXTRA",  # 8 extra field
    ]
    text = HEADER + "\n" + "\n".join(rows) + "\n"
    events, errors, _w, log = _parse(text)
    assert len(events) == 1
    assert _data_rows(log) == set(range(2, 2 + len(rows)))
    by_row = {e.row_number: e for e in log if e.disposition in {"accepted", "rejected", "skipped"}}
    assert by_row[2].disposition == "accepted"
    assert by_row[3].reason == "comment_row"
    assert by_row[4].reason == "blank_row"
    assert by_row[5].reason == "bad_quantity"
    assert by_row[6].reason == "missing_unit_of_measure"
    assert by_row[7].reason == "bad_date"
    assert by_row[8].reason == "extra_fields"
    rejected = [e for e in log if e.disposition == "rejected"]
    assert len(rejected) == len(errors) == 4


def test_unrecognized_columns_flagged_and_kept():
    text = f"{HEADER},partner_bin\nLOT-SYN-1,Synthetic Kale,10,lbs,2026-03-12,Synthetic Farm,BIN-7\n"
    events, errors, _w, log = _parse(text)
    assert errors == [] and len(events) == 1
    assert events[0].kdes.get("partner_bin") == "BIN-7"
    flagged = [e for e in log if e.reason == "unrecognized_column"]
    assert [e.field for e in flagged] == ["partner_bin"]


def test_header_mapping_guess_logged_without_cell_value():
    header = "traceability_lot_code,product_description,amount,unit_of_measure,harvest_date,location_name"
    text = f"{header}\nLOT-SYN-1,Synthetic Kale,10,lbs,2026-03-12,Synthetic Farm\n"
    events, errors, _w, log = _parse(text, mapping={"amount": "quantity"})
    assert errors == [] and len(events) == 1
    guesses = [e for e in log if e.reason == "header_guess_applied"]
    assert len(guesses) == 1
    assert guesses[0].field == "amount" and guesses[0].guessed_as == "quantity"
    assert "10" not in (guesses[0].detail or "")


def test_log_detail_never_echoes_guessed_cell_values():
    text = f"{HEADER}\nLOT-SYN-1,Synthetic Kale,10,lbs,2026-03-12,Synthetic Farm\n"
    _e, _err, _w, log = _parse(text)
    for entry in log:
        if entry.disposition == "flagged":
            assert "LOT-SYN-1" not in (entry.detail or "")


def test_header_only_file_is_not_a_missing_column_error():
    _e, errors, _w, _log = _parse("partner_col_a,partner_col_b\n")
    assert errors == []


# ---------------------------------------------------------------------------
# Red Team acceptance bar: every unrecognised field, event type or format is
# flagged in the disposition log AND the error/warning output, and
# rows in == accepted + rejected + skipped (nothing silently dropped).
# Inputs are derived from the synthetic fixture 01_harvesting.csv.
# ---------------------------------------------------------------------------

import csv as _csv
import io as _io

import pytest


def _fixture_rows() -> tuple[list[str], list[dict]]:
    reader = _csv.DictReader(_io.StringIO(FIXTURE.read_text()))
    return list(reader.fieldnames or []), list(reader)


def _to_csv(header: list[str], rows: list[dict]) -> str:
    out = _io.StringIO()
    writer = _csv.DictWriter(out, fieldnames=header, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return out.getvalue()


def _assert_counts_balance(text: str, events, log) -> None:
    rows_in = len(text.splitlines()) - 1
    outcome = {e.row_number: e.disposition for e in log if e.row_number >= 2 and e.disposition != "flagged"}
    assert len(outcome) == rows_in, "every input row needs exactly one outcome"
    assert sum(1 for d in outcome.values() if d == "accepted") == len(events)


@pytest.fixture
def unknown_column_csv() -> str:
    header, rows = _fixture_rows()
    for i, row in enumerate(rows):
        row["partner_pallet_code"] = f"PAL-SYN-{i}"
    return _to_csv([*header, "partner_pallet_code"], rows)


@pytest.fixture
def unknown_cte_csv() -> str:
    header, rows = _fixture_rows()
    for row in rows:
        row["cte_type"] = "harvesting"
    rows[1]["cte_type"] = "teleporting"
    return _to_csv([*header, "cte_type"], rows)


@pytest.fixture
def malformed_date_csv() -> str:
    header, rows = _fixture_rows()
    rows[0]["harvest_date"] = "32/13/2026"
    return _to_csv(header, rows)


@pytest.fixture
def malformed_quantity_csv() -> str:
    header, rows = _fixture_rows()
    rows[0]["quantity"] = "5,000 lbs"
    return _to_csv(header, rows)


@pytest.fixture
def missing_columns_csv() -> str:
    header, rows = _fixture_rows()
    kept = [h for h in header if h not in {"quantity", "unit_of_measure"}]
    return _to_csv(kept, rows)


@pytest.fixture
def garbled_and_empty_rows_csv() -> str:
    text = FIXTURE.read_text().rstrip("\n").split("\n")
    header, good = text[0], text[1:]
    garbled = "\x00\x07%%LOT??,,,,,,,,,,,,ZZZ"
    empty = "," * (header.count(","))
    return "\n".join([header, good[0], garbled, empty, *good[1:]]) + "\n"


def test_acceptance_unknown_column_is_flagged(unknown_column_csv):
    events, errors, warnings, log = _parse(unknown_column_csv)
    assert any(e.reason == "unrecognized_column" and e.field == "partner_pallet_code" for e in log)
    assert any("partner_pallet_code" in w for w in warnings)
    assert errors == []
    _assert_counts_balance(unknown_column_csv, events, log)


def test_acceptance_unknown_cte_type_is_rejected_not_defaulted(unknown_cte_csv):
    events, errors, _w, log = _parse(unknown_cte_csv, cte="harvesting")
    assert [e.row_number for e in log if e.reason == "unknown_cte_type"] == [3]
    assert any("Row 3" in e and "teleporting" in e for e in errors)
    _assert_counts_balance(unknown_cte_csv, events, log)


def test_acceptance_malformed_date_is_flagged(malformed_date_csv):
    events, errors, _w, log = _parse(malformed_date_csv)
    assert [e.row_number for e in log if e.reason == "bad_date"] == [2]
    assert any(e.startswith("Row 2:") for e in errors)
    _assert_counts_balance(malformed_date_csv, events, log)


def test_acceptance_malformed_quantity_format_is_flagged(malformed_quantity_csv):
    events, errors, _w, log = _parse(malformed_quantity_csv)
    assert [e.row_number for e in log if e.reason == "bad_quantity"] == [2]
    assert any(e.startswith("Row 2:") and "not a number" in e for e in errors)
    _assert_counts_balance(malformed_quantity_csv, events, log)


def test_acceptance_missing_required_columns_flagged(missing_columns_csv):
    events, errors, _w, log = _parse(missing_columns_csv)
    assert events == []
    assert {e.field for e in log if e.reason == "missing_column"} == {"quantity", "unit_of_measure"}
    assert len(errors) == 1 and "quantity" in errors[0] and "unit_of_measure" in errors[0]


def test_acceptance_garbled_and_empty_rows_flagged(garbled_and_empty_rows_csv):
    events, errors, _w, log = _parse(garbled_and_empty_rows_csv)
    outcome = {e.row_number: e for e in log if e.row_number >= 2 and e.disposition != "flagged"}
    assert outcome[3].disposition == "rejected"  # garbled
    assert any(e.startswith("Row 3:") for e in errors)
    assert outcome[4].reason == "blank_row"  # empty
    _assert_counts_balance(garbled_and_empty_rows_csv, events, log)
