"""#2970 follow-up: EPCIS quantity extraction contract, data-free.

#2970 made the EPCIS required-field set depend on event type, so a
``TransformationEvent`` (quantities in ``inputQuantityList`` /
``outputQuantityList``) now reaches
``shared.canonical_event._extract_epcis_quantity``. These tests pin the
parts of that contract that need no event records: absent or empty
quantity members never yield a fabricated quantity (#1249), the strict
wrapper raises, and the two writers agree when no quantity exists.
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

# Every member the extractor reads a quantity list from, each present but empty.
EMPTY_QUANTITY_SHAPES = [
    pytest.param({}, id="no-members"),
    pytest.param({"extension": {"quantityList": []}}, id="extension-quantityList"),
    pytest.param({"quantityList": []}, id="quantityList"),
    pytest.param({"outputQuantityList": []}, id="outputQuantityList"),
    pytest.param({"inputQuantityList": []}, id="inputQuantityList"),
]


class TestQuantityExtractionEmptyInput2970:
    @pytest.mark.parametrize("event", EMPTY_QUANTITY_SHAPES)
    def test_no_quantity_is_fabricated(self, event) -> None:
        """#1249: absent or empty quantity lists yield (None, None)."""
        assert _extract_epcis_quantity(event) == (None, None)

    @pytest.mark.parametrize("event", EMPTY_QUANTITY_SHAPES)
    def test_require_raises_when_no_quantity_exists(self, event) -> None:
        with pytest.raises(ValueError):
            _require_epcis_quantity(event)


class TestWritersAgreeEmptyInput2970:
    """normalization.py's comment claims it agrees with canonical_event on
    every event. Pin it on events that carry no quantity."""

    def test_normalizer_rejects_empty_event(self) -> None:
        from app.epcis.normalization import _normalize_epcis_to_cte
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _normalize_epcis_to_cte({})
        assert exc_info.value.status_code == 400

    @pytest.mark.parametrize("event", EMPTY_QUANTITY_SHAPES)
    def test_both_writers_extract_no_quantity(self, event) -> None:
        from app.epcis.normalization import _EVENT_TYPE_MAP, _normalize_epcis_to_cte

        # Any mapped bizStep from the production map; no event data is invented.
        event = {**event, "bizStep": next(iter(_EVENT_TYPE_MAP))}
        shared_value, shared_uom = _extract_epcis_quantity(event)
        normalized = _normalize_epcis_to_cte(event)

        assert (shared_value, shared_uom) == (None, None)
        assert normalized["quantity"] is None
        assert normalized["unit_of_measure"] is None
