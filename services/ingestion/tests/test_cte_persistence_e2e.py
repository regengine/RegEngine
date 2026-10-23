"""Data-free boundary checks for legacy CTE persistence and FDA CSV export.

These tests do not create traceability records or connect to a database.
"""

from __future__ import annotations

import csv
import hashlib
import io
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))


def test_store_event_rejects_missing_event_type_before_database_write():
    from shared.cte_persistence import CTEPersistence

    session = MagicMock()
    with pytest.raises(ValueError, match="event_type is required"):
        CTEPersistence(session).store_event(
            tenant_id="",
            event_type="",
            traceability_lot_code="",
            product_description="",
            quantity=None,
            unit_of_measure="",
            event_timestamp="",
        )

    session.execute.assert_not_called()


def test_store_event_rejects_missing_timestamp_before_database_write():
    from shared.cte_persistence import CTEPersistence

    session = MagicMock()
    with pytest.raises(ValueError, match="event_timestamp is required"):
        CTEPersistence(session).store_event(
            tenant_id="",
            event_type="harvesting",
            traceability_lot_code="",
            product_description="",
            quantity=None,
            unit_of_measure="",
            event_timestamp="",
        )

    session.execute.assert_not_called()


def test_verify_chain_empty_result_is_valid():
    from shared.cte_persistence import CTEPersistence

    session = MagicMock()
    session.execute.return_value.fetchall.return_value = []
    session.execute.return_value.fetchone.return_value = (0,)

    result = CTEPersistence(session).verify_chain("")

    assert result.valid is True
    assert result.chain_length == 0
    assert result.cte_events_count == 0
    assert result.errors == []
    assert result.missing_chain_rows == []
    assert session.execute.call_count == 3


def test_query_events_by_tlc_rejects_missing_tenant_before_database_read():
    from shared.cte_persistence import CTEPersistence

    session = MagicMock()
    with pytest.raises(ValueError):
        CTEPersistence(session).query_events_by_tlc("", "")

    session.execute.assert_not_called()


def test_fda_export_csv_empty_input_has_header_only():
    from app.fda_export_service import FDA_COLUMNS, _generate_csv

    rows = list(csv.reader(io.StringIO(_generate_csv([]))))

    assert rows == [FDA_COLUMNS]


def test_fda_export_hash_of_empty_input_is_reproducible():
    from app.fda_export.formatters import generate_csv_and_hash

    first_csv, first_hash = generate_csv_and_hash([])
    second_csv, second_hash = generate_csv_and_hash([])

    assert first_csv == second_csv
    assert first_hash == second_hash
    assert first_hash == hashlib.sha256(first_csv.encode("utf-8")).hexdigest()
