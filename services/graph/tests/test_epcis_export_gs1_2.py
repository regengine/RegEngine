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

from shared.fsma_validation import calculate_gs1_check_digit, verify_gs1_check_digit  # noqa: E402
from services.graph.app.routers.fsma import compliance  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[2] / "ingestion" / "tests" / "fixtures" / "epcis_gs1"
TENANT = uuid.uuid4()


def _independent_gs1_mod10_check_digit(data_digits: str) -> int:
    """GS1 mod-10, weight 3 from the rightmost data digit. Test-local oracle."""
    total = 0
    for i, ch in enumerate(reversed(data_digits)):
        total += (3 if i % 2 == 0 else 1) * int(ch)
    return (10 - (total % 10)) % 10


def gs1_number(length):
    digits = str(uuid.uuid4().int).zfill(length - 1)[:length - 1]
    value = f"{digits}{calculate_gs1_check_digit(digits)}"
    assert len(value) == length
    assert value.isdigit()
    assert verify_gs1_check_digit(value)
    return value


def lot_code():
    return f"LOT-{uuid.uuid4().hex[:8].upper()}"


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
    with patch.object(compliance, "Neo4jClient", FakeNeo4j), patch.object(
        compliance, "reconcile_tenant_scope", return_value=str(TENANT)
    ), patch.object(compliance, "query_events_by_range", query):
        response = await endpoint(
            Request({"type": "http", "method": "GET", "path": "/export/epcis", "query_string": b"", "headers": []}),
            today, today, format, TENANT, object(),
        )
        assert response.headers["X-RegEngine-Preview"] == "true"
        payload = await body(response)
        if format == "json-ld":
            document = json.loads(payload)
            context = document["@context"]
            assert isinstance(context, list)
            assert context[1]["regengine"] == "https://regengine.co/ns/"
            assert context[1]["preview"] == "regengine:preview"
            assert context[1]["previewNotice"] == "regengine:previewNotice"
            metadata = document["regengine:exportMetadata"]
            for key in metadata:
                assert context[1][key] == f"regengine:{key}"
            assert metadata["preview"] is True
            assert metadata["previewNotice"] == (
                "EPCIS export is in Preview. Validate with your trading partner before relying on it for compliance."
            )
        return payload


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
        assert isinstance(event["transformationID"], str)
        assert event["transformationID"].startswith("urn:uuid:")
        assert event["transformationID"][len("urn:uuid:"):]
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
    jsonschema.Draft7Validator(
        json.loads(schema_file("EPCIS-JSON-Schema.json").read_text())
    ).validate(document)
    schema = etree.XMLSchema(etree.parse(str(schema_file("XSD/EPCglobal-epcis-2_0.xsd"))))
    tree = etree.fromstring(xml, etree.XMLParser(no_network=True)).getroottree()
    assert schema.validate(tree), str(schema.error_log)
    assert tree.xpath("//*[local-name()='EventList']/*") == []


def test_missing_event_time_is_skipped():
    row = graph_row("RECEIVING")
    row["event_time"] = None
    document = json.loads(asyncio.run(export("json-ld", [row])))
    assert document["epcisBody"]["eventList"] == []


def test_gs1_location_check_digit_accepts_generated_valid_gln():
    """Graph location helper must use GS1 weight-3-from-right."""
    row = graph_row("RECEIVING")
    digits = str(uuid.uuid4().int).zfill(12)[:12]
    check_digit = _independent_gs1_mod10_check_digit(digits)
    row["location_gln"] = f"{digits}{check_digit}"
    assert verify_gs1_check_digit(row["location_gln"])
    row["tlc"] = epc_identifier()
    document = json.loads(asyncio.run(export("json-ld", [row])))
    assert document["epcisBody"]["eventList"]
    read_point = document["epcisBody"]["eventList"][0]["readPoint"]["id"]
    assert read_point.startswith("https://id.gs1.org/414/")
    assert read_point.endswith(row["location_gln"])

    bad_gln = f"{digits}{(check_digit + 1) % 10}"
    assert not verify_gs1_check_digit(bad_gln)
    row["location_gln"] = bad_gln
    document = json.loads(asyncio.run(export("json-ld", [row])))
    for event in document["epcisBody"]["eventList"]:
        assert "readPoint" not in event


def test_graph_exports_raw_tlc_with_lot_gtin_as_digital_link():
    """Real FSMA lots use free-text TLC + Lot.gtin — must not be silently dropped."""
    row = {
        "type": "SHIPPING",
        "event_date": datetime.now(timezone.utc).date().isoformat(),
        "event_time": datetime.now(timezone.utc).time().isoformat(timespec="seconds"),
        "tlc": lot_code(),
        "gtin": gs1_number(14),
        "location_gln": gs1_number(13),
        "ship_from_gln": gs1_number(13),
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
    epc_class = event["quantityList"][0]["epcClass"]
    assert epc_class.startswith("https://id.gs1.org/01/")
    assert f"/01/{row['gtin']}/10/" in epc_class
    assert epc_class.endswith(row["tlc"])
    assert event["bizStep"] == "shipping"
    assert document["regengine:exportMetadata"]["skippedEventsCount"] == 0


def test_graph_exports_transformation_with_input_tlc_and_gtin():
    row = {
        "type": "TRANSFORMATION",
        "event_date": datetime.now(timezone.utc).date().isoformat(),
        "event_time": datetime.now(timezone.utc).time().isoformat(timespec="seconds"),
        "tlc": lot_code(),
        "gtin": gs1_number(14),
        "input_tlc": lot_code(),
        "input_gtin": gs1_number(14),
        "location_gln": location_identifier(),
        "event_id": uuid.uuid4().hex,
        "quantity": 3,
        "unit_of_measure": "KGM",
    }
    document = json.loads(asyncio.run(export("json-ld", [row])))
    event = document["epcisBody"]["eventList"][0]
    assert event["type"] == "TransformationEvent"
    for quantity_list, gtin, tlc in (
        ("outputQuantityList", "gtin", "tlc"),
        ("inputQuantityList", "input_gtin", "input_tlc"),
    ):
        epc_class = event[quantity_list][0]["epcClass"]
        assert epc_class.startswith("https://id.gs1.org/01/")
        assert f"/01/{row[gtin]}/10/" in epc_class
        assert epc_class.endswith(row[tlc])
    assert event["transformationID"].startswith("urn:uuid:")


def test_graph_harvesting_uses_creating_class_instance_bizstep():
    row = graph_row("HARVESTING")
    document = json.loads(asyncio.run(export("json-ld", [row])))
    assert document["epcisBody"]["eventList"][0]["bizStep"] == "creating_class_instance"
    etree = pytest.importorskip("lxml.etree")
    tree = etree.fromstring(asyncio.run(export("xml", [row])))
    assert tree.xpath("//*[local-name()='bizStep']/text()") == [
        "https://ref.gs1.org/cbv/BizStep-creating_class_instance"
    ]


def test_missing_event_time_records_skip_reason():
    row = graph_row("RECEIVING")
    row["event_time"] = None
    document = json.loads(asyncio.run(export("json-ld", [row])))
    assert document["epcisBody"]["eventList"] == []
    assert document["regengine:exportMetadata"]["skippedEventsCount"] == 1
    assert document["regengine:exportMetadata"]["skippedEventsByReason"]["missing_time"] == 1


def test_graph_harvesting_exports_lot_gtin_quantity_class():
    row = graph_row("HARVESTING")
    row.update(tlc=lot_code(), gtin=gs1_number(14), quantity=12, unit_of_measure="KGM")
    document = json.loads(asyncio.run(export("json-ld", [row])))
    event = document["epcisBody"]["eventList"][0]
    assert event["bizStep"] == "creating_class_instance"
    assert event["quantityList"][0]["epcClass"] == (
        f"https://id.gs1.org/01/{row['gtin']}/10/{row['tlc']}"
    )
