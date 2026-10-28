"""RE-SEC-001 / 002 integration tests for compliance.py export builders.

We test the inner builder functions directly to avoid pulling up Neo4j /
auth fixtures. These cover:

* ``_epcis_to_xml`` — tenant-stored TLC / GLN / EPC values must be XML-
  escaped, not concatenated raw.
* CSV cells produced via ``csv_safe`` — Excel formula prefixes from
  tenant-stored values must be neutralized.
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import defusedxml.ElementTree as ET
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.exporters.safe_text import csv_safe  # noqa: E402
from services.graph.app.routers.fsma.compliance import _epcis_to_xml  # noqa: E402


@pytest.mark.security
class TestEpcisXmlEscaping:
    def test_xml_declares_utf8_and_is_parseable(self):
        xml = _epcis_to_xml({"epcisBody": {"eventList": []}})

        declaration = xml.splitlines()[0]
        assert declaration == "<?xml version='1.0' encoding='utf-8'?>"
        assert "unicode" not in declaration
        root = ET.fromstring(xml.encode("utf-8"))
        assert root.tag == "{urn:epcglobal:epcis:xsd:2}EPCISDocument"
        assert root.find("EPCISBody/EventList") is not None

    def test_attack_vector_in_epc_is_escaped(self):
        """A tenant Lot.tlc containing XML metacharacters must not break out."""
        attack_epc = "urn:epc:id:sgtin:</epc><inject>é & 茶</inject><epc>"
        doc = {
            "creationDate": "2026-05-09T00:00:00Z",
            "epcisBody": {
                "eventList": [
                    {
                        "type": "ObjectEvent",
                        "eventTime": "2026-05-09T00:00:00Z",
                        "eventTimeZoneOffset": "-08:00",
                        "epcList": [attack_epc],
                        "action": "ADD",
                        "bizStep": "urn:epcglobal:cbv:bizstep:commissioning",
                        "disposition": "urn:epcglobal:cbv:disp:in_progress",
                        "readPoint": {"id": "urn:epc:id:sgln:0123456789012"},
                    }
                ]
            },
        }
        xml = _epcis_to_xml(doc)

        # Output must parse as well-formed XML.
        root = ET.fromstring(xml.encode("utf-8"))

        # The attack vector must NOT have introduced an <inject> element.
        assert root.find(".//inject") is None
        assert "<inject>" not in xml

        # The original literal value should round-trip through .text.
        epc_elem = root.find(".//epc")
        assert epc_elem is not None
        assert epc_elem.text == attack_epc

    def test_attack_vector_in_creation_date_is_escaped(self):
        attack = '" foo="bar'  # try to inject a sibling attribute
        doc = {
            "creationDate": attack,
            "epcisBody": {"eventList": []},
        }
        xml = _epcis_to_xml(doc)
        # Must still parse.
        root = ET.fromstring(xml)
        assert root.attrib.get("creationDate") == attack
        # And no rogue attribute was introduced.
        assert "foo" not in root.attrib


@pytest.mark.security
class TestCsvFormulaInjectionViaWriter:
    """End-to-end: csv_safe + csv.writer correctly produce a benign cell."""

    def test_hyperlink_attack_neutralized_in_csv(self):
        attack = '=HYPERLINK("http://evil/", "Click")'
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["TLC", "Description"])
        w.writerow(["LOT-1", csv_safe(attack)])
        text = buf.getvalue()

        # Reading back must NOT yield a leading '=' in the cell, so Excel
        # does not interpret it as a formula.
        rows = list(csv.reader(io.StringIO(text)))
        assert rows[1][1].startswith("'")
        assert not rows[1][1].startswith("=")
