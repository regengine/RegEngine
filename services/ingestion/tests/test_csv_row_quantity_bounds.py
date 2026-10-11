"""Row quantity bounds for CSV ingest rows.

``parse_csv_rows`` must reject non-finite (nan, inf) and non-positive (0,
negative) quantities with a row-specific message. The ``IngestEvent`` model
already requires ``quantity`` to be finite and greater than 0, so these rows
were rejected before, but only with the generic "could not be parsed (see
server logs)" message that names no row cause.
"""

from __future__ import annotations

import pytest
from app.csv_templates import parse_csv_rows

HEADER = (
    "traceability_lot_code,product_description,quantity,unit_of_measure,"
    "harvest_date,location_name,reference_document\n"
)


def _parse(quantity: str):
    row = f"TOM-001,Roma Tomatoes,{quantity},cases,2026-02-26,Valley Fresh Farms,REF-1\n"
    return parse_csv_rows(HEADER + row, "harvesting")


@pytest.mark.parametrize("quantity", ["nan", "NaN", "inf", "-inf", "Infinity"])
def test_non_finite_quantity_rejected_with_clear_message(quantity: str):
    events, errors, _warnings = _parse(quantity)
    assert events == []
    assert len(errors) == 1
    assert "must be a finite number" in errors[0]
    assert "could not be parsed" not in errors[0]


@pytest.mark.parametrize("quantity", ["0", "0.0", "-5", "-0.25"])
def test_non_positive_quantity_rejected_with_clear_message(quantity: str):
    events, errors, _warnings = _parse(quantity)
    assert events == []
    assert len(errors) == 1
    assert "must be greater than 0" in errors[0]
    assert "could not be parsed" not in errors[0]


def test_non_numeric_quantity_keeps_existing_message():
    events, errors, _warnings = _parse("abc")
    assert events == []
    assert len(errors) == 1
    assert "is not a number" in errors[0]


@pytest.mark.parametrize("quantity", ["1", "500", "0.5", "1e3"])
def test_positive_quantity_still_accepted(quantity: str):
    events, errors, _warnings = _parse(quantity)
    assert errors == []
    assert len(events) == 1
    assert events[0].quantity == pytest.approx(float(quantity))
