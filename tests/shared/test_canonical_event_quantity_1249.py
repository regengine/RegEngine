"""Regression tests for #1249 — EPCIS canonical quantity must not be
silently fabricated or silently dropped.

Before the fix, ``normalize_epcis_event`` did two wrong things:

    1. It looked for ``epcis_data["quantity"]["value"]``, which is NOT
       where real EPCIS 2.0 events carry quantity (the real shape is
       ``extension.quantityList[0].quantity``). For every production
       EPCIS event, the extraction failed and the function silently
       defaulted to ``1.0``. The canonical row — which FDA export and
       the rules engine read from — claimed a 1-unit event regardless
       of what the shipper actually reported.

    2. The ``TraceabilityEvent.quantity`` Pydantic field was declared
       ``gt=0``, so any legitimate zero-quantity event (empty pallet,
       full recall correction, zero-loss inspection) raised on canonical
       write. The raise was swallowed by a best-effort try/except in
       ``_persist_prepared_event_in_session``, so the event was stored
       in ``fsma.cte_events`` but missing from ``traceability_events``.
       FDA exports run off canonical and so would have omitted the zero.

Both failure modes falsified FDA 204 traceability records. This test
file pins the new contract:

    * ``_extract_epcis_quantity`` parses the real EPCIS shape AND the
      flat legacy shape, and returns ``(None, ...)`` when neither
      carries a numeric quantity (never fabricates).
    * ``normalize_epcis_event`` raises :class:`ValueError` rather than
      defaulting to ``1.0`` on missing / non-numeric quantity.
    * ``TraceabilityEvent.quantity`` accepts zero.
    * The canonical row preserves the true quantity end-to-end for
      both EPCIS shapes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from shared.canonical_event import (
    CTEType,
    IngestionSource,
    TraceabilityEvent,
    _extract_epcis_quantity,
    _require_epcis_quantity,
    normalize_epcis_event,
)


TENANT_ID = str(uuid4())


# ─────────────────────────────────────────────────────────────────────
# TraceabilityEvent schema — zero is now legal
# ─────────────────────────────────────────────────────────────────────


def _minimal_traceability_event(quantity: float) -> TraceabilityEvent:
    """Build the smallest legal TraceabilityEvent that pins the field
    under test. Keep required fields together so the test stays honest
    if the schema grows new required fields."""
    return TraceabilityEvent(
        tenant_id=uuid4(),
        source_system=IngestionSource.EPCIS_API,
        event_type=CTEType.RECEIVING,
        event_timestamp=datetime.now(timezone.utc),
        traceability_lot_code="00012345678901-ROMZERO",
        quantity=quantity,
        unit_of_measure="CS",
    )


def test_traceability_event_accepts_zero_quantity():
    """#1249: zero is a legitimate FSMA quantity (empty pallet, full
    recall correction, zero-loss inspection). It must round-trip
    through the canonical model without raising."""
    evt = _minimal_traceability_event(0.0)
    assert evt.quantity == 0.0


def test_traceability_event_accepts_positive_quantity():
    """Happy path — don't regress the normal case."""
    evt = _minimal_traceability_event(42.5)
    assert evt.quantity == 42.5


def test_traceability_event_rejects_negative_quantity():
    """Negative quantities have no well-defined FSMA 204 semantics
    (EPCIS quantity is a count, not a signed transfer). The schema
    stays ``ge=0`` — reversals/corrections are modeled as separate
    CTE events, not as signed numeric quantities."""
    with pytest.raises(ValidationError):
        _minimal_traceability_event(-1.0)


# ─────────────────────────────────────────────────────────────────────
# _extract_epcis_quantity — parses real + flat shapes, never fabricates
# ─────────────────────────────────────────────────────────────────────


def test_extract_real_epcis_shape():
    """The actual EPCIS 2.0 wire format — quantityList nested under
    ``extension``. This is what every production event looks like and
    is exactly the shape the old code silently missed (defaulting
    everyone to 1.0)."""
    event = {
        "extension": {
            "quantityList": [
                {"epcClass": "urn:epc:class:lgtin:test", "quantity": 10.0, "uom": "CS"}
            ]
        }
    }
    assert _extract_epcis_quantity(event) == (10.0, "CS")


def test_extract_top_level_quantity_list():
    """Some shims flatten the structure one level; still should parse.
    The point is we accept every reasonable carrier rather than
    falling through to a silent default."""
    event = {
        "quantityList": [{"quantity": 5.5, "uom": "kg"}]
    }
    assert _extract_epcis_quantity(event) == (5.5, "kg")


def test_extract_flat_shape_used_by_legacy_tests():
    """Existing test fixtures use ``quantity: {value, uom}``. Keep that
    working so we don't break downstream tests while we migrate them.
    This shape is NOT valid EPCIS 2.0 but it's the path the old
    fabrication code was written against."""
    event = {"quantity": {"value": 12.0, "uom": "lbs"}}
    assert _extract_epcis_quantity(event) == (12.0, "lbs")


def test_extract_missing_quantity_returns_none_not_fabricated():
    """#1249 core: no quantity anywhere → ``(None, None)``. We must
    NEVER default to 1.0 or any other value. The caller decides what
    to do (reject vs. preserve source-of-truth). The old code's silent
    1.0 default is the exact falsification pattern this issue tracks."""
    assert _extract_epcis_quantity({}) == (None, None)
    assert _extract_epcis_quantity({"extension": {}}) == (None, None)
    assert _extract_epcis_quantity({"extension": {"quantityList": []}}) == (None, None)
    # Quantity key present but value is None
    assert _extract_epcis_quantity({"quantity": {"value": None}}) == (None, None)


def test_extract_non_numeric_quantity_returns_none():
    """Strings, booleans, dicts, lists — anything that can't be cast to
    float must not silently coerce. Returning None here is what lets
    ``_require_epcis_quantity`` raise a clear error."""
    bad_values = ["banana", {"nested": "dict"}, [1, 2, 3], object()]
    for bad in bad_values:
        event = {"extension": {"quantityList": [{"quantity": bad, "uom": "CS"}]}}
        value, _uom = _extract_epcis_quantity(event)
        assert value is None, f"non-numeric value {bad!r} must not coerce"


def test_extract_zero_is_preserved_not_treated_as_missing():
    """Zero is not the same as missing. Pin this — a past version of
    this code used truthiness checks (``if not quantity:``) that
    collapsed 0 into the missing bucket, silently rewriting zero to
    the default."""
    event = {"extension": {"quantityList": [{"quantity": 0, "uom": "CS"}]}}
    assert _extract_epcis_quantity(event) == (0.0, "CS")


def test_extract_negative_is_preserved_numerically():
    """The extractor does NOT enforce sign — that's the schema's job.
    We preserve what the source reported so the rejection happens at
    a single well-defined layer (TraceabilityEvent.quantity's ge=0)."""
    event = {"extension": {"quantityList": [{"quantity": -3, "uom": "CS"}]}}
    assert _extract_epcis_quantity(event) == (-3.0, "CS")


# ─────────────────────────────────────────────────────────────────────
# _require_epcis_quantity — raises instead of fabricating
# ─────────────────────────────────────────────────────────────────────


def test_require_quantity_raises_on_missing():
    """#1249 core: the old code silently produced ``1.0`` here. The
    new contract is that callers must supply a quantity or get a loud
    failure — fabrication is what falsified FDA records."""
    with pytest.raises(ValueError, match="no numeric quantity"):
        _require_epcis_quantity({})


def test_require_quantity_raises_on_non_numeric():
    event = {"extension": {"quantityList": [{"quantity": "not-a-number", "uom": "CS"}]}}
    with pytest.raises(ValueError, match="no numeric quantity"):
        _require_epcis_quantity(event)


def test_require_quantity_returns_zero_when_explicit():
    """Zero is valid. The "require" in the name is about presence, not
    positivity — that's enforced downstream by the schema."""
    event = {"extension": {"quantityList": [{"quantity": 0, "uom": "CS"}]}}
    assert _require_epcis_quantity(event) == 0.0


# ─────────────────────────────────────────────────────────────────────
# normalize_epcis_event — end-to-end quantity preservation
# ─────────────────────────────────────────────────────────────────────


_REAL_EPCIS_SHIPPING_EVENT = {
    "type": "ObjectEvent",
    "eventTime": "2026-02-28T09:30:00.000-05:00",
    "eventTimeZoneOffset": "-05:00",
    "action": "OBSERVE",
    "bizStep": "urn:epcglobal:cbv:bizstep:shipping",
    "bizLocation": {"id": "urn:epc:id:sgln:0614141.00002.0"},
    "epcList": ["urn:epc:id:sgtin:0614141.107346.ROM0042"],
    "ilmd": {"fsma:traceabilityLotCode": "00012345678901-ROM0042"},
}


def test_normalize_preserves_real_epcis_quantity():
    """The one-line summary of #1249: production EPCIS events (using
    ``extension.quantityList``) used to get rewritten to ``quantity=1``
    in canonical because the extractor was looking at the wrong key.
    This is the single regression test that would have caught it."""
    event = dict(_REAL_EPCIS_SHIPPING_EVENT)
    event["extension"] = {
        "quantityList": [{"quantity": 42.0, "uom": "CS"}]
    }

    canonical = normalize_epcis_event(event, TENANT_ID)
    assert canonical.quantity == 42.0, (
        "real-EPCIS-shape quantity must round-trip into canonical. "
        "A regression here means every production EPCIS event is "
        "being recorded as quantity=1 (#1249)."
    )
    assert canonical.unit_of_measure == "CS"


def test_normalize_preserves_zero_quantity():
    """Zero-quantity events must reach the canonical store — not be
    silently dropped. Pre-fix, the ``gt=0`` constraint raised and the
    caller's best-effort try/except swallowed the exception, leaving
    the event in cte_events but missing from traceability_events."""
    event = dict(_REAL_EPCIS_SHIPPING_EVENT)
    event["extension"] = {"quantityList": [{"quantity": 0.0, "uom": "CS"}]}

    canonical = normalize_epcis_event(event, TENANT_ID)
    assert canonical.quantity == 0.0


def test_normalize_raises_on_missing_quantity():
    """No quantity anywhere → ValueError. The old code returned a
    canonical row with ``quantity=1`` — the regulator-visible
    falsification this issue tracks."""
    event = dict(_REAL_EPCIS_SHIPPING_EVENT)
    event.pop("extension", None)
    event.pop("quantity", None)

    with pytest.raises(ValueError):
        normalize_epcis_event(event, TENANT_ID)


def test_normalize_raises_on_non_numeric_quantity():
    event = dict(_REAL_EPCIS_SHIPPING_EVENT)
    event["extension"] = {"quantityList": [{"quantity": "banana", "uom": "CS"}]}

    with pytest.raises(ValueError):
        normalize_epcis_event(event, TENANT_ID)


def test_normalize_rejects_negative_at_schema_boundary():
    """Extraction preserves the sign; the schema rejects it. Two-layer
    separation means the error fires at a well-defined spot regardless
    of which ingestion path produced the event."""
    event = dict(_REAL_EPCIS_SHIPPING_EVENT)
    event["extension"] = {"quantityList": [{"quantity": -5.0, "uom": "CS"}]}

    # ValidationError from Pydantic when building the TraceabilityEvent
    with pytest.raises(ValidationError):
        normalize_epcis_event(event, TENANT_ID)


def test_normalize_flat_shape_still_works():
    """Don't break the legacy/test shape as a side effect of fixing
    the real-shape path."""
    event = dict(_REAL_EPCIS_SHIPPING_EVENT)
    event["quantity"] = {"value": 7.5, "uom": "kg"}

    canonical = normalize_epcis_event(event, TENANT_ID)
    assert canonical.quantity == 7.5
    assert canonical.unit_of_measure == "kg"


def test_normalize_prefers_real_shape_over_flat():
    """If both shapes are present (shouldn't happen in practice but
    test fixtures can drift), the real EPCIS shape wins — it's what
    production data actually uses."""
    event = dict(_REAL_EPCIS_SHIPPING_EVENT)
    event["extension"] = {"quantityList": [{"quantity": 100.0, "uom": "CS"}]}
    event["quantity"] = {"value": 999.0, "uom": "WRONG"}

    canonical = normalize_epcis_event(event, TENANT_ID)
    assert canonical.quantity == 100.0
    assert canonical.unit_of_measure == "CS"
