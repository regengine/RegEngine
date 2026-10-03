"""Per-input quantities on transformation / initial packing CSV rows.

21 CFR 1.1350(a)(1)(iii) requires the quantity and unit of measure of each
input lot. The template gains ``input_quantities`` and
``input_units_of_measure`` aligned with ``input_lot_codes``; the parser folds
them into ``kdes.inputs`` and rejects rows whose values cannot be attributed
to a lot rather than guessing.
"""

from __future__ import annotations

import csv
import io

import pytest
from app.csv_templates import CTE_COLUMNS, _generate_csv_template, parse_csv_rows

HEADER = (
    "traceability_lot_code,product_description,quantity,unit_of_measure,"
    "transformation_date,location_name,reference_document,input_lot_codes,"
    "input_quantities,input_units_of_measure\n"
)


def _parse(row: str, cte: str = "transformation"):
    return parse_csv_rows(HEADER + row, cte)


def test_template_serves_the_new_columns_with_example_values():
    for cte in ("transformation", "initial_packing"):
        header, example = list(csv.reader(io.StringIO(_generate_csv_template(cte))))[:2]
        by_col = dict(zip(header, example))
        assert "input_quantities" in header and "input_units_of_measure" in header, cte
        assert by_col["input_quantities"].strip() and by_col["input_units_of_measure"].strip(), cte
        # One quantity per input lot in the example row.
        lots = [c for c in by_col["input_lot_codes"].split(",") if c.strip()]
        assert len(by_col["input_quantities"].split(",")) == len(lots), cte
    assert [c[0] for c in CTE_COLUMNS["transformation"]].index("input_quantities") > [
        c[0] for c in CTE_COLUMNS["transformation"]
    ].index("input_lot_codes")


def test_aligned_quantities_become_kdes_inputs():
    events, errors, warnings = _parse('NEW1,Mix,100,bags,2026-04-17,Plant A,REF,"LOT1,LOT2","600,400","cases,lb"\n')
    assert errors == []
    assert not any("input_quantities" in w for w in warnings)
    ev = events[0]
    assert ev.kdes["input_lot_codes"] == ["LOT1", "LOT2"]
    assert ev.kdes["inputs"] == [
        {"traceability_lot_code": "LOT1", "quantity": 600.0, "unit_of_measure": "cases"},
        {"traceability_lot_code": "LOT2", "quantity": 400.0, "unit_of_measure": "lbs"},  # alias normalised
    ]
    # The raw columns are folded into inputs, not copied as loose KDEs.
    assert "input_quantities" not in ev.kdes and "input_units_of_measure" not in ev.kdes


def test_single_unit_applies_to_every_input_lot():
    events, errors, _ = _parse('NEW1,Mix,100,bags,2026-04-17,Plant A,REF,"LOT1,LOT2","600,400",cases\n')
    assert errors == []
    assert [i["unit_of_measure"] for i in events[0].kdes["inputs"]] == ["cases", "cases"]


def test_misaligned_quantities_reject_the_row_instead_of_guessing():
    events, errors, _ = _parse('NEW1,Mix,100,bags,2026-04-17,Plant A,REF,"LOT1,LOT2",600,cases\n')
    assert events == []
    assert len(errors) == 1
    assert "1 value(s) for 2 input lot(s)" in errors[0]


def test_non_numeric_quantity_rejects_the_row():
    events, errors, _ = _parse('NEW1,Mix,100,bags,2026-04-17,Plant A,REF,"LOT1,LOT2","six hundred,400",cases\n')
    assert events == []
    assert "not a number" in errors[0] and "LOT1" in errors[0]


def test_quantities_without_lots_reject_the_row():
    events, errors, _ = _parse("NEW1,Mix,100,bags,2026-04-17,Plant A,REF,,600,cases\n")
    assert events == []
    assert "without input_lot_codes" in errors[0]


def test_transformation_without_input_quantities_ingests_with_a_warning():
    events, errors, warnings = _parse('NEW1,Mix,100,bags,2026-04-17,Plant A,REF,"LOT1,LOT2",,\n')
    assert errors == []
    assert events[0].kdes["input_lot_codes"] == ["LOT1", "LOT2"]
    assert "inputs" not in events[0].kdes
    assert any("input_quantities missing" in w and "1.1350(a)(1)(iii)" in w for w in warnings)


def test_initial_packing_inputs_are_optional_and_silent_when_absent():
    header = (
        "traceability_lot_code,product_description,quantity,unit_of_measure,packing_date,location_name,"
        "input_lot_codes,reference_document,harvester_business_name,harvester_business_phone\n"
    )
    events, errors, warnings = parse_csv_rows(
        header + "PACK1,Tomatoes,200,cases,2026-02-26,Packhouse,FIELD-LOT-1,PACK-1,Farm LLC,+1-202-555-0100\n",
        "initial_packing",
    )
    assert errors == []
    assert events[0].kdes["input_lot_codes"] == ["FIELD-LOT-1"]
    assert not any("input_quantities" in w for w in warnings)


@pytest.mark.parametrize("quantity", ["0", "0.25", "1000000"])
def test_finite_nonnegative_input_quantities_remain_accepted(quantity):
    # BE-002 preserves the existing input domain, including zero.
    events, errors, _ = _parse(f"NEW1,Mix,100,bags,2026-04-17,Plant A,REF,LOT1,{quantity},cases\n")
    assert errors == []
    assert events[0].kdes["inputs"][0]["quantity"] == float(quantity)


def test_negative_input_quantity_remains_rejected():
    events, errors, _ = _parse("NEW1,Mix,100,bags,2026-04-17,Plant A,REF,LOT1,-1,cases\n")
    assert events == []
    assert "is negative" in errors[0]
