"""``_create_transformation_links`` records lineage for initial packing too.

The CSV templates give both ``transformation`` (§1.1350) and
``initial_packing`` (§1.1330) rows an ``input_lot_codes`` column. The link
writer used to return early for anything but a transformation, so a packed
TLC's connection to its source lots was silently dropped and never showed
in ``trace_backward``.

Mocking style: ``object.__new__(CanonicalEventStore)`` + a MagicMock
session, matching ``test_canonical_persistence_meter_usage.py``. No live DB.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.shared.canonical_persistence.writer import CanonicalEventStore

TENANT_ID = "00000000-0000-0000-0000-00000000c0de"


def _make_writer() -> tuple[CanonicalEventStore, MagicMock]:
    writer = object.__new__(CanonicalEventStore)
    session = MagicMock()
    # The "latest event for this input TLC" lookup finds nothing: the
    # input lot was never ingested, which must not prevent the link row.
    session.execute.return_value.fetchone.return_value = None
    writer.session = session
    return writer, session


def _make_event(event_type: str, kdes: dict) -> SimpleNamespace:
    return SimpleNamespace(
        event_type=SimpleNamespace(value=event_type),
        kdes=kdes,
        tenant_id=TENANT_ID,
        traceability_lot_code="TLC-OUT-001",
        event_id="11111111-1111-4111-8111-111111111111",
        quantity=40.0,
        unit_of_measure="cases",
    )


def _inserts(session: MagicMock) -> list[dict]:
    """Parameters of every INSERT INTO fsma.transformation_links issued."""
    rows = []
    for call in session.execute.call_args_list:
        statement = str(call.args[0])
        if "INSERT INTO fsma.transformation_links" in statement:
            rows.append(call.args[1])
    return rows


@pytest.mark.parametrize(
    ("event_type", "expected_process_type"),
    [
        ("transformation", None),  # unchanged: process_type only if the row supplied one
        ("initial_packing", "initial_packing"),  # new: packing lineage is recorded
    ],
)
def test_events_naming_input_lots_create_links(event_type, expected_process_type):
    writer, session = _make_writer()
    writer._create_transformation_links(_make_event(event_type, {"input_lot_codes": ["TLC-IN-001", "TLC-IN-002"]}))

    rows = _inserts(session)
    assert [r["input_tlc"] for r in rows] == ["TLC-IN-001", "TLC-IN-002"]
    assert all(r["output_tlc"] == "TLC-OUT-001" for r in rows)
    assert all(r["process_type"] == expected_process_type for r in rows)
    assert all(r["link_source"] == "explicit" for r in rows)


def test_explicit_process_type_on_packing_row_is_kept():
    writer, session = _make_writer()
    writer._create_transformation_links(
        _make_event("initial_packing", {"input_lot_codes": ["TLC-IN-001"], "process_type": "field_pack"})
    )
    assert [r["process_type"] for r in _inserts(session)] == ["field_pack"]


@pytest.mark.parametrize("event_type", ["receiving", "shipping", "harvesting", "cooling"])
def test_other_event_types_still_create_no_links(event_type):
    writer, session = _make_writer()
    writer._create_transformation_links(_make_event(event_type, {"input_lot_codes": ["TLC-IN-001"]}))
    assert _inserts(session) == []


def test_packing_row_without_input_lots_creates_no_links():
    writer, session = _make_writer()
    writer._create_transformation_links(_make_event("initial_packing", {}))
    assert _inserts(session) == []


def test_input_quantities_from_kdes_inputs_are_written_on_the_link():
    writer, session = _make_writer()
    writer._create_transformation_links(
        _make_event(
            "transformation",
            {
                "input_lot_codes": ["TLC-IN-001", "TLC-IN-002", "TLC-IN-003"],
                "inputs": [
                    {"traceability_lot_code": "TLC-IN-001", "quantity": 600, "unit_of_measure": "cases"},
                    {"traceability_lot_code": "TLC-IN-002", "quantity": 400.5, "unit_of_measure": "lbs"},
                    # TLC-IN-003 has no recorded quantity: the link stays NULL, never inferred.
                ],
            },
        )
    )
    rows = _inserts(session)
    assert [(r["input_tlc"], r["input_quantity"], r["input_unit"]) for r in rows] == [
        ("TLC-IN-001", 600.0, "cases"),
        ("TLC-IN-002", 400.5, "lbs"),
        ("TLC-IN-003", None, None),
    ]
    assert all(
        "input_quantity" in str(c.args[0])
        for c in session.execute.call_args_list
        if "INSERT INTO fsma.transformation_links" in str(c.args[0])
    )
