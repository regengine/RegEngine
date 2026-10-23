"""Graph EPCIS export against pinned GS1 JSON Schema and XML XSD."""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app import fsma_utils  # noqa: E402
from services.graph.app.routers.fsma import compliance  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[2] / "ingestion" / "tests" / "fixtures" / "epcis_gs1"
TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


class FakeNeo4j:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    @staticmethod
    def get_tenant_database_name(tenant_id):
        return "test-db"


async def body(response):
    return b"".join([part async for part in response.body_iterator])


def graph_row(event):
    timestamp = datetime.fromisoformat(event["eventTime"].replace("Z", "+00:00"))
    epc = (event.get("epcList") or event.get("outputEPCList"))[0]
    quantity = (event.get("quantityList") or event.get("outputQuantityList"))[0]
    row = {
        "type": "TRANSFORMATION" if event["type"] == "TransformationEvent" else event["bizStep"].upper(),
        "event_date": timestamp.date().isoformat(),
        "event_time": timestamp.time().isoformat(timespec="seconds"),
        "tlc": epc.removeprefix("urn:epc:id:sgtin:"),
        "location_gln": event["readPoint"]["id"].removeprefix("urn:epc:id:sgln:"),
        "quantity": quantity["quantity"],
        "unit_of_measure": quantity.get("uom"),
    }
    if event["type"] == "TransformationEvent":
        row["input_tlc"] = event["inputEPCList"][0].removeprefix("urn:epc:id:sgtin:")
        row["event_id"] = event["transformationID"]
    else:
        for key, field in (("sourceList", "ship_from_gln"), ("destinationList", "ship_to_gln")):
            if event.get(key):
                row[field] = event[key][0]["source" if key == "sourceList" else "destination"].removeprefix(
                    "urn:epc:id:sgln:"
                )
    return row


@pytest.mark.parametrize(
    "name",
    [
        "JSON/WithFullCombinationOfFields/object_event_all_possible_fields.jsonld",
        "JSON/WithFullCombinationOfFields/transformation_event_all_possible_fields.jsonld",
    ],
)
def test_graph_json_and_xml_conform(name):
    jsonschema = pytest.importorskip("jsonschema")
    etree = pytest.importorskip("lxml.etree")
    source = fixture(name)["epcisBody"]["eventList"][0]
    rows = [graph_row(source)]

    async def query(client, start, end, tenant):
        assert tenant == TENANT
        return rows

    async def export(format):
        return await compliance.export_epcis(
            Request({"type": "http", "method": "GET", "path": "/export/epcis", "query_string": b"", "headers": []}),
            "2013-01-01", "2014-01-01", format, uuid.UUID(TENANT), object(),
        )

    with patch.object(compliance, "Neo4jClient", FakeNeo4j), patch.object(
        compliance, "reconcile_tenant_scope", return_value=TENANT
    ), patch.object(fsma_utils, "query_events_by_range", query):
        document = json.loads(asyncio.run(body(asyncio.run(export("json-ld")))))
        xml = asyncio.run(body(asyncio.run(export("xml"))))

    jsonschema.Draft7Validator(
        fixture("EPCIS-JSON-Schema.json"), format_checker=jsonschema.FormatChecker()
    ).validate(document)
    event = document["epcisBody"]["eventList"][0]
    assert "extension" not in event
    assert all(value is not None and value != [] for value in event.values())
    schema = etree.XMLSchema(etree.parse(str(FIXTURES / "XSD" / "EPCglobal-epcis-2_0.xsd")))
    tree = etree.fromstring(xml, etree.XMLParser(no_network=True)).getroottree()
    assert schema.validate(tree), str(schema.error_log)
    node = tree.xpath("//*[local-name()='EventList']/*")[0]
    for field in ("sourceList", "destinationList", "quantityList", "inputEPCList", "outputEPCList"):
        if event.get(field):
            assert node.find(field) is not None
    if event["type"] == "TransformationEvent":
        assert node.find("transformationID") is not None


def test_xml_serializes_gs1_quantity_and_ilmd_with_escaping():
    etree = pytest.importorskip("lxml.etree")
    source = fixture("JSON/Example_9.6.2-ObjectEvent.jsonld")
    event = source["epcisBody"]["eventList"][0]
    document = {"schemaVersion": "2.0", "creationDate": source["creationDate"], "epcisBody": {"eventList": [event]}}
    xml = compliance._epcis_to_xml(document)
    schema = etree.XMLSchema(etree.parse(str(FIXTURES / "XSD" / "EPCglobal-epcis-2_0.xsd")))
    tree = etree.fromstring(xml.encode(), etree.XMLParser(no_network=True)).getroottree()
    assert schema.validate(tree), str(schema.error_log)
    node = tree.xpath("//*[local-name()='EventList']/*")[0]
    assert node.find("quantityList/quantityElement/epcClass").text == event["quantityList"][0]["epcClass"]
    assert node.find("sourceList/source").text == event["sourceList"][0]["source"]
    assert node.find("destinationList/destination").text == event["destinationList"][0]["destination"]
    full = fixture("JSON/WithFullCombinationOfFields/object_event_all_possible_fields.jsonld")
    full_event = full["epcisBody"]["eventList"][0]
    event["ilmd"] = {
        "urn:epcglobal:cbv:mda:lotNumber": full_event["ilmd"]["cbvmda:lotNumber"]
    }
    xml = compliance._epcis_to_xml(document)
    tree = etree.fromstring(xml.encode(), etree.XMLParser(no_network=True)).getroottree()
    assert schema.validate(tree), str(schema.error_log)
    assert tree.xpath("//*[local-name()='ilmd']/*[local-name()='lotNumber']")[0].text == "ABC123"
