"""Data-free CSV parser checks for empty and header-only input.

Quantity bounds require a row containing a quantity. Those record-bearing
cases are intentionally omitted under the real-data-only rule.
"""

from __future__ import annotations

from app.csv_templates import parse_csv_rows


def test_empty_csv_contains_no_events():
    events, errors, warnings = parse_csv_rows("")
    assert events == []
    assert errors == []
    assert warnings == []


def test_header_only_csv_contains_no_events():
    events, errors, warnings = parse_csv_rows("quantity\n")
    assert events == []
    assert errors == []
    assert warnings == []


def test_blank_header_is_rejected():
    events, errors, warnings = parse_csv_rows(" \n")
    assert events == []
    assert errors == ["CSV has no header row: the first line must list the column names"]
    assert warnings == []
