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


def _independent_gs1_mod10_check_digit(data_digits: str) -> int:
    """GS1 General Specifications mod-10, written out for the test.

    From the rightmost data digit: weights alternate 3, 1, 3, 1, ...
    Check digit is (10 - (sum % 10)) % 10. Independent of
    shared.fsma_validation / exporter._gs1_check_digit_valid.
    """
    if not data_digits.isdigit():
        raise ValueError("data digits must be numeric")
    total = 0
    for i, ch in enumerate(reversed(data_digits)):
        total += (3 if i % 2 == 0 else 1) * int(ch)
    return (10 - (total % 10)) % 10


def _gs1_with_check(data_digits: str) -> str:
    """Append check digit from the independent mod-10 above."""
    return data_digits + str(_independent_gs1_mod10_check_digit(data_digits))


def generated_gtin14() -> str:
    base = str(uuid4().int % (10**13)).zfill(13)
    return _gs1_with_check(base)


def generated_gln13() -> str:
    base = str(uuid4().int % (10**12)).zfill(12)
    return _gs1_with_check(base)


def generated_sscc18() -> str:
    base = str(uuid4().int % (10**17)).zfill(17)
    return _gs1_with_check(base)


def generated_lot() -> str:
    return f"SYN-{uuid4().hex[:12]}"


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
    """Namespace + @context terms without pyld (pyld is not in requirements.lock)."""
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
    assert document["@context"][0] == CONTEXT_URL
    assert isinstance(document["@context"][1], dict)
    assert document["@context"][1].get("regengine") == "https://regengine.co/ns/"
    assert "regengine:source" in document["regengine:metadata"]
    assert "regengine:event_count" in document["regengine:metadata"]


def test_gs1_check_digit_independent_mod10_and_published_examples():
    """Independent mod-10 + known published vectors; production must agree.

    Published examples are the independent guard (not minted via production).
    Generated IDs are minted with the test-local mod-10, then checked by the
    exporter so a reversed weight in production would fail.
    """
    # Published GS1 examples (data + expected check digit), each cited from a
    # GS1 document on ref.gs1.org / gs1.org — no third-party pages.
    published = (
        # GTIN-14 09506000134352 — GS1 General Specifications Release 26.0
        # §1.2.4.4 (JSON-LD example gs1:gtin); also QR Code powered by GS1
        # best practices (2023), Best practice 1.
        ("0950600013435", "2", 14),
        # GLN-13 0614141000005 — GS1 Verifiable Credentials White Paper on
        # Data Model and Validations 1.0.1 §5.1.2 (partyGLN for GS1 US).
        ("061414100000", "5", 13),
        # SSCC-18 376104250021234569 — GS1 General Specifications Release 26.0
        # §7.9.1 Table 7-9 (18-digit check digit calculation example).
        ("37610425002123456", "9", 18),
    )
    for data, expected_cd, length in published:
        assert _independent_gs1_mod10_check_digit(data) == int(expected_cd)
        full = data + expected_cd
        assert len(full) == length
        assert exporter._gs1_check_digit_valid(full)
        wrong_cd = "0" if expected_cd != "0" else "1"
        bad = data + wrong_cd
        assert _independent_gs1_mod10_check_digit(data) != int(wrong_cd)
        assert not exporter._gs1_check_digit_valid(bad)

    # Generated structure + production agreement with independent mint.
    gtin = generated_gtin14()
    gln = generated_gln13()
    sscc = generated_sscc18()
    assert len(gtin) == 14 and gtin.isdigit()
    assert len(gln) == 13 and gln.isdigit()
    assert len(sscc) == 18 and sscc.isdigit()
    assert _independent_gs1_mod10_check_digit(gtin[:-1]) == int(gtin[-1])
    assert _independent_gs1_mod10_check_digit(gln[:-1]) == int(gln[-1])
    assert _independent_gs1_mod10_check_digit(sscc[:-1]) == int(sscc[-1])
    assert exporter._gs1_check_digit_valid(gtin)
    assert exporter._gs1_check_digit_valid(gln)
    assert exporter._gs1_check_digit_valid(sscc)
    bad_gtin = gtin[:-1] + ("0" if gtin[-1] != "0" else "1")
    assert not exporter._gs1_check_digit_valid(bad_gtin)


def test_export_builds_class_from_query_gtin_and_lot():
    """Regression: query returns gtin (not a test-only epc_class column)."""
    gtin = generated_gtin14()
    gln = generated_gln13()
    lot = generated_lot()
    row = {
        "event_type": "receiving",
        "epcis_event_type": "ObjectEvent",
        "epcis_action": "ADD",
        "epcis_biz_step": "receiving",
        "event_timestamp": datetime.now(timezone.utc),
        "gtin": gtin,
        "traceability_lot_code": lot,
        "quantity": 10,
        "unit_of_measure": "lbs",
        "location_gln": gln,
    }
    ctx = type("Tenant", (), {"tenant_id": str(uuid4())})()
    with patch.object(exporter, "_query_tenant_events", return_value=[row]):
        response = asyncio.run(
            exporter.export_epcis(exporter.ExportRequest(tenant_id=ctx.tenant_id), validate=True, ctx=ctx)
        )
    document = json.loads(response.body)
    event = document["epcisBody"]["eventList"][0]
    assert event["quantityList"][0]["epcClass"] == f"https://id.gs1.org/01/{gtin}/10/{lot}"
    assert event["quantityList"][0]["uom"] == "LBR"
    assert event["regengine:unitOfMeasure"] == "lbs"
    assert event["readPoint"]["id"] == f"https://id.gs1.org/414/{gln}"
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
        "traceability_lot_code": generated_lot(),
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
        "traceability_lot_code": generated_lot(),
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


def test_harvesting_maps_to_creating_class_instance_bizstep():
    """Harvesting commissions a class instance (CBV creating_class_instance)."""
    epc_class = class_uri()
    row = {
        "event_type": "harvesting",
        "epcis_event_type": "ObjectEvent",
        "epcis_action": "ADD",
        "epcis_biz_step": None,
        "event_timestamp": datetime.now(timezone.utc),
        "epc_class": epc_class,
        "traceability_lot_code": generated_lot(),
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
    assert document["epcisBody"]["eventList"][0]["bizStep"] == "creating_class_instance"
