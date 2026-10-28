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
