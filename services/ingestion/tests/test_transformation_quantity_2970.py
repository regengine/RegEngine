"""#2970 follow-up: a conformant EPCIS 2.0 TransformationEvent must not 500.

#2970 made the EPCIS required-field set depend on event type, because
``TransformationEvent`` has no ``action`` member and requiring it
unconditionally made a mandatory FSMA 204 CTE unreachable. That fix was
correct, but it opened a path that had never been exercised: such an event
now passes validation and reaches
``shared.canonical_event._extract_epcis_quantity``, which only read
``extension.quantityList`` / ``quantityList``. A TransformationEvent has
neither — its quantities live in ``inputQuantityList`` /
``outputQuantityList`` — so the canonical writer raised ``ValueError`` and
the route returned 500 on a *conformant* event.

``epcis/normalization.py`` was updated for this in the same change and its
comment already asserts the two writers "agree on every event". These tests
pin that claim rather than trusting it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.canonical_event import (  # noqa: E402
    _extract_epcis_quantity,
    _require_epcis_quantity,
)


def _transformation_event(**overrides):
    """A conformant EPCIS 2.0 TransformationEvent: no `action`, no `quantityList`."""
    event = {
        "type": "TransformationEvent",
        "eventTime": "2026-08-27T00:00:00Z",
        "bizStep": "urn:epcglobal:cbv:bizstep:commissioning",
        "inputQuantityList": [
            {"epcClass": "urn:regengine:lot:IN-1", "quantity": 100.0, "uom": "KGM"}
        ],
        "outputQuantityList": [
            {"epcClass": "urn:regengine:lot:OUT-1", "quantity": 95.0, "uom": "KGM"}
        ],
    }
    event.update(overrides)
    return event


class TestTransformationQuantityExtraction2970:
    def test_output_quantity_is_extracted_not_none(self) -> None:
        """The regression: this returned (None, None) and 500'd the route."""
        assert _extract_epcis_quantity(_transformation_event()) == (95.0, "KGM")

    def test_require_does_not_raise_on_a_conformant_transformation(self) -> None:
        assert _require_epcis_quantity(_transformation_event()) == 95.0

    def test_output_list_wins_over_input_list(self) -> None:
        """For a transformation CTE the FSMA quantity is the lot it creates,
        so the output list must take precedence over the input list."""
        value, uom = _extract_epcis_quantity(_transformation_event())
        assert (value, uom) == (95.0, "KGM"), "input quantity leaked into the CTE"

    def test_input_list_used_when_there_is_no_output_list(self) -> None:
        event = _transformation_event()
        del event["outputQuantityList"]
        assert _extract_epcis_quantity(event) == (100.0, "KGM")

    def test_top_level_quantity_list_still_wins_over_transformation_lists(self) -> None:
        """Precedence must not regress for events carrying both."""
        event = _transformation_event(
            quantityList=[{"epcClass": "urn:regengine:lot:X", "quantity": 7.0, "uom": "EA"}]
        )
        assert _extract_epcis_quantity(event) == (7.0, "EA")

    def test_extension_wrapper_still_wins_over_everything(self) -> None:
        """The EPCIS 1.x XML shape keeps top precedence (#2968)."""
        event = _transformation_event(
            extension={"quantityList": [{"epcClass": "u", "quantity": 3.0, "uom": "LBR"}]},
            quantityList=[{"epcClass": "u", "quantity": 7.0, "uom": "EA"}],
        )
        assert _extract_epcis_quantity(event) == (3.0, "LBR")

    def test_still_raises_when_no_quantity_exists_anywhere(self) -> None:
        """#1249's contract is unchanged: never fabricate a quantity."""
        event = _transformation_event()
        del event["inputQuantityList"]
        del event["outputQuantityList"]
        assert _extract_epcis_quantity(event) == (None, None)
        with pytest.raises(ValueError):
            _require_epcis_quantity(event)


class TestWritersAgree2970:
    """normalization.py's comment claims it agrees with canonical_event on
    every event. Pin it instead of trusting the comment."""

    def test_both_writers_extract_the_same_quantity(self) -> None:
        from services.ingestion.app.epcis.normalization import _normalize_epcis_to_cte

        event = _transformation_event()
        shared_value, shared_uom = _extract_epcis_quantity(event)
        normalized = _normalize_epcis_to_cte(event)

        assert normalized["quantity"] == shared_value
        assert normalized["unit_of_measure"] == shared_uom
