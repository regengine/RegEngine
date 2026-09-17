"""EPCIS canonical normalization: lot precedence and transformation inputs.

Before this change ``normalize_epcis_event`` read the lot only from
``epcList``. A TransformationEvent (input/output lists, no epcList) or any
event naming its lot in ILMD was stored as ``"UNKNOWN"``, and the per-input
quantities in ``inputQuantityList`` were dropped, so the canonical store held
a fabricated lot code and no lineage for every EPCIS transformation.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared.canonical_event import CTEType, normalize_epcis_event

TENANT = str(uuid4())


def _transformation(**overrides):
    event = {
        "type": "TransformationEvent",
        "eventTime": "2026-02-28T11:00:00.000-05:00",
        "eventTimeZoneOffset": "-05:00",
        "bizStep": "urn:epcglobal:cbv:bizstep:transforming",
        "bizLocation": {"id": "urn:epc:id:sgln:0614141.00002.0"},
        "transformationID": "urn:uuid:8b4c2f1e-0f4b-4f8c-9a3e-3f0d2c1b7a55",
        "inputEPCList": ["urn:epc:id:sgtin:0614141.107346.2017"],
        "inputQuantityList": [
            {"epcClass": "urn:epc:class:lgtin:0614141.107346.TOM-0226", "quantity": 600, "uom": "KGM"},
            {"epcClass": "urn:epc:class:lgtin:0614141.107350.LET-0226", "quantity": 40},
        ],
        "outputEPCList": ["urn:epc:id:sgtin:0614141.107777.9001"],
        "outputQuantityList": [
            {"epcClass": "urn:epc:class:lgtin:0614141.107777.CHOP01", "quantity": 250.0, "uom": "KGM"}
        ],
        "ilmd": {"cbvmda:lotNumber": "CHOP-01", "fsma:traceabilityLotCode": "SALAD-0226-001"},
    }
    event.update(overrides)
    return event


def test_transformation_takes_tlc_from_ilmd_and_records_inputs():
    canonical = normalize_epcis_event(_transformation(), TENANT)
    assert canonical.event_type is CTEType.TRANSFORMATION
    assert canonical.traceability_lot_code == "SALAD-0226-001"
    assert canonical.quantity == 250.0 and canonical.unit_of_measure == "KGM"
    assert canonical.kdes["input_lot_codes"] == ["TOM-0226", "LET-0226", "2017"]
    inputs = canonical.kdes["inputs"]
    assert inputs[0] == {
        "traceability_lot_code": "TOM-0226",
        "quantity": 600.0,
        "unit_of_measure": "KGM",
        "epc_class": "urn:epc:class:lgtin:0614141.107346.TOM-0226",
    }
    # A quantityElement without uom is a count of instances in EPCIS.
    assert inputs[1]["quantity"] == 40.0 and inputs[1]["unit_of_measure"] == "each"
    # An instance EPC is exactly one item.
    assert inputs[2] == {
        "traceability_lot_code": "2017",
        "quantity": 1.0,
        "unit_of_measure": "each",
        "epc": "urn:epc:id:sgtin:0614141.107346.2017",
    }


def test_transformation_without_ilmd_uses_the_output_lgtin_lot():
    canonical = normalize_epcis_event(_transformation(ilmd={}), TENANT)
    assert canonical.traceability_lot_code == "CHOP01"
    assert canonical.kdes["gtin"]


def test_object_event_prefers_ilmd_tlc_over_sgtin_serial():
    event = {
        "type": "ObjectEvent",
        "eventTime": "2026-03-25T14:30:00Z",
        "action": "OBSERVE",
        "bizStep": "urn:epcglobal:cbv:bizstep:receiving",
        "epcList": ["urn:epc:id:sgtin:0614141.107346.2017"],
        "quantityList": [{"epcClass": "urn:epc:class:lgtin:0614141.107346.ROM-42", "quantity": 12, "uom": "KGM"}],
        "ilmd": {"fsma:traceabilityLotCode": "ROM-42"},
    }
    canonical = normalize_epcis_event(event, TENANT)
    assert canonical.traceability_lot_code == "ROM-42"
    assert "inputs" not in canonical.kdes  # not a transformation


def test_event_without_any_lot_identifier_is_rejected_not_unknown():
    event = {
        "type": "ObjectEvent",
        "eventTime": "2026-03-25T14:30:00Z",
        "action": "OBSERVE",
        "bizStep": "urn:epcglobal:cbv:bizstep:receiving",
        "epcList": ["urn:epc:id:sscc:0614141.1234567890"],
        "quantity": {"value": 5, "uom": "cases"},
    }
    with pytest.raises(ValueError, match="no lot identifier"):
        normalize_epcis_event(event, TENANT)


def test_event_without_event_time_is_rejected_not_stamped_now():
    with pytest.raises(ValueError, match="eventTime"):
        normalize_epcis_event(_transformation(eventTime=None), TENANT)
