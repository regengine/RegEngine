"""Data-free evidence export checks after removal of row-based fixtures."""

import csv
import io

from app.remediation.evidence import _accepted_csv


def test_empty_evidence_csv_has_headers_only():
    rows = list(csv.reader(io.StringIO(_accepted_csv([]))))
    assert len(rows) == 1
    assert "event_date" in rows[0]
