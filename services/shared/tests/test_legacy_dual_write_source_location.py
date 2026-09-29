"""Keep source location names distinct from identifiers in legacy exports."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from shared.canonical_event import normalize_webhook_event
from shared.canonical_persistence.legacy_dual_write import dual_write_legacy

from tests.shared.test_canonical_persistence_hardening import FakeSession, _make_event


def _persisted_location(event):
    session = FakeSession()
    dual_write_legacy(session, event)
    return next(params for sql, params in session.calls if "INSERT INTO fsma.cte_events" in sql)


@pytest.mark.parametrize("name", ["Source Farm", "  Source Farm  "])
def test_source_name_is_not_replaced_by_gln_after_normalization(name):
    source = SimpleNamespace(
        cte_type="shipping",
        traceability_lot_code="SOURCE-LOT-001",
        product_description="Fresh basil",
        quantity=12.5,
        unit_of_measure="cases",
        timestamp=datetime(2026, 3, 1, tzinfo=timezone.utc),
        location_gln="0614141000005",
        location_name=name,
        kdes={},
    )
    event = normalize_webhook_event(source, str(uuid4()))
    original = event.model_dump()

    params = _persisted_location(event)

    assert params["location_gln"] == "0614141000005"
    assert params["location_name"] == name
    assert event.model_dump() == original


def test_name_only_webhook_does_not_fabricate_a_gln():
    source = SimpleNamespace(
        cte_type="shipping",
        traceability_lot_code="SOURCE-LOT-002",
        product_description="Fresh basil",
        quantity=12.5,
        unit_of_measure="cases",
        timestamp=datetime(2026, 3, 1, tzinfo=timezone.utc),
        location_gln=None,
        location_name="Source Farm",
        kdes={},
    )
    event = normalize_webhook_event(source, str(uuid4()))

    params = _persisted_location(event)

    assert params["location_gln"] is None
    assert params["location_name"] == "Source Farm"


@pytest.mark.parametrize("name", [None, "", "  ", 42])
def test_unusable_source_name_falls_back_to_canonical_reference(name):
    event = _make_event()
    event.raw_payload = {"location_name": name}

    params = _persisted_location(event)

    assert params["location_gln"] == "urn:gs1:414:0614141000005"
    assert params["location_name"] == "urn:gs1:414:0614141000005"


@pytest.mark.parametrize(
    ("reference", "expected_gln"),
    [
        ("Source Farm", None),
        ("Warehouse-123", None),
        ("0614141000005", "0614141000005"),
        ("0614141000005.0", "0614141000005.0"),
        ("urn:epc:id:sgln:0614141.00001.0", "urn:epc:id:sgln:0614141.00001.0"),
        ("urn:gs1:414:0614141000005", "urn:gs1:414:0614141000005"),
        ("https://id.gs1.org/414/0614141000005", "https://id.gs1.org/414/0614141000005"),
        (None, None),
    ],
)
@pytest.mark.parametrize("direction", ["from", "to"])
def test_canonical_fallback_preserves_identifiers_without_promoting_names(reference, expected_gln, direction):
    event = _make_event()
    event.raw_payload = {}
    event.from_facility_reference = reference if direction == "from" else None
    event.to_facility_reference = reference if direction == "to" else None

    params = _persisted_location(event)

    assert params["location_gln"] == expected_gln
    assert params["location_name"] == reference


def test_explicit_source_location_is_not_replaced_by_directional_reference():
    event = _make_event()
    event.raw_payload = {"location_gln": "0614141000098", "location_name": "Source Farm"}

    params = _persisted_location(event)

    assert params["location_gln"] == "0614141000098"
    assert params["location_name"] == "Source Farm"
