"""Data-free GLN regressions for FDA spreadsheet rows."""

import csv
import io

import pytest

from services.compliance.app import fsma_spreadsheet


@pytest.mark.parametrize("raw", ["x", "1", "bad"])
@pytest.mark.parametrize("origin", ["facility_gln", "location_gln", "ship_from_gln"])
@pytest.mark.parametrize("destination", ["dest_gln", "ship_to_gln"])
def test_spreadsheet_omits_invalid_glns(raw, origin, destination):
    event = {"kdes": {"tlc_source_gln": raw}}
    for key in (origin, destination):
        target = event["kdes"] if key.startswith("ship_") else event
        target[key] = raw

    row = fsma_spreadsheet._normalise_event(event)

    for column in ("origin_gln", "destination_gln", "tlc_source_gln"):
        assert row[column] == ""
    assert row["additional_kdes_json"] == ""


@pytest.mark.parametrize("raw", ["x", "1", "bad"])
def test_spreadsheet_csv_omits_invalid_glns(raw):
    event = {"facility_gln": raw, "dest_gln": raw, "kdes": {"tlc_source_gln": raw}}

    rows = list(csv.reader(io.StringIO(fsma_spreadsheet.generate_fda_csv([event]))))
    header_index = next(index for index, row in enumerate(rows) if row == fsma_spreadsheet.FDA_HEADERS)
    row = dict(zip(fsma_spreadsheet.FDA_COLUMNS, rows[header_index + 1]))

    for column in ("origin_gln", "destination_gln", "tlc_source_gln"):
        assert row[column] == ""


def test_spreadsheet_preserves_filtered_glns(monkeypatch):
    marker = "GLN_MARKER"
    monkeypatch.setattr(fsma_spreadsheet, "gln_for_export", lambda value: marker)

    row = fsma_spreadsheet._normalise_event({})

    for column in ("origin_gln", "destination_gln", "tlc_source_gln"):
        assert row[column] == marker
