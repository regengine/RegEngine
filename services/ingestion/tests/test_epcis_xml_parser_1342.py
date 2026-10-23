"""Data-free coverage for app/epcis/xml_parser.py.

No EPCIS event documents, GS1 identifiers, or lot codes. Namespace helpers
run on plain strings. Element walkers run on empty lxml elements, comments,
and processing instructions. ``_parse_epcis_xml`` is exercised with
malformed bytes, an empty document, and a comment-only document.

Issue: #1342
"""

from __future__ import annotations

import sys

import pytest
from app.epcis import xml_parser as xp
from lxml import etree  # type: ignore

EPCIS_NS = "urn:epcglobal:epcis:xsd:2"
FSMA_NS = "urn:fsma:food:traceability"


def _el(tag: str, *, ns: str | None = None):
    """Build an empty lxml element. No text and no attributes."""
    qname = f"{{{ns}}}{tag}" if ns else tag
    return etree.Element(qname)


class TestNamespaceHelpers:
    def test_xml_local_strips_namespace(self):
        assert xp._xml_local("{urn:example}tag") == "tag"

    def test_xml_local_passes_through_bare_tag(self):
        assert xp._xml_local("plain") == "plain"

    def test_xml_local_on_comment_tag_is_empty(self):
        comment = etree.Comment("note")
        assert xp._xml_local(comment.tag) == ""

    def test_xml_ns_prefix_for_known_uri(self):
        assert xp._xml_ns_prefix(f"{{{EPCIS_NS}}}foo") == "epcis:"
        assert xp._xml_ns_prefix(f"{{{FSMA_NS}}}foo") == "fsma:"

    def test_xml_ns_prefix_unknown_ns_returns_empty(self):
        assert xp._xml_ns_prefix("{unknown:ns}foo") == ""

    def test_xml_ns_prefix_no_ns_returns_empty(self):
        assert xp._xml_ns_prefix("plain") == ""

    def test_xml_ns_prefix_on_comment_tag_is_empty(self):
        comment = etree.Comment("note")
        assert xp._xml_ns_prefix(comment.tag) == ""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            (b"<?xml version='1.0'?><root/>", True),
            (b"<root/>", True),
            (b"   <root/>", True),
            (b'{"json": true}', False),
            (b"plain text", False),
            (b"", False),
        ],
    )
    def test_is_xml_content(self, raw, expected):
        assert xp._is_xml_content(raw) is expected


class TestEmptyElementsAndComments:
    """Parser helpers on empty elements, comments, and processing instructions."""

    def test_elements_skip_comments_and_processing_instructions(self):
        parent = _el("root")
        comment = etree.Comment("note")
        instruction = etree.ProcessingInstruction("target", "data")
        parent.append(comment)
        parent.append(instruction)
        assert list(parent) == [comment, instruction]
        assert list(xp._xml_elements(parent)) == []

    def test_child_text_on_empty_element_is_none(self):
        assert xp._xml_child_text(_el("root"), "child") is None

    def test_child_text_ignores_comment_sibling(self):
        parent = _el("root")
        parent.append(etree.Comment("note"))
        parent.append(_el("child"))
        assert xp._xml_child_text(parent, "child") is None

    def test_find_events_on_empty_parent_is_empty(self):
        root = _el("EPCISDocument")
        root.append(etree.Comment("note"))
        assert xp._xml_find_events(root) == []

    def test_find_events_ignores_unknown_empty_tag(self):
        root = _el("EPCISDocument")
        root.append(_el("NotAnEvent"))
        assert xp._xml_find_events(root) == []

    def test_collect_list_on_empty_element_is_empty(self):
        assert xp._xml_collect_list(_el("parent"), "epcList", "epc") == []

    def test_quantity_list_on_empty_element_is_empty(self):
        assert xp._xml_collect_quantity_list(_el("parent")) == []

    def test_empty_quantity_element_not_collected(self):
        parent = _el("parent")
        container = _el("quantityList")
        container.append(_el("quantityElement"))
        parent.append(container)
        assert xp._xml_collect_quantity_list(parent) == []

    def test_location_on_empty_element_is_none(self):
        parent = _el("parent")
        parent.append(_el("bizLocation"))
        assert xp._xml_extract_location(parent, "bizLocation") is None
        assert xp._xml_extract_location(_el("parent"), "bizLocation") is None

    def test_source_dest_on_empty_element_is_empty(self):
        parent = _el("parent")
        container = _el("sourceList")
        container.append(_el("source"))
        parent.append(container)
        assert xp._xml_extract_source_dest_list(parent, "sourceList", "source") == []
        assert xp._xml_extract_source_dest_list(_el("parent"), "sourceList", "source") == []

    def test_ilmd_on_empty_element_is_empty(self):
        parent = _el("extension")
        parent.append(_el("ilmd"))
        assert xp._xml_extract_ilmd(parent) == {}
        assert xp._xml_extract_ilmd(_el("extension")) == {}

    def test_biz_transactions_on_empty_element_is_empty(self):
        parent = _el("parent")
        container = _el("bizTransactionList")
        container.append(_el("bizTransaction"))
        parent.append(container)
        assert xp._xml_extract_biz_transactions(parent) == []
        assert xp._xml_extract_biz_transactions(_el("parent")) == []

    def test_event_to_dict_on_empty_element_has_only_type(self):
        empty = _el("TransformationEvent")
        empty.append(etree.Comment("note"))
        assert xp._xml_event_to_dict(empty) == {"type": "TransformationEvent"}


class TestParseEpcisXml:
    def test_malformed_xml_returns_400(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as caught:
            xp._parse_epcis_xml(b"<a>")
        assert caught.value.status_code == 400
        detail = caught.value.detail
        assert isinstance(detail, str)
        assert detail.startswith("malformed XML")
        assert "Traceback" not in detail
        assert 'File "' not in detail

    def test_empty_document_returns_empty(self):
        raw = b"<?xml version='1.0'?><EPCISDocument/>"
        assert xp._parse_epcis_xml(raw) == []

    def test_comment_only_document_returns_empty(self):
        raw = b"<?xml version='1.0'?><EPCISDocument><!-- note --></EPCISDocument>"
        assert xp._parse_epcis_xml(raw) == []

    def test_missing_defusedxml_returns_empty_list(self):
        """If defusedxml.lxml import fails, the handler logs and returns []."""
        original = sys.modules.get("defusedxml.lxml")
        sys.modules["defusedxml.lxml"] = None  # type: ignore[assignment]
        try:
            result = xp._parse_epcis_xml(b"<root/>")
            assert result == []
        finally:
            if original is not None:
                sys.modules["defusedxml.lxml"] = original
            else:
                sys.modules.pop("defusedxml.lxml", None)
