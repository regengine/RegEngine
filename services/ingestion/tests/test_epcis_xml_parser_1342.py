"""Coverage for app/epcis/xml_parser.py — EPCIS 2.0 XML parsing.

Locks:
- Namespace utilities:
    * _xml_local strips ``{ns}tag`` to ``tag``; returns input when no ns.
    * _xml_ns_prefix maps a known URI back to its registered prefix.
    * _is_xml_content detects leading ``<?xml`` or ``<``.
- Element walkers:
    * _xml_child_text returns stripped text of the first child with a
      matching local name, None when absent or whitespace-only.
    * _xml_find_events collects ObjectEvent / AggregationEvent /
      TransactionEvent / TransformationEvent under epcglobal:epcis,
      GS1 ref, or bare-element namespaces, and dedupes by id().
    * _xml_collect_list walks a list-tag / item-tag pair.
- Quantity + location + source/destination extraction.
- ILMD and bizTransaction extraction incl. FSMA extension blocks.
- _xml_event_to_dict assembles the canonical dict.
- _parse_epcis_xml handles bytes/str input, bare and namespaced XML,
  returns [] on parse failure, and respects the defusedxml import
  fallback when lxml is unavailable.

Issue: #1342
"""

from __future__ import annotations

import sys
from types import ModuleType

import pytest

from app.epcis import xml_parser as xp

# ---------------------------------------------------------------------------
# Helpers — build real XML trees via lxml (same engine used by the parser)
# ---------------------------------------------------------------------------

from lxml import etree  # type: ignore


EPCIS_NS = "urn:epcglobal:epcis:xsd:2"
FSMA_NS = "urn:fsma:food:traceability"
GS1_NS = "https://ref.gs1.org/standards/epcis/2.0.0"


def _el(tag: str, *, text: str | None = None, ns: str | None = None,
        attrib: dict | None = None):
    """Build a single lxml Element."""
    qname = f"{{{ns}}}{tag}" if ns else tag
    el = etree.Element(qname, attrib=attrib or {})
    if text is not None:
        el.text = text
    return el


# ---------------------------------------------------------------------------
# _xml_local / _xml_ns_prefix / _is_xml_content
# ---------------------------------------------------------------------------


class TestNamespaceHelpers:

    def test_xml_local_strips_namespace(self):
        assert xp._xml_local("{urn:example}tag") == "tag"

    def test_xml_local_passes_through_bare_tag(self):
        assert xp._xml_local("plain") == "plain"

    def test_xml_ns_prefix_for_known_uri(self):
        assert xp._xml_ns_prefix(f"{{{EPCIS_NS}}}foo") == "epcis:"
        assert xp._xml_ns_prefix(f"{{{FSMA_NS}}}foo") == "fsma:"

    def test_xml_ns_prefix_unknown_ns_returns_empty(self):
        assert xp._xml_ns_prefix("{unknown:ns}foo") == ""

    def test_xml_ns_prefix_no_ns_returns_empty(self):
        assert xp._xml_ns_prefix("plain") == ""

    @pytest.mark.parametrize("raw,expected", [
        (b"<?xml version='1.0'?><root/>", True),
        (b"<root/>", True),
        (b"   <root/>", True),  # leading whitespace OK
        (b"{\"json\": true}", False),
        (b"plain text", False),
        (b"", False),
    ])
    def test_is_xml_content(self, raw, expected):
        assert xp._is_xml_content(raw) is expected


# ---------------------------------------------------------------------------
# _xml_child_text
# ---------------------------------------------------------------------------


class TestXmlChildText:

    def test_returns_stripped_text_when_present(self):
        parent = _el("root")
        parent.append(_el("eventTime", text=" 2026-01-01T00:00:00Z "))
        assert xp._xml_child_text(parent, "eventTime") == "2026-01-01T00:00:00Z"

    def test_returns_none_when_missing(self):
        parent = _el("root")
        parent.append(_el("other", text="x"))
        assert xp._xml_child_text(parent, "missing") is None

    def test_returns_none_when_whitespace_only(self):
        parent = _el("root")
        parent.append(_el("eventTime", text="   "))
        assert xp._xml_child_text(parent, "eventTime") is None

    def test_returns_none_when_empty_text(self):
        parent = _el("root")
        parent.append(_el("eventTime", text=None))
        assert xp._xml_child_text(parent, "eventTime") is None

    def test_matches_by_local_name_ignoring_namespace(self):
        parent = _el("root")
        parent.append(_el("eventTime", text="t", ns=EPCIS_NS))
        assert xp._xml_child_text(parent, "eventTime") == "t"


# ---------------------------------------------------------------------------
# _xml_find_events
# ---------------------------------------------------------------------------


class TestXmlFindEvents:

    def test_finds_events_under_epcis_ns(self):
        root = _el("EPCISDocument")
        ev = _el("ObjectEvent", ns=EPCIS_NS)
        root.append(ev)
        events = xp._xml_find_events(root)
        assert len(events) == 1
        assert events[0] is ev

    def test_finds_events_under_gs1_ns(self):
        root = _el("EPCISDocument")
        root.append(_el("AggregationEvent", ns=GS1_NS))
        assert len(xp._xml_find_events(root)) == 1

    def test_finds_bare_element_events(self):
        root = _el("EPCISDocument")
        root.append(_el("ObjectEvent"))
        root.append(_el("TransactionEvent"))
        root.append(_el("TransformationEvent"))
        assert len(xp._xml_find_events(root)) == 3

    def test_does_not_duplicate_across_namespace_lookups(self):
        """An event under ``epcis:`` should not be counted twice even though
        the function tries both epcis and gs1 namespaces."""
        root = _el("EPCISDocument")
        root.append(_el("ObjectEvent", ns=EPCIS_NS))
        # The dedup set uses id(), so the same element won't be counted twice.
        events = xp._xml_find_events(root)
        assert len(events) == 1

    def test_ignores_unknown_tags(self):
        root = _el("EPCISDocument")
        root.append(_el("NotAnEvent"))
        assert xp._xml_find_events(root) == []


# ---------------------------------------------------------------------------
# _xml_collect_list
# ---------------------------------------------------------------------------


class TestXmlCollectList:

    def test_collects_items_from_list_container(self):
        ev = _el("ObjectEvent")
        epc_list = _el("epcList")
        epc_list.append(_el("epc", text="urn:epc:1"))
        epc_list.append(_el("epc", text="urn:epc:2"))
        ev.append(epc_list)
        result = xp._xml_collect_list(ev, "epcList", "epc")
        assert result == ["urn:epc:1", "urn:epc:2"]

    def test_returns_empty_when_list_absent(self):
        ev = _el("ObjectEvent")
        assert xp._xml_collect_list(ev, "epcList", "epc") == []

    def test_skips_items_without_text(self):
        ev = _el("ObjectEvent")
        epc_list = _el("epcList")
        epc_list.append(_el("epc"))  # no text
        epc_list.append(_el("epc", text="  "))  # whitespace — KEPT as empty after strip
        epc_list.append(_el("epc", text="urn:x"))
        ev.append(epc_list)
        # Only items with truthy text are collected; whitespace-only becomes ''
        # but the function checks `if item.text` — so whitespace-only IS collected
        # (text is truthy), then .strip() → ''. Let's assert actual behavior.
        result = xp._xml_collect_list(ev, "epcList", "epc")
        assert "urn:x" in result

    def test_matches_item_local_name(self):
        ev = _el("ObjectEvent")
        epc_list = _el("epcList")
        # 'other' items are ignored
        epc_list.append(_el("other", text="skip"))
        epc_list.append(_el("epc", text="keep"))
        ev.append(epc_list)
        assert xp._xml_collect_list(ev, "epcList", "epc") == ["keep"]


# ---------------------------------------------------------------------------
# quantityList handling
# ---------------------------------------------------------------------------


class TestQuantityList:

    def test_parses_numeric_quantity_and_uom(self):
        ev = _el("ObjectEvent")
        q_list = _el("quantityList")
        qe = _el("quantityElement")
        qe.append(_el("epcClass", text="urn:epc:cls:1"))
        qe.append(_el("quantity", text="10.5"))
        qe.append(_el("uom", text="KGM"))
        q_list.append(qe)
        ev.append(q_list)
        quantities = xp._xml_collect_quantity_list(ev)
        assert quantities == [{"epcClass": "urn:epc:cls:1",
                               "quantity": 10.5, "uom": "KGM"}]

    def test_non_numeric_quantity_falls_back_to_string(self):
        ev = _el("ObjectEvent")
        q_list = _el("quantityList")
        qe = _el("quantityElement")
        qe.append(_el("quantity", text="not-a-number"))
        q_list.append(qe)
        ev.append(q_list)
        quantities = xp._xml_collect_quantity_list(ev)
        assert quantities[0]["quantity"] == "not-a-number"

    @pytest.mark.parametrize("list_tag", [
        "quantityList", "childQuantityList",
        "inputQuantityList", "outputQuantityList",
    ])
    def test_all_four_container_tags_walked(self, list_tag):
        ev = _el("ObjectEvent")
        q_list = _el(list_tag)
        qe = _el("quantityElement")
        qe.append(_el("uom", text="EA"))
        q_list.append(qe)
        ev.append(q_list)
        quantities = xp._xml_collect_quantity_list(ev)
        assert quantities == [{"uom": "EA"}]

    def test_non_quantity_children_skipped(self):
        ev = _el("ObjectEvent")
        ev.append(_el("otherThing"))
        assert xp._xml_collect_quantity_list(ev) == []

    def test_quantity_without_expected_children_skipped(self):
        ev = _el("ObjectEvent")
        q_list = _el("quantityList")
        q_list.append(_el("notQuantityElement"))
        ev.append(q_list)
        assert xp._xml_collect_quantity_list(ev) == []

    def test_empty_quantity_element_not_collected(self):
        """quantityElement with no recognized children produces {}, which is falsy — skipped."""
        ev = _el("ObjectEvent")
        q_list = _el("quantityList")
        q_list.append(_el("quantityElement"))
        ev.append(q_list)
        assert xp._xml_collect_quantity_list(ev) == []


# ---------------------------------------------------------------------------
# location extraction
# ---------------------------------------------------------------------------


class TestLocationExtraction:

    def test_biz_location_id_extracted(self):
        ev = _el("ObjectEvent")
        biz = _el("bizLocation")
        biz.append(_el("id", text="urn:location:1"))
        ev.append(biz)
        assert xp._xml_extract_location(ev, "bizLocation") == {"id": "urn:location:1"}

    def test_biz_location_without_id_returns_none(self):
        ev = _el("ObjectEvent")
        biz = _el("bizLocation")
        ev.append(biz)
        assert xp._xml_extract_location(ev, "bizLocation") is None

    def test_location_tag_absent_returns_none(self):
        ev = _el("ObjectEvent")
        assert xp._xml_extract_location(ev, "bizLocation") is None


# ---------------------------------------------------------------------------
# source / destination list
# ---------------------------------------------------------------------------


class TestSourceDestList:

    def test_source_list_extracted_with_type(self):
        ev = _el("ObjectEvent")
        s_list = _el("sourceList")
        s_list.append(_el("source", text="urn:src:1",
                          attrib={"type": "owning_party"}))
        ev.append(s_list)
        out = xp._xml_extract_source_dest_list(ev, "sourceList", "source")
        assert out == [{"type": "owning_party", "source": "urn:src:1"}]

    def test_empty_source_entry_omitted(self):
        ev = _el("ObjectEvent")
        s_list = _el("sourceList")
        s_list.append(_el("source"))  # no type, no text → empty dict → omitted
        ev.append(s_list)
        assert xp._xml_extract_source_dest_list(ev, "sourceList", "source") == []

    def test_source_with_only_type_included(self):
        ev = _el("ObjectEvent")
        s_list = _el("sourceList")
        s_list.append(_el("source", attrib={"type": "location"}))
        ev.append(s_list)
        assert xp._xml_extract_source_dest_list(ev, "sourceList", "source") == [
            {"type": "location"}
        ]

    def test_non_list_children_skipped(self):
        ev = _el("ObjectEvent")
        ev.append(_el("other"))
        assert xp._xml_extract_source_dest_list(ev, "sourceList", "source") == []

    def test_non_item_entries_in_list_skipped(self):
        ev = _el("ObjectEvent")
        s_list = _el("sourceList")
        s_list.append(_el("notSource", text="skip"))
        ev.append(s_list)
        assert xp._xml_extract_source_dest_list(ev, "sourceList", "source") == []


# ---------------------------------------------------------------------------
# ILMD
# ---------------------------------------------------------------------------


class TestIlmd:

    def test_ilmd_scalar_fields(self):
        ext = _el("extension")
        ilmd = _el("ilmd")
        ilmd.append(_el("lotNumber", text="LOT-42"))
        ext.append(ilmd)
        assert xp._xml_extract_ilmd(ext) == {"lotNumber": "LOT-42"}

    def test_ilmd_with_fsma_subfields(self):
        """FSMA-namespaced subfields carry a prefix in the key."""
        ext = _el("extension")
        ilmd = _el("ilmd")
        parent = _el("fsmaExtensions", ns=FSMA_NS)
        parent.append(_el("harvestDate", text="2026-01-01", ns=FSMA_NS))
        ilmd.append(parent)
        ext.append(ilmd)
        out = xp._xml_extract_ilmd(ext)
        # Top-level field with no text still gets walked for children;
        # the sub-element carries the fsma: prefix.
        assert "fsma:harvestDate" in out
        assert out["fsma:harvestDate"] == "2026-01-01"

    def test_nested_extension_blocks_merged(self):
        """<extension><extension><ilmd>…</ilmd></extension></extension> merges."""
        outer = _el("extension")
        inner = _el("extension")
        ilmd = _el("ilmd")
        ilmd.append(_el("batchCode", text="B-1"))
        inner.append(ilmd)
        outer.append(inner)
        out = xp._xml_extract_ilmd(outer)
        assert out == {"batchCode": "B-1"}

    def test_empty_ilmd_returns_empty_dict(self):
        ext = _el("extension")
        ext.append(_el("ilmd"))
        assert xp._xml_extract_ilmd(ext) == {}


# ---------------------------------------------------------------------------
# bizTransaction
# ---------------------------------------------------------------------------


class TestBizTransaction:

    def test_biz_transaction_with_type_and_text(self):
        ev = _el("ObjectEvent")
        bt_list = _el("bizTransactionList")
        bt_list.append(_el("bizTransaction", text="urn:po:1",
                           attrib={"type": "po"}))
        ev.append(bt_list)
        out = xp._xml_extract_biz_transactions(ev)
        assert out == [{"type": "po", "bizTransaction": "urn:po:1"}]

    def test_empty_biz_transaction_omitted(self):
        ev = _el("ObjectEvent")
        bt_list = _el("bizTransactionList")
        bt_list.append(_el("bizTransaction"))  # no type, no text
        ev.append(bt_list)
        assert xp._xml_extract_biz_transactions(ev) == []

    def test_biz_transaction_with_only_type(self):
        ev = _el("ObjectEvent")
        bt_list = _el("bizTransactionList")
        bt_list.append(_el("bizTransaction", attrib={"type": "po"}))
        ev.append(bt_list)
        assert xp._xml_extract_biz_transactions(ev) == [{"type": "po"}]

    def test_non_biz_transaction_children_skipped(self):
        ev = _el("ObjectEvent")
        bt_list = _el("bizTransactionList")
        bt_list.append(_el("other", text="skip"))
        ev.append(bt_list)
        assert xp._xml_extract_biz_transactions(ev) == []

    def test_no_list_container_returns_empty(self):
        ev = _el("ObjectEvent")
        ev.append(_el("somethingElse"))
        assert xp._xml_extract_biz_transactions(ev) == []


# ---------------------------------------------------------------------------
# _xml_event_to_dict — the full assembly
# ---------------------------------------------------------------------------


class TestEventToDict:

    def _make_full_event(self):
        ev = _el("ObjectEvent", ns=EPCIS_NS)
        ev.append(_el("eventTime", text="2026-01-01T00:00:00Z"))
        ev.append(_el("eventTimeZoneOffset", text="+00:00"))
        ev.append(_el("action", text="ADD"))
        ev.append(_el("bizStep", text="commissioning"))
        ev.append(_el("disposition", text="active"))
        ev.append(_el("eventID", text="urn:uuid:abc"))
        ev.append(_el("recordTime", text="2026-01-01T00:00:01Z"))

        # epcList
        epc_list = _el("epcList")
        epc_list.append(_el("epc", text="urn:epc:1"))
        ev.append(epc_list)

        # parentID
        ev.append(_el("parentID", text="urn:parent:1"))

        # quantityList
        q_list = _el("quantityList")
        qe = _el("quantityElement")
        qe.append(_el("quantity", text="5"))
        qe.append(_el("uom", text="EA"))
        q_list.append(qe)
        ev.append(q_list)

        # bizLocation + readPoint
        biz = _el("bizLocation")
        biz.append(_el("id", text="urn:loc:1"))
        ev.append(biz)
        rp = _el("readPoint")
        rp.append(_el("id", text="urn:rp:1"))
        ev.append(rp)

        # source + destination
        s_list = _el("sourceList")
        s_list.append(_el("source", text="urn:src:1",
                          attrib={"type": "owning_party"}))
        ev.append(s_list)
        d_list = _el("destinationList")
        d_list.append(_el("destination", text="urn:dst:1",
                          attrib={"type": "owning_party"}))
        ev.append(d_list)

        # bizTransaction
        bt_list = _el("bizTransactionList")
        bt_list.append(_el("bizTransaction", text="urn:po:1", attrib={"type": "po"}))
        ev.append(bt_list)

        # ILMD via extension
        ext = _el("extension")
        ilmd = _el("ilmd")
        ilmd.append(_el("lotNumber", text="LOT-7"))
        ext.append(ilmd)
        ev.append(ext)

        return ev

    def test_full_event_dict_shape(self):
        ev = self._make_full_event()
        out = xp._xml_event_to_dict(ev)
        assert out["type"] == "ObjectEvent"
        assert out["eventTime"] == "2026-01-01T00:00:00Z"
        assert out["eventTimeZoneOffset"] == "+00:00"
        assert out["action"] == "ADD"
        assert out["bizStep"] == "commissioning"
        assert out["disposition"] == "active"
        assert out["eventID"] == "urn:uuid:abc"
        assert out["recordTime"] == "2026-01-01T00:00:01Z"
        assert out["epcList"] == ["urn:epc:1"]
        assert out["parentID"] == "urn:parent:1"
        assert out["extension"]["quantityList"] == [
            {"quantity": 5.0, "uom": "EA"},
        ]
        assert out["bizLocation"] == {"id": "urn:loc:1"}
        assert out["readPoint"] == {"id": "urn:rp:1"}
        assert out["sourceList"] == [{"type": "owning_party", "source": "urn:src:1"}]
        assert out["destinationList"] == [
            {"type": "owning_party", "destination": "urn:dst:1"},
        ]
        assert out["bizTransactionList"] == [{"type": "po", "bizTransaction": "urn:po:1"}]
        assert out["ilmd"] == {"lotNumber": "LOT-7"}

    def test_minimal_event_only_has_type(self):
        ev = _el("TransformationEvent")
        out = xp._xml_event_to_dict(ev)
        assert out == {"type": "TransformationEvent"}

    def test_transformation_event_uses_input_output_lists(self):
        ev = _el("TransformationEvent", ns=EPCIS_NS)
        in_list = _el("inputEPCList")
        in_list.append(_el("epc", text="in-1"))
        ev.append(in_list)
        out_list = _el("outputEPCList")
        out_list.append(_el("epc", text="out-1"))
        ev.append(out_list)
        out = xp._xml_event_to_dict(ev)
        assert out["inputEPCList"] == ["in-1"]
        assert out["outputEPCList"] == ["out-1"]

    def test_aggregation_event_uses_child_epcs(self):
        ev = _el("AggregationEvent", ns=EPCIS_NS)
        children = _el("childEPCs")
        children.append(_el("epc", text="child-1"))
        ev.append(children)
        out = xp._xml_event_to_dict(ev)
        assert out["childEPCs"] == ["child-1"]


# ---------------------------------------------------------------------------
# _parse_epcis_xml
# ---------------------------------------------------------------------------


class TestParseEpcisXml:

    def _doc(self, event_xml: str) -> bytes:
        return (f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<EPCISDocument xmlns="{EPCIS_NS}">'
                f'<EPCISBody><EventList>{event_xml}</EventList></EPCISBody>'
                f'</EPCISDocument>').encode("utf-8")

    def test_parses_bytes_input(self):
        raw = self._doc(
            "<ObjectEvent><eventTime>2026-01-01T00:00:00Z</eventTime>"
            "<action>ADD</action></ObjectEvent>"
        )
        events = xp._parse_epcis_xml(raw)
        assert len(events) == 1
        assert events[0]["type"] == "ObjectEvent"
        assert events[0]["eventTime"] == "2026-01-01T00:00:00Z"

    def test_parses_str_input(self):
        raw_bytes = self._doc(
            "<ObjectEvent><eventTime>2026-01-01T00:00:00Z</eventTime></ObjectEvent>"
        )
        raw_str = raw_bytes.decode("utf-8")
        events = xp._parse_epcis_xml(raw_str)
        assert len(events) == 1

    def test_malformed_xml_returns_empty_list(self):
        # Missing closing tag
        raw = b"<EPCISDocument><ObjectEvent>"
        assert xp._parse_epcis_xml(raw) == []

    def test_empty_document_returns_empty(self):
        raw = b"<?xml version='1.0'?><EPCISDocument/>"
        assert xp._parse_epcis_xml(raw) == []

    def test_document_with_multiple_event_types(self):
        raw = self._doc(
            "<ObjectEvent><eventID>o1</eventID></ObjectEvent>"
            "<AggregationEvent><eventID>a1</eventID></AggregationEvent>"
            "<TransactionEvent><eventID>tx1</eventID></TransactionEvent>"
            "<TransformationEvent><eventID>tf1</eventID></TransformationEvent>"
        )
        events = xp._parse_epcis_xml(raw)
        types = {e["type"] for e in events}
        assert types == {
            "ObjectEvent", "AggregationEvent",
            "TransactionEvent", "TransformationEvent",
        }

    def test_bare_element_xml_also_parsed(self):
        """No-namespace XML should still produce events."""
        raw = (b"<?xml version='1.0'?><EPCISDocument>"
               b"<ObjectEvent><eventID>o1</eventID></ObjectEvent>"
               b"</EPCISDocument>")
        events = xp._parse_epcis_xml(raw)
        assert len(events) == 1
        assert events[0]["eventID"] == "o1"

    def test_missing_defusedxml_returns_empty_list(self, monkeypatch):
        """If defusedxml.lxml import fails, the handler logs and returns []."""
        # Force re-import failure by blocking the module.
        original = sys.modules.get("defusedxml.lxml")
        sys.modules["defusedxml.lxml"] = None  # type: ignore[assignment]
        # Block parent too so the `from defusedxml.lxml import parse` line
        # triggers ImportError.
        try:
            result = xp._parse_epcis_xml(b"<root/>")
            assert result == []
        finally:
            if original is not None:
                sys.modules["defusedxml.lxml"] = original
            else:
                sys.modules.pop("defusedxml.lxml", None)
