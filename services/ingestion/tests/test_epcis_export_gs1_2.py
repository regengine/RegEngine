"""Offline GS1 EPCIS 2.0 export conformance using pinned upstream artifacts."""

from __future__ import annotations

import asyncio
import copy
import importlib
import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import epcis_export as exporter  # noqa: E402

epcis_router = importlib.import_module("app.epcis.router")

FIXTURES = Path(__file__).parent / "fixtures" / "epcis_gs1"
CONTEXT_URL = "https://ref.gs1.org/standards/epcis/2.0.0/epcis-context.jsonld"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def assert_conformant(document):
    jsonschema = pytest.importorskip("jsonschema")
    schema = fixture("EPCIS-JSON-Schema.json")
    jsonschema.Draft7Validator(schema, format_checker=jsonschema.FormatChecker()).validate(document)
    assert not any(value is None for value in walk(document))
    for event in document["epcisBody"]["eventList"]:
        assert "extension" not in event
        assert all(value != [] for value in event.values())


def walk(value):
    if isinstance(value, dict):
        yield from value.values()
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def test_tenant_export_uses_real_class_and_skips_lot_only_rows():
    source = fixture("JSON/WithFullCombinationOfFields/object_event_all_possible_fields.jsonld")
    event = source["epcisBody"]["eventList"][0]
    row = {
        "event_type": "receiving",
        "epcis_event_type": "ObjectEvent",
        "epcis_action": "ADD",
        "epcis_biz_step": "receiving",
        "event_timestamp": datetime.fromisoformat(event["eventTime"].replace("Z", "+00:00")),
        "traceability_lot_code": event["quantityList"][0]["epcClass"].rsplit(".", 1)[-1],
        "epcis_document_json": json.dumps(event),
        "quantity": event["quantityList"][0]["quantity"],
        "unit_of_measure": event["quantityList"][0]["uom"],
        "location_gln": event["readPoint"]["id"],
        "sha256_hash": None,
    }
    ctx = type("Tenant", (), {"tenant_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"})()
    with patch.object(exporter, "_query_tenant_events", return_value=[row, {**row, "epcis_document_json": None}]):
        response = asyncio.run(exporter.export_epcis(exporter.ExportRequest(tenant_id=ctx.tenant_id), validate=True, ctx=ctx))
    document = json.loads(response.body)
    assert_conformant(document)
    assert document["epcisBody"]["eventList"][0]["quantityList"][0]["epcClass"] == event["quantityList"][0]["epcClass"]
    assert document["regengine:exportMetadata"]["skippedEventsCount"] == 1
    assert document["regengine:validation"]["valid"] is True


def test_sample_export_conforms_and_validator_rejects_legacy_values():
    ctx = type("Tenant", (), {"tenant_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"})()
    with patch.object(exporter, "_query_tenant_events", return_value=[]):
        response = asyncio.run(exporter.export_epcis(exporter.ExportRequest(tenant_id=ctx.tenant_id), validate=True, ctx=ctx))
    document = json.loads(response.body)
    assert_conformant(document)
    bad = copy.deepcopy(document)
    bad["epcisBody"]["eventList"][0]["extension"] = {"quantityList": []}
    bad["epcisBody"]["eventList"][0]["bizStep"] = "transforming"
    assert len(exporter._validate_epcis_document(bad)) >= 2


def test_stored_event_export_preserves_custom_fields_in_declared_namespace():
    source = fixture("JSON/WithFullCombinationOfFields/object_event_all_possible_fields.jsonld")
    event = source["epcisBody"]["eventList"][0]
    ctx = type("Tenant", (), {"tenant_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"})()
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
