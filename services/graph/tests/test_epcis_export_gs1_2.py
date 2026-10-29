"""Graph EPCIS export against pinned GS1 JSON Schema and XML XSD."""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app import fsma_utils  # noqa: E402
from services.graph.app.routers.fsma import compliance  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[2] / "ingestion" / "tests" / "fixtures" / "epcis_gs1"
TENANT = uuid.uuid4()


def schema_file(name):
    return FIXTURES / name


class FakeNeo4j:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    @staticmethod
    def get_tenant_database_name(tenant_id):
        return f"tenant-{tenant_id}"


async def body(response):
    return b"".join([part async for part in response.body_iterator])


def epc_identifier():
    digits = str(uuid.uuid4().int).zfill(13)[:13]
    return f"{digits[:7]}.{digits[7:]}.{uuid.uuid4().hex}"


def location_identifier():
    digits = str(uuid.uuid4().int).zfill(12)[:12]
    return f"{digits[:7]}.{digits[7:]}.{uuid.uuid4().hex}"


def graph_row(kind):
    now = datetime.now(timezone.utc)
    row = {
        "type": kind,
        "event_date": now.date().isoformat(),
        "event_time": now.time().isoformat(timespec="seconds"),
        "tlc": epc_identifier(),
        "location_gln": location_identifier(),
    }
    if kind == "TRANSFORMATION":
        row["input_tlc"] = epc_identifier()
        row["event_id"] = f"urn:uuid:{uuid.uuid4()}"
    else:
        row["ship_from_gln"] = location_identifier()
        row["ship_to_gln"] = location_identifier()
    return row


async def export(format, rows):
    async def query(client, start, end, tenant, **kwargs):
        assert tenant == str(TENANT)
        return rows

    today = datetime.now(timezone.utc).date().isoformat()
    # Bypass slowapi so the suite can call the endpoint many times in one process.
    endpoint = getattr(compliance.export_epcis, "__wrapped__", compliance.export_epcis)
    with (
        patch.object(compliance, "Neo4jClient", FakeNeo4j),
        patch.object(compliance, "reconcile_tenant_scope", return_value=str(TENANT)),
        patch.object(fsma_utils, "query_events_by_range", query),
        patch.object(compliance, "query_events_by_range", query),
    ):
        response = await endpoint(
            Request({"type": "http", "method": "GET", "path": "/export/epcis", "query_string": b"", "headers": []}),
            today,
            today,
            format,
            TENANT,
            object(),
        )
        return await body(response)


@pytest.mark.parametrize("kind", ["RECEIVING", "TRANSFORMATION"])
def test_graph_json_and_xml_conform(kind):
    jsonschema = pytest.importorskip("jsonschema")
    etree = pytest.importorskip("lxml.etree")
    rows = [graph_row(kind)]
    document = json.loads(asyncio.run(export("json-ld", rows)))
    xml = asyncio.run(export("xml", rows))

    jsonschema.Draft7Validator(
        json.loads(schema_file("EPCIS-JSON-Schema.json").read_text()),
        format_checker=jsonschema.FormatChecker(),
    ).validate(document)
    event = document["epcisBody"]["eventList"][0]
    assert "extension" not in event
    assert all(value is not None and value != [] for value in event.values())
    schema = etree.XMLSchema(etree.parse(str(schema_file("XSD/EPCglobal-epcis-2_0.xsd"))))
    tree = etree.fromstring(xml, etree.XMLParser(no_network=True)).getroottree()
    assert schema.validate(tree), str(schema.error_log)
    node = tree.xpath("//*[local-name()='EventList']/*")[0]
    if kind == "TRANSFORMATION":
        assert event["transformationID"] == rows[0]["event_id"]
        assert node.find("transformationID") is not None
    else:
        assert event["epcList"][0].endswith(rows[0]["tlc"])
        assert node.find("epcList") is not None


def test_empty_export_has_no_events_in_either_format():
    etree = pytest.importorskip("lxml.etree")
    document = json.loads(asyncio.run(export("json-ld", [])))
    xml = asyncio.run(export("xml", []))
    assert document["epcisBody"]["eventList"] == []
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.Draft7Validator(json.loads(schema_file("EPCIS-JSON-Schema.json").read_text())).validate(document)
    schema = etree.XMLSchema(etree.parse(str(schema_file("XSD/EPCglobal-epcis-2_0.xsd"))))
    tree = etree.fromstring(xml, etree.XMLParser(no_network=True)).getroottree()
    assert schema.validate(tree), str(schema.error_log)
    assert tree.xpath("//*[local-name()='EventList']/*") == []


def test_missing_event_time_is_skipped():
    row = graph_row("RECEIVING")
    row["event_time"] = None
    document = json.loads(asyncio.run(export("json-ld", [row])))
    assert document["epcisBody"]["eventList"] == []


def test_gs1_location_check_digit_accepts_known_valid_gln():
    """Graph location helper must use GS1 weight-3-from-right."""
    row = graph_row("RECEIVING")
    row["location_gln"] = "0614141000005"
    row["tlc"] = epc_identifier()
    document = json.loads(asyncio.run(export("json-ld", [row])))
    assert document["epcisBody"]["eventList"]
    assert document["epcisBody"]["eventList"][0]["readPoint"]["id"] == "https://id.gs1.org/414/0614141000005"


def test_graph_exports_raw_tlc_with_lot_gtin_as_digital_link():
    """Real FSMA lots use free-text TLC + Lot.gtin — must not be silently dropped."""
    row = {
        "type": "SHIPPING",
        "event_date": datetime.now(timezone.utc).date().isoformat(),
        "event_time": datetime.now(timezone.utc).time().isoformat(timespec="seconds"),
        "tlc": "LOT-2024-001",
        "gtin": "09506000134352",
        "location_gln": "0614141000005",
        "ship_from_gln": "0614141000005",
        "ship_to_gln": location_identifier(),
        "quantity": 12,
        "unit_of_measure": "KGM",
        "event_id": f"urn:uuid:{uuid.uuid4()}",
    }
    document = json.loads(asyncio.run(export("json-ld", [row])))
    events = document["epcisBody"]["eventList"]
    assert len(events) == 1
    event = events[0]
    assert event["type"] == "ObjectEvent"
    assert event["quantityList"][0]["epcClass"] == "https://id.gs1.org/01/09506000134352/10/LOT-2024-001"
    assert event["bizStep"] == "shipping"
    assert document["regengine:exportMetadata"]["skippedEventsCount"] == 0


def test_graph_exports_transformation_with_input_tlc_and_gtin():
    row = {
        "type": "TRANSFORMATION",
        "event_date": datetime.now(timezone.utc).date().isoformat(),
        "event_time": datetime.now(timezone.utc).time().isoformat(timespec="seconds"),
        "tlc": "OUT-LOT-9",
        "gtin": "09506000134352",
        "input_tlc": "IN-LOT-9",
        "input_gtin": "09506000134352",
        "location_gln": location_identifier(),
        "event_id": "evt-bare-id-123",
        "quantity": 3,
        "unit_of_measure": "KGM",
    }
    document = json.loads(asyncio.run(export("json-ld", [row])))
    event = document["epcisBody"]["eventList"][0]
    assert event["type"] == "TransformationEvent"
    assert event["outputQuantityList"][0]["epcClass"].endswith("/10/OUT-LOT-9")
    assert event["inputQuantityList"][0]["epcClass"].endswith("/10/IN-LOT-9")
    assert event["transformationID"].startswith("urn:uuid:")


def test_graph_harvesting_uses_collecting_bizstep():
    row = graph_row("HARVESTING")
    # graph_row uses split SGTIN-shaped tlc
    document = json.loads(asyncio.run(export("json-ld", [row])))
    assert document["epcisBody"]["eventList"][0]["bizStep"] == "collecting"


def test_missing_event_time_records_skip_reason():
    row = graph_row("RECEIVING")
    row["event_time"] = None
    document = json.loads(asyncio.run(export("json-ld", [row])))
    assert document["epcisBody"]["eventList"] == []
    assert document["regengine:exportMetadata"]["skippedEventsCount"] == 1
    assert document["regengine:exportMetadata"]["skippedEventsByReason"]["missing_time"] == 1
