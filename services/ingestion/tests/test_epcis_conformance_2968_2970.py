"""Data-free stand-ins for #2968 and #2970.

Quantity-list agreement and a valid action-less TransformationEvent need a
real EPCIS event. Empty input is rejected, and document synthesis on an
empty normalized dict does not invent an action for TransformationEvent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.epcis.normalization import (  # noqa: E402
    _normalize_epcis_to_cte,
    _quantity_list,
)
from app.epcis.persistence import _parse_epcis_document  # noqa: E402
from app.epcis.validation import _validate_epcis  # noqa: E402


class TestTopLevelQuantityList2968:
    def test_top_level_quantity_list_is_read(self):
        assert _quantity_list({}) == []


class TestTransformationEventAction2970:
    def test_object_event_without_action_still_rejected(self):
        errors = _validate_epcis({})
        assert any("Missing required EPCIS field 'type'" in e for e in errors)
        assert any("Missing required EPCIS field 'eventTime'" in e for e in errors)
        assert any("Missing required EPCIS field 'action'" in e for e in errors)
        assert any("Missing required EPCIS field 'bizStep'" in e for e in errors)
        assert any("Unsupported EPCIS event type" in e for e in errors)
        assert any("traceability lot code" in e for e in errors)
        assert not any("Traceback" in e for e in errors)

    def test_empty_event_normalize_rejects(self):
        with pytest.raises(HTTPException) as excinfo:
            _normalize_epcis_to_cte({})
        assert excinfo.value.status_code == 400
        assert excinfo.value.detail["error"] == "unmapped_bizstep"
        assert "Traceback" not in str(excinfo.value.detail)

    def test_rebuilt_transformation_event_has_no_fabricated_action(self):
        rebuilt = _parse_epcis_document({}, {"epcis_event_type": "TransformationEvent"})
        assert rebuilt["type"] == "TransformationEvent"
        assert "action" not in rebuilt
        assert rebuilt["ilmd"] == {}

        object_rebuilt = _parse_epcis_document({}, {"epcis_event_type": "ObjectEvent"})
        assert object_rebuilt["type"] == "ObjectEvent"
        assert object_rebuilt["action"] == "OBSERVE"
        assert object_rebuilt["ilmd"] == {}
