"""Routing envelopes must retain every extracted CTE and KDE field."""

import json
from copy import deepcopy
from dataclasses import fields

import pytest

from services.nlp.app.extractors.fsma_extractor import FSMAExtractor
from services.nlp.app.extractors.fsma_types import (
    CTE,
    KDE,
    CTEType,
    DocumentType,
    ExtractionConfidence,
    FSMAExtractionResult,
)

KDE_VALUES = {
    "traceability_lot_code": "ORIGIN-LOT-001",
    "product_description": "Romaine — whole heads",
    "quantity": 0.0,
    "unit_of_measure": "cases",
    "location_identifier": "urn:epc:id:sgln:0614141.12345.0",
    "event_date": "2026-09-28",
    "event_time": "",
    "ship_from_location": "Farm packing house",
    "ship_to_location": "Distribution center",
    "tlc_source_gln": "0614141123452",
    "tlc_source_fda_reg": "12345678901",
    "ship_from_gln": "0614141123452",
    "ship_to_gln": "0614141987652",
    "gtin": "00012345678901",
    "harvester_identifier": "HARVESTER-17",
    "field_identifier": "FIELD-8",
    "harvest_date": "2026-09-27",
    "cooling_location": "Cooler A",
    "cooling_temperature": "0 C",
    "packing_location": "Packing line 2",
    "harvest_location_ref": "Farm north field",
    "entry_point": "Dock 3",
    "source_vessel_name": "Vessel One",
    "prior_source_tlc": "PRIOR-ORIGIN-LOT",
    "is_ftl_covered": True,
    "ftl_category": "Leafy greens",
}
SOURCE_TEXT = "Lot: ORIGIN-LOT-001\nQuantity: 0 cases\nTemperature: 0 C"
BOUNDING_BOX = {"x": 0.0, "y": 4.5, "width": 0.0, "height": 6.0}


def _result(ctes, review_required):
    return FSMAExtractionResult(
        document_id="document-lossless",
        tenant_id="11111111-1111-1111-1111-111111111111",
        document_type=DocumentType.BILL_OF_LADING,
        ctes=ctes,
        extraction_timestamp="2026-09-28T12:00:00Z",
        warnings=["Original extraction warning"],
        confidence_level=(ExtractionConfidence.LOW if review_required else ExtractionConfidence.HIGH),
        review_required=review_required,
    )


@pytest.mark.parametrize("review_required", [False, True], ids=["graph", "review"])
@pytest.mark.parametrize("ftl_covered", [True, False, None], ids=["ftl", "non-ftl", "unknown"])
def test_routing_preserves_all_cte_fields_and_json_values(review_required, ftl_covered):
    # Explicit values make a dropped, renamed, or coerced field observable.
    expected_kdes = {**KDE_VALUES, "is_ftl_covered": ftl_covered}
    assert set(expected_kdes) == {field.name for field in fields(KDE)}
    cte = CTE(
        type=CTEType.COOLING,
        kdes=KDE(**expected_kdes),
        confidence=0.0,
        source_text=SOURCE_TEXT,
        bounding_box=BOUNDING_BOX.copy(),
        event_id="stable-event-001",
    )
    result = _result([cte], review_required)
    original = deepcopy(result)

    routing = FSMAExtractor().route_extraction(result)

    expected_cte = {
        "event_id": "stable-event-001",
        "type": "COOLING",
        "kdes": expected_kdes,
        "confidence": 0.0,
        "source_text": SOURCE_TEXT,
        "bounding_box": BOUNDING_BOX,
    }
    assert set(expected_cte) == {field.name for field in fields(CTE)}
    if review_required:
        expected_cte["missing_kdes"] = []
    assert routing["topic"] == ("nlp.needs_review" if review_required else "graph.update")
    assert routing["payload"] == {
        "event_type": "fsma.extraction",
        "document_id": result.document_id,
        "tenant_id": result.tenant_id,
        "document_type": "BOL",
        "timestamp": result.extraction_timestamp,
        "ctes": [expected_cte],
        "warnings": ["Original extraction warning"],
        "risk_assessment": {
            "level": "LOW" if review_required else "HIGH",
            "review_required": review_required,
        },
    }
    serialized = routing["payload"]["ctes"][0]
    assert type(serialized["type"]) is str
    decoded = json.loads(json.dumps(routing["payload"]))
    assert decoded == routing["payload"]
    assert decoded["ctes"][0]["kdes"]["is_ftl_covered"] is ftl_covered
    assert type(decoded["ctes"][0]["kdes"]["quantity"]) is float
    assert type(decoded["ctes"][0]["confidence"]) is float
    assert result == original

    # Mutating emitted evidence must not alter the extraction awaiting another route.
    serialized["kdes"]["traceability_lot_code"] = "CHANGED"
    serialized["bounding_box"]["x"] = 99.0
    assert result == original


@pytest.mark.parametrize("review_required", [False, True], ids=["graph", "review"])
def test_routing_retains_explicit_null_optional_fields(review_required):
    cte = CTE(
        type=CTEType.SHIPPING,
        kdes=KDE(traceability_lot_code="LOT-MINIMUM", event_date="2026-09-28"),
        confidence=0.9,
    )

    serialized = FSMAExtractor().route_extraction(_result([cte], review_required))["payload"]["ctes"][0]

    expected_kdes = dict.fromkeys(KDE_VALUES)
    expected_kdes.update(traceability_lot_code="LOT-MINIMUM", event_date="2026-09-28")
    expected = {
        "event_id": cte.event_id,
        "type": "SHIPPING",
        "kdes": expected_kdes,
        "confidence": 0.9,
        "source_text": None,
        "bounding_box": None,
    }
    if review_required:
        expected["missing_kdes"] = []
    assert serialized == expected
    assert json.loads(json.dumps(serialized)) == expected


@pytest.mark.parametrize("review_required", [False, True], ids=["graph", "review"])
def test_paired_event_ids_and_prior_tlc_survive_repeated_serialization(review_required):
    shipping = CTE(
        type=CTEType.SHIPPING,
        kdes=KDE(traceability_lot_code="ORIGINAL-TLC", event_date="2026-09-28"),
        confidence=0.95,
    )
    receiving = CTE(
        type=CTEType.RECEIVING,
        kdes=KDE(
            traceability_lot_code="RECEIVING-TLC",
            event_date="2026-09-28",
            prior_source_tlc="ORIGINAL-TLC",
        ),
        confidence=0.95,
    )
    result = _result([shipping, receiving], review_required)
    original = deepcopy(result)
    extractor = FSMAExtractor()
    expected_ids = [shipping.event_id, receiving.event_id]
    assert len(set(expected_ids)) == 2

    for _ in range(2):
        ctes = extractor.route_extraction(result)["payload"]["ctes"]
        assert [cte["event_id"] for cte in ctes] == expected_ids
        assert [cte["type"] for cte in ctes] == ["SHIPPING", "RECEIVING"]
        assert ctes[1]["kdes"]["prior_source_tlc"] == "ORIGINAL-TLC"
        assert ctes[0]["kdes"]["traceability_lot_code"] == "ORIGINAL-TLC"
    assert result == original


@pytest.mark.parametrize("review_required", [False, True], ids=["graph", "review"])
@pytest.mark.parametrize(
    ("tlc", "event_date", "missing"),
    [
        (None, "2026-09-28", ["traceability_lot_code"]),
        ("", "2026-09-28", ["traceability_lot_code"]),
        ("LOT-GAP", None, ["event_date"]),
        ("LOT-GAP", "", ["event_date"]),
        (None, None, ["traceability_lot_code", "event_date"]),
        ("", "", ["traceability_lot_code", "event_date"]),
    ],
)
def test_required_kde_gate_is_unchanged(review_required, tlc, event_date, missing):
    qualified = CTE(type=CTEType.SHIPPING, kdes=KDE(**KDE_VALUES), confidence=0.9)
    deficient = CTE(
        type=CTEType.RECEIVING,
        kdes=KDE(traceability_lot_code=tlc, event_date=event_date),
        confidence=0.5,
        source_text="Incomplete original evidence",
        bounding_box={"x": 0.0},
    )
    result = _result([qualified, deficient], review_required)
    original = deepcopy(result)

    ctes = FSMAExtractor().route_extraction(result)["payload"]["ctes"]

    assert [cte["event_id"] for cte in ctes] == (
        [qualified.event_id, deficient.event_id] if review_required else [qualified.event_id]
    )
    if review_required:
        assert ctes[0]["missing_kdes"] == []
        assert ctes[1]["missing_kdes"] == missing
        assert ctes[1]["kdes"]["traceability_lot_code"] == tlc
        assert ctes[1]["kdes"]["event_date"] == event_date
        assert ctes[1]["source_text"] == "Incomplete original evidence"
        assert ctes[1]["bounding_box"] == {"x": 0.0}
    else:
        assert "missing_kdes" not in ctes[0]
    assert result == original
