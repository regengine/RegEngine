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
