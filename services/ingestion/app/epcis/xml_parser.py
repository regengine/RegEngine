"""EPCIS 2.0 XML parsing utilities.

Handles XML namespace constants, element traversal, and conversion of
EPCIS XML documents into the canonical dict format used by the JSON-LD path.
"""

from __future__ import annotations

import io
import logging
import os
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger("epcis-ingestion")


def _strict_fsma_validation() -> bool:
    """Return True when parse-time FSMA validation MUST reject invalid events (#1151).

    Default: strict. ``STRICT_FSMA_VALIDATION=false`` disables the parse
    gate so a malformed event is only logged as WARNING instead of
    surfaced as HTTP 422. FDA/SMB tenants may temporarily need lenient
    mode during onboarding; it is not intended for steady-state use.

    Falls back to legacy ``FSMA_STRICT_MODE`` when ``STRICT_FSMA_VALIDATION``
    is unset so operators can use either name interchangeably.
    """
    explicit = os.getenv("STRICT_FSMA_VALIDATION")
    if explicit is None:
        explicit = os.getenv("FSMA_STRICT_MODE")
    if explicit is None:
        return True
    return explicit.strip().lower() in {"1", "true", "yes", "on", "strict"}


# ---------------------------------------------------------------------------
# EPCIS 2.0 XML Namespace constants
# ---------------------------------------------------------------------------
_EPCIS_NS = "urn:epcglobal:epcis:xsd:2"
_CBV_NS = "urn:epcglobal:cbv:xsd"
_EPCIS_QUERY_NS = "urn:epcglobal:epcis-query:xsd:2"
_FSMA_NS = "urn:fsma:food:traceability"
_GS1_NS = "https://ref.gs1.org/standards/epcis/2.0.0"
_SBDH_NS = "http://www.unece.org/cefact/namespaces/StandardBusinessDocumentHeader"
_CBVMDA_NS = "urn:epcglobal:cbv:mda"

_NS_MAP = {
    "epcis": _EPCIS_NS,
    "cbv": _CBV_NS,
    "cbvmda": _CBVMDA_NS,
    "fsma": _FSMA_NS,
    "gs1": _GS1_NS,
    "sbdh": _SBDH_NS,
    "epcisq": _EPCIS_QUERY_NS,
}

_EVENT_TYPE_TAGS = [
    "ObjectEvent",
    "AggregationEvent",
    "TransactionEvent",
    "TransformationEvent",
]


def _xml_local(tag: object) -> str:
    """Strip namespace from an XML tag.

    Comment and processing-instruction nodes have a callable ``tag``.
    Those are not elements; callers skip them, and this returns ``""``
    if one is passed in anyway.
    """
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _xml_elements(parent):
    """Child elements only. Comments and processing instructions are skipped."""
    for node in parent:
        if isinstance(getattr(node, "tag", None), str):
            yield node


def _xml_child_text(element, path: str) -> str | None:
    """Get text from a direct child element by local name."""
    for child in _xml_elements(element):
        if _xml_local(child.tag) == path:
            return (child.text or "").strip() or None
    return None


def _xml_find_events(parent) -> list:
    """Find all EPCIS event elements, deduplicating."""
    events = []
    for tag_name in _EVENT_TYPE_TAGS:
        for ns_uri in [_EPCIS_NS, _GS1_NS, ""]:
            qname = f"{{{ns_uri}}}{tag_name}" if ns_uri else tag_name
            events.extend(parent.iter(qname))
    seen: set[int] = set()
    unique = []
    for ev in events:
        eid = id(ev)
        if eid not in seen:
            seen.add(eid)
            unique.append(ev)
    return unique


def _xml_collect_list(element, list_tag: str, item_tag: str) -> list[str]:
    """Collect text values from a list container element."""
    items = []
    for child in _xml_elements(element):
        if _xml_local(child.tag) == list_tag:
            for item in _xml_elements(child):
                if _xml_local(item.tag) == item_tag and item.text:
                    items.append(item.text.strip())
    return items


def _xml_collect_quantity_list(element) -> list[dict]:
    """Extract quantityList elements from an event."""
    quantity_tags = {"quantityList", "childQuantityList", "inputQuantityList", "outputQuantityList"}
    quantities: list[dict] = []
    for child in _xml_elements(element):
        if _xml_local(child.tag) not in quantity_tags:
            continue
        for qe in _xml_elements(child):
            if _xml_local(qe.tag) != "quantityElement":
                continue
            q = _xml_parse_quantity_element(qe)
            if q:
                quantities.append(q)
    return quantities


_QUANTITY_LIST_TAGS = ("quantityList", "childQuantityList", "inputQuantityList", "outputQuantityList")


def _xml_quantity_lists_by_name(element) -> dict[str, list[dict]]:
    """Quantity lists keyed by their element name.

    ``_xml_collect_quantity_list`` still concatenates every list for the
    callers that walk one tag at a time. The event dict keeps them apart:
    a TransformationEvent's output list must not be prefixed by its inputs,
    and an AggregationEvent's ``childQuantityList`` is not a ``quantityList``.
    """
    found: dict[str, list[dict]] = {}
    for child in _xml_elements(element):
        local = _xml_local(child.tag)
        if local not in _QUANTITY_LIST_TAGS:
            continue
        quantities: list[dict] = []
        for qe in _xml_elements(child):
            if _xml_local(qe.tag) != "quantityElement":
                continue
            parsed = _xml_parse_quantity_element(qe)
            if parsed:
                quantities.append(parsed)
        if quantities:
            found.setdefault(local, []).extend(quantities)
    return found


def _xml_parse_quantity_element(qe) -> dict[str, Any]:
    """Parse a single quantityElement."""
    q: dict[str, Any] = {}
    for field in _xml_elements(qe):
        fl = _xml_local(field.tag)
        if fl == "epcClass" and field.text:
            q["epcClass"] = field.text.strip()
        elif fl == "quantity" and field.text:
            try:
                q["quantity"] = float(field.text.strip())
            except ValueError:
                q["quantity"] = field.text.strip()
        elif fl == "uom" and field.text:
            q["uom"] = field.text.strip()
    return q


def _xml_extract_location(element, tag_name: str) -> dict | None:
    """Extract bizLocation or readPoint as {id: ...}."""
    for child in _xml_elements(element):
        if _xml_local(child.tag) == tag_name:
            loc_id = _xml_child_text(child, "id")
            if loc_id:
                return {"id": loc_id}
    return None


def _xml_extract_source_dest_list(element, list_tag: str, item_tag: str) -> list[dict]:
    """Extract sourceList/destinationList."""
    results: list[dict] = []
    for child in _xml_elements(element):
        if _xml_local(child.tag) != list_tag:
            continue
        for item in _xml_elements(child):
            if _xml_local(item.tag) != item_tag:
                continue
            entry: dict[str, str] = {}
            stype = item.get("type") or ""
            if stype:
                entry["type"] = stype
            if item.text and item.text.strip():
                entry[item_tag.lower()] = item.text.strip()
            if entry:
                results.append(entry)
    return results


def _xml_ns_prefix(tag: object) -> str:
    """Reconstruct namespace prefix for downstream compatibility."""
    if not isinstance(tag, str) or "}" not in tag:
        return ""
    ns_uri = tag.split("}")[0].lstrip("{")
    for prefix, uri in _NS_MAP.items():
        if uri == ns_uri:
            return f"{prefix}:"
    return ""


def _xml_extract_ilmd(element) -> dict:
    """Extract ILMD (Instance/Lot Master Data) including FSMA extensions."""
    ilmd: dict[str, Any] = {}
    for child in _xml_elements(element):
        local = _xml_local(child.tag)
        if local == "ilmd":
            _xml_populate_ilmd_fields(child, ilmd)
        elif local == "extension":
            nested = _xml_extract_ilmd(child)
            ilmd.update(nested)
    return ilmd


def _xml_populate_ilmd_fields(ilmd_element, ilmd: dict) -> None:
    """Populate ilmd dict from an ilmd XML element."""
    for field in _xml_elements(ilmd_element):
        fl = _xml_local(field.tag)
        ns = _xml_ns_prefix(field.tag)
        key = f"{ns}{fl}" if ns else fl
        if field.text and field.text.strip():
            ilmd[key] = field.text.strip()
        for sub in _xml_elements(field):
            sub_local = _xml_local(sub.tag)
            sub_ns = _xml_ns_prefix(sub.tag)
            sub_key = f"{sub_ns}{sub_local}" if sub_ns else sub_local
            if sub.text and sub.text.strip():
                ilmd[sub_key] = sub.text.strip()


def _xml_extract_biz_transactions(ev_element) -> list[dict]:
    """Extract bizTransactionList from an event element."""
    biz_transactions: list[dict] = []
    for child in _xml_elements(ev_element):
        if _xml_local(child.tag) != "bizTransactionList":
            continue
        for bt in _xml_elements(child):
            if _xml_local(bt.tag) != "bizTransaction":
                continue
            bt_entry: dict[str, str] = {}
            if bt.get("type"):
                bt_entry["type"] = bt.get("type", "")
            if bt.text and bt.text.strip():
                bt_entry["bizTransaction"] = bt.text.strip()
            if bt_entry:
                biz_transactions.append(bt_entry)
    return biz_transactions


def _xml_event_to_dict(ev_element) -> dict:
    """Convert an XML event element into the canonical dict format."""
    event_type = _xml_local(ev_element.tag)
    event: dict[str, Any] = {"type": event_type}

    # Core scalar fields
    # #2970: ``transformationID`` identifies a TransformationEvent, which
    # has no ``action``; without it the XML path cannot satisfy the
    # structural validator for a conformant transformation.
    for field_name in (
        "eventTime",
        "eventTimeZoneOffset",
        "action",
        "bizStep",
        "disposition",
        "eventID",
        "recordTime",
        "transformationID",
    ):
        val = _xml_child_text(ev_element, field_name)
        if val:
            event[field_name] = val

    # EPC lists
    for list_tag, item_tag, key in [
        ("epcList", "epc", "epcList"),
        ("childEPCs", "epc", "childEPCs"),
        ("inputEPCList", "epc", "inputEPCList"),
        ("outputEPCList", "epc", "outputEPCList"),
    ]:
        items = _xml_collect_list(ev_element, list_tag, item_tag)
        if items:
            event[key] = items

    parent_id = _xml_child_text(ev_element, "parentID")
    if parent_id:
        event["parentID"] = parent_id

    # Quantity lists. ``quantityList`` stays under ``extension`` — that is
    # the shape the EPCIS 1.x XML path and the existing full-event test
    # use. The other three lists are distinct members.
    for list_name, quantities in _xml_quantity_lists_by_name(ev_element).items():
        if list_name == "quantityList":
            event.setdefault("extension", {})["quantityList"] = quantities
        else:
            event[list_name] = quantities

    # Locations
    for tag, key in [("bizLocation", "bizLocation"), ("readPoint", "readPoint")]:
        loc = _xml_extract_location(ev_element, tag)
        if loc:
            event[key] = loc

    # Source / Destination
    sources = _xml_extract_source_dest_list(ev_element, "sourceList", "source")
    if sources:
        event["sourceList"] = sources
    destinations = _xml_extract_source_dest_list(ev_element, "destinationList", "destination")
    if destinations:
        event["destinationList"] = destinations

    # ILMD
    ilmd = _xml_extract_ilmd(ev_element)
    if ilmd:
        event["ilmd"] = ilmd

    # Business transactions
    biz_transactions = _xml_extract_biz_transactions(ev_element)
    if biz_transactions:
        event["bizTransactionList"] = biz_transactions

    return event


def _malformed_xml_detail(exc: BaseException) -> str | None:
    """Client-facing detail for a real XML parse failure, or None.

    Only lxml syntax errors and defusedxml's own rejections (DTD, entities,
    external references) count. Anything else is a bug and must not be
    relabelled as malformed input. The detail is the words "malformed XML"
    plus line and column when the parser reported them. The parser's own
    message is omitted: it can contain filesystem paths and library internals.
    """
    syntax_types: tuple[type, ...] = ()
    defused_types: tuple[type, ...] = ()
    try:
        from lxml.etree import XMLSyntaxError

        syntax_types = (XMLSyntaxError,)
    except ImportError:
        pass
    try:
        from defusedxml.common import DefusedXmlException

        defused_types = (DefusedXmlException,)
    except ImportError:
        pass
    if not isinstance(exc, syntax_types + defused_types):
        return None

    line = getattr(exc, "lineno", None)
    column = getattr(exc, "offset", None)
    position = getattr(exc, "position", None)
    if not isinstance(line, int) or line <= 0:
        if isinstance(position, tuple) and position and isinstance(position[0], int):
            line = position[0]
    if not isinstance(column, int) or column <= 0:
        if isinstance(position, tuple) and len(position) > 1 and isinstance(position[1], int):
            column = position[1]
    if isinstance(line, int) and line > 0 and isinstance(column, int) and column > 0:
        return f"malformed XML at line {line}, column {column}"
    if isinstance(line, int) and line > 0:
        return f"malformed XML at line {line}"
    return "malformed XML"


def _parse_epcis_xml(raw: bytes | str) -> list[dict]:
    """Parse EPCIS 2.0 XML document and return a list of event dicts.

    Supports both namespace-qualified and bare-element XML. Extracts all four
    event types and converts them into the same dict structure used by the
    JSON-LD path so downstream normalization works identically.

    #1151: After extraction, each event is run through ``_validate_epcis``.
    In strict mode (default, ``STRICT_FSMA_VALIDATION=true``) any event
    that fails validation causes the whole parse to raise
    ``HTTPException(422)`` with a per-index error map — previously the
    parser silently returned malformed events and the persistence layer
    either downstream-rejected them or accepted them into the graph.
    Lenient mode logs a WARNING per invalid event and returns them as
    before for legacy tenants still onboarding.
    """
    try:
        from defusedxml.lxml import parse as _safe_parse
    except ImportError:
        logger.warning("lxml_not_available_for_epcis_xml_parsing")
        return []

    if isinstance(raw, str):
        raw = raw.encode("utf-8")

    try:
        tree = _safe_parse(io.BytesIO(raw))
        root = tree.getroot()
    except Exception as exc:
        detail = _malformed_xml_detail(exc)
        if detail is None:
            # Not an XML parse failure. Propagate so the API returns 500.
            raise
        logger.warning("epcis_xml_parse_failed error=%s", detail)
        raise HTTPException(status_code=400, detail=detail) from None

    event_elements = _xml_find_events(root)
    events = [_xml_event_to_dict(ev) for ev in event_elements]

    # #1151: gate extracted events through the EPCIS structural validator.
    # Imported lazily to avoid a circular import (validation.py imports
    # from extraction.py which is sibling to this module).
    from .validation import _validate_epcis

    strict = _strict_fsma_validation()
    validation_errors: list[dict] = []
    for idx, ev in enumerate(events):
        errors = _validate_epcis(ev)
        if not errors:
            continue
        if strict:
            validation_errors.append({"index": idx, "errors": errors})
        else:
            logger.warning(
                "epcis_xml_event_validation_failed_lenient index=%d errors=%s",
                idx,
                errors,
            )

    if validation_errors:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "epcis_xml_validation_failed",
                "message": (
                    "One or more EPCIS events failed structural FSMA "
                    "validation. No events were persisted. Set "
                    "STRICT_FSMA_VALIDATION=false only for migration / "
                    "onboarding windows."
                ),
                "errors": validation_errors,
            },
        )

    return events


def _is_xml_content(raw: bytes) -> bool:
    """Detect whether raw bytes look like XML content."""
    stripped = raw.lstrip()
    return stripped[:5] == b"<?xml" or stripped[:1] == b"<"
