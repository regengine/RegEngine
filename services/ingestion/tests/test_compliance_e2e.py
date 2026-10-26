"""Data-free checks for the CSV input previously used by the E2E test."""

from __future__ import annotations

import csv
import io

import pytest
from app.csv_templates import CTE_COLUMNS, parse_csv_rows
from app.shared.xlsx_rows import reject_unsupported_excel
from app.webhook_models import REQUIRED_KDES_BY_CTE, WebhookCTEType
from fastapi import HTTPException


def _header_only_csv() -> str:
    output = io.StringIO()
    csv.writer(output).writerow([name for name, _example, _description in CTE_COLUMNS["harvesting"]])
    return output.getvalue()


def test_harvest_header_only_has_no_events():
    events, errors, warnings = parse_csv_rows(_header_only_csv(), fallback_cte="harvesting")
    assert events == []
    assert errors == []
    assert warnings == []


def test_harvest_template_has_required_headers():
    headers = set(next(csv.reader(io.StringIO(_header_only_csv()))))
    required = set(REQUIRED_KDES_BY_CTE[WebhookCTEType.HARVESTING])
    assert required <= headers
    assert required - (headers - {"traceability_lot_code"}) == {"traceability_lot_code"}


def test_missing_header_is_rejected():
    events, errors, warnings = parse_csv_rows("\n", fallback_cte="harvesting")
    assert events == []
    assert errors == ["CSV has no header row: the first line must list the column names"]
    assert warnings == []


def test_duplicate_header_is_rejected_without_data_rows():
    header = _header_only_csv().strip()
    events, errors, warnings = parse_csv_rows(f"{header},quantity\n", fallback_cte="harvesting")
    assert events == []
    assert len(errors) == 1 and "duplicate column" in errors[0]
    assert warnings == []


def test_unsupported_content_type_is_rejected():
    with pytest.raises(HTTPException) as excinfo:
        reject_unsupported_excel("manifest.csv", "application/vnd.ms-excel.sheet.macroenabled.12")
    assert excinfo.value.status_code == 415
