"""Offline GS1 EPCIS 2.0 export conformance using pinned schemas."""

from __future__ import annotations

import asyncio
import copy
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import epcis_export as exporter  # noqa: E402

epcis_router = importlib.import_module("app.epcis.router")
FIXTURES = Path(__file__).parent / "fixtures" / "epcis_gs1"
CONTEXT_URL = "https://ref.gs1.org/standards/epcis/2.0.0/epcis-context.jsonld"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def class_uri():
    digits = str(uuid4().int).zfill(13)[:13]
    return f"urn:epc:class:lgtin:{digits[:7]}.{digits[7:]}.{uuid4().hex}"


def assert_conformant(document):
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.Draft7Validator(
        fixture("EPCIS-JSON-Schema.json"), format_checker=jsonschema.FormatChecker()
    ).validate(document)
    for event in document["epcisBody"]["eventList"]:
        assert "extension" not in event
        assert all(value is not None and value != [] for value in event.values())


def test_tenant_export_uses_runtime_class_and_skips_lot_only_rows():
    epc_class = class_uri()
    row = {
        "event_type": "receiving",
        "epcis_event_type": "ObjectEvent",
        "epcis_action": "ADD",
        "epcis_biz_step": "receiving",
        "event_timestamp": datetime.now(timezone.utc),
        "epc_class": epc_class,
        "traceability_lot_code": uuid4().hex,
        "quantity": None,
        "location_gln": None,
    }
    ctx = type("Tenant", (), {"tenant_id": str(uuid4())})()
    with patch.object(exporter, "_query_tenant_events", return_value=[row, {**row, "epc_class": None}]):
        response = asyncio.run(exporter.export_epcis(exporter.ExportRequest(tenant_id=ctx.tenant_id), validate=True, ctx=ctx))
    document = json.loads(response.body)
    assert_conformant(document)
    assert document["epcisBody"]["eventList"][0]["quantityList"][0]["epcClass"] == epc_class
    assert document["regengine:exportMetadata"]["skippedEventsCount"] == 1
    assert document["regengine:validation"]["valid"] is True
    bad = copy.deepcopy(document)
    bad["epcisBody"]["eventList"][0]["extension"] = {"quantityList": []}
    bad["epcisBody"]["eventList"][0]["bizStep"] = "transforming"
    assert len(exporter._validate_epcis_document(bad)) >= 2


def test_empty_export_has_no_fabricated_events():
    ctx = type("Tenant", (), {"tenant_id": str(uuid4())})()
    with patch.object(exporter, "_query_tenant_events", return_value=[]):
        response = asyncio.run(exporter.export_epcis(exporter.ExportRequest(tenant_id=ctx.tenant_id), validate=True, ctx=ctx))
    document = json.loads(response.body)
    assert_conformant(document)
    assert document["epcisBody"]["eventList"] == []
    assert document["regengine:exportMetadata"]["eventsCount"] == 0
    assert document["regengine:exportMetadata"]["regengine:message"] == "No data yet"
    assert document["regengine:validation"]["valid"] is False


def test_stored_event_export_preserves_metadata_namespace():
    event = {
        "type": "ObjectEvent",
        "eventTime": datetime.now(timezone.utc).isoformat(),
        "eventTimeZoneOffset": "+00:00",
        "action": "ADD",
        "bizStep": "receiving",
        "quantityList": [{"epcClass": class_uri()}],
    }
    ctx = type("Tenant", (), {"tenant_id": str(uuid4())})()
    with patch.object(epcis_router, "_list_events_from_db", return_value=[event]), patch.object(
        epcis_router, "_allow_in_memory_fallback", return_value=False
    ):
        document = asyncio.run(epcis_router.export_epcis_events(None, None, None, None, None, None, ctx))
    assert_conformant(document)
    assert "regengine:metadata" in document
    assert "metadata" not in document
    jsonld = pytest.importorskip("pyld").jsonld
    context = fixture("epcis-context.jsonld")
    dropped = []

    def loader(url, options=None):
        if url != CONTEXT_URL:
            raise ValueError(f"Unexpected context URL: {url}")
        return {"contextUrl": None, "documentUrl": url, "document": context}

    expanded = jsonld.expand(document, options={"documentLoader": loader}, on_property_dropped=dropped.append)
    assert not dropped
    assert "https://regengine.co/ns/metadata" in expanded[0]


def test_gs1_check_digit_weights_match_known_valid_examples():
    """Rightmost data digit must receive weight 3 (GS1 mod-10)."""
    # GTIN-14, GLN-13, and EAN-13 textbook examples
    assert exporter._gs1_check_digit_valid("09506000134352")
    assert exporter._gs1_check_digit_valid("0614141000005")
    assert exporter._gs1_check_digit_valid("4006381333931")
    # SSCC-18: base 10614141123456789 → check digit 7
    assert exporter._gs1_check_digit_valid("106141411234567897")
    assert not exporter._gs1_check_digit_valid("09506000134351")


def test_export_builds_class_from_query_gtin_and_lot():
    """Regression: query returns gtin (not a test-only epc_class column)."""
    row = {
        "event_type": "receiving",
        "epcis_event_type": "ObjectEvent",
        "epcis_action": "ADD",
        "epcis_biz_step": "receiving",
        "event_timestamp": datetime.now(timezone.utc),
        "gtin": "09506000134352",
        "traceability_lot_code": "SYN-LOT-001",
        "quantity": 10,
        "unit_of_measure": "lbs",
        "location_gln": "0614141000005",
    }
    ctx = type("Tenant", (), {"tenant_id": str(uuid4())})()
    with patch.object(exporter, "_query_tenant_events", return_value=[row]):
        response = asyncio.run(
            exporter.export_epcis(exporter.ExportRequest(tenant_id=ctx.tenant_id), validate=True, ctx=ctx)
        )
    document = json.loads(response.body)
    event = document["epcisBody"]["eventList"][0]
    assert event["quantityList"][0]["epcClass"] == "https://id.gs1.org/01/09506000134352/10/SYN-LOT-001"
    assert event["quantityList"][0]["uom"] == "LBR"
    assert event["regengine:unitOfMeasure"] == "lbs"
    assert event["readPoint"]["id"] == "https://id.gs1.org/414/0614141000005"
    assert document["regengine:exportMetadata"]["skippedEventsCount"] == 0
    assert "regengine:message" not in document["regengine:exportMetadata"]


def test_export_builds_class_from_product_id_kde():
    epc_class = class_uri()
    row = {
        "event_type": "shipping",
        "epcis_event_type": None,
        "epcis_action": None,
        "epcis_biz_step": None,
        "event_timestamp": datetime.now(timezone.utc),
        "product_id": epc_class,
        "traceability_lot_code": "SYN-LOT-002",
        "quantity": None,
        "unit_of_measure": None,
        "location_gln": None,
    }
    ctx = type("Tenant", (), {"tenant_id": str(uuid4())})()
    with patch.object(exporter, "_query_tenant_events", return_value=[row]):
        response = asyncio.run(
            exporter.export_epcis(exporter.ExportRequest(tenant_id=ctx.tenant_id), validate=False, ctx=ctx)
        )
    document = json.loads(response.body)
    assert document["epcisBody"]["eventList"][0]["quantityList"][0]["epcClass"] == epc_class


def test_transformation_cte_emitted_as_transformation_event():
    epc_class = class_uri()
    input_class = class_uri()
    row = {
        "event_type": "transformation",
        "epcis_event_type": "TransformationEvent",
        "epcis_action": None,
        "epcis_biz_step": "commissioning",
        "event_timestamp": datetime.now(timezone.utc),
        "epc_class": epc_class,
        "traceability_lot_code": "OUT-LOT",
        "quantity": 5,
        "unit_of_measure": "kg",
        "sha256_hash": "a" * 64,
        "epcis_document_json": json.dumps(
            {"inputQuantityList": [{"epcClass": input_class}]}
        ),
    }
    ctx = type("Tenant", (), {"tenant_id": str(uuid4())})()
    with patch.object(exporter, "_query_tenant_events", return_value=[row]):
        response = asyncio.run(
            exporter.export_epcis(exporter.ExportRequest(tenant_id=ctx.tenant_id), validate=True, ctx=ctx)
        )
    document = json.loads(response.body)
    event = document["epcisBody"]["eventList"][0]
    assert event["type"] == "TransformationEvent"
    assert event["outputQuantityList"][0]["epcClass"] == epc_class
    assert event["outputQuantityList"][0]["uom"] == "KGM"
    assert event["inputQuantityList"][0]["epcClass"] == input_class
    assert event["transformationID"].startswith("urn:sha256:")
    assert document["regengine:exportMetadata"]["skippedEventsCount"] == 0


def test_harvesting_maps_to_collecting_bizstep():
    """Phase A keeps harvesting → collecting."""
    epc_class = class_uri()
    row = {
        "event_type": "harvesting",
        "epcis_event_type": "ObjectEvent",
        "epcis_action": "ADD",
        "epcis_biz_step": None,
        "event_timestamp": datetime.now(timezone.utc),
        "epc_class": epc_class,
        "traceability_lot_code": "HARVEST-1",
        "quantity": 1,
        "unit_of_measure": "EA",
        "location_gln": None,
    }
    ctx = type("Tenant", (), {"tenant_id": str(uuid4())})()
    with patch.object(exporter, "_query_tenant_events", return_value=[row]):
        response = asyncio.run(
            exporter.export_epcis(exporter.ExportRequest(tenant_id=ctx.tenant_id), validate=False, ctx=ctx)
        )
    document = json.loads(response.body)
    assert document["epcisBody"]["eventList"][0]["bizStep"] == "collecting"


def test_export_epc_class_equals_stored_canonical_full_id():
    """SEL-598: when TLC is already a class URI, emit it unchanged."""
    full = "https://id.gs1.org/01/00012345678905/10/LotRebuild"
    assert exporter._epc_class({"traceability_lot_code": full}) == full
    # Bare lot + valid GTIN rebuilds using the derived token only.
    assert (
        exporter._epc_class({"traceability_lot_code": "LotRebuild", "gtin": "00012345678905"})
        == full
    )
    # A full URI must never be nested as the /10/ segment.
    nested = exporter._epc_class({"traceability_lot_code": full, "gtin": "00012345678905"})
    assert nested == full
    assert "/10/https" not in nested

