"""EPCIS 2.0 XML parsing utilities.

Handles XML namespace constants, element traversal, and conversion of
EPCIS XML documents into the canonical dict format used by the JSON-LD path.
"""

from __future__ import annotations

import io
import logging
from typing import Any

logger = logging.getLogger("epcis-ingestion")

# ---------------------------------------------------------------------------
# EPCIS 2.0 XML Namespace constants
# ---------------------------------------------------------------------------
_EPCIS_NS = "urn:epcglobal:epcis:xsd:2"
_CBV_NS = "urn:epcglobal:cbv:xsd"
_EPCIS_QUERY_NS = "urn:epcglobal:epcis-query:xsd:2"
_FSMA_NS = "urn:fsma:food:traceability"
_GS1_NS = "https://ref.gs1.org/standards/epcis/2.0.0"
_SBDH_NS = "http://www.unece.org/cefact/namespaces/StandardBusinessDocumentHeader"

_NS_MAP = {
    "epcis": _EPCIS_NS,
    "cbv": _CBV_NS,
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


def _xml_local(tag: str) -> str:
    """Strip namespace from an XML tag."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _xml_child_text(element, path: str) -> str | None:
    """Get text from a direct child element by local name."""
    for child in element:
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
    for child in element:
        if _xml_local(child.tag) == list_tag:
            for item in child:
                if _xml_local(item.tag) == item_tag and item.text:
                    items.append(item.text.strip())
    return items


def _xml_collect_quantity_list(element) -> list[dict]:
    """Extract quantityList elements from an event."""
    quantity_tags = {"quantityList", "childQuantityList", "inputQuantityList", "outputQuantityList"}
    quantities: list[dict] = []
    for child in element:
        if _xml_local(child.tag) not in quantity_tags:
            continue
        for qe in child:
            if _xml_local(qe.tag) != "quantityElement":
                continue
            q = _xml_parse_quantity_element(qe)
            if q:
                quantities.append(q)
    return quantities


def _xml_parse_quantity_element(qe) -> dict[str, Any]:
    """Parse a single quantityElement."""
    q: dict[str, Any] = {}
    for field in qe:
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
    for child in element:
        if _xml_local(child.tag) == tag_name:
            loc_id = _xml_child_text(child, "id")
            if loc_id:
                return {"id": loc_id}
    return None


def _xml_extract_source_dest_list(element, list_tag: str, item_tag: str) -> list[dict]:
    """Extract sourceList/destinationList."""
    results: list[dict] = []
    for child in element:
        if _xml_local(child.tag) != list_tag:
            continue
        for item in child:
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


def _xml_ns_prefix(tag: str) -> str:
    """Reconstruct namespace prefix for downstream compatibility."""
    if "}" not in tag:
        return ""
    ns_uri = tag.split("}")[0].lstrip("{")
    for prefix, uri in _NS_MAP.items():
        if uri == ns_uri:
            return f"{prefix}:"
    return ""


def _xml_extract_ilmd(element) -> dict:
    """Extract ILMD (Instance/Lot Master Data) including FSMA extensions."""
    ilmd: dict[str, Any] = {}
    for child in element:
        local = _xml_local(child.tag)
        if local == "ilmd":
            _xml_populate_ilmd_fields(child, ilmd)
        elif local == "extension":
            nested = _xml_extract_ilmd(child)
            ilmd.update(nested)
    return ilmd


def _xml_populate_ilmd_fields(ilmd_element, ilmd: dict) -> None:
    """Populate ilmd dict from an ilmd XML element."""
    for field in ilmd_element:
        fl = _xml_local(field.tag)
        ns = _xml_ns_prefix(field.tag)
        key = f"{ns}{fl}" if ns else fl
        if field.text and field.text.strip():
            ilmd[key] = field.text.strip()
        for sub in field:
            sub_local = _xml_local(sub.tag)
            sub_ns = _xml_ns_prefix(sub.tag)
            sub_key = f"{sub_ns}{sub_local}" if sub_ns else sub_local
            if sub.text and sub.text.strip():
                ilmd[sub_key] = sub.text.strip()


def _xml_extract_biz_transactions(ev_element) -> list[dict]:
    """Extract bizTransactionList from an event element."""
    biz_transactions: list[dict] = []
    for child in ev_element:
        if _xml_local(child.tag) != "bizTransactionList":
            continue
        for bt in child:
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
    for field_name in ("eventTime", "eventTimeZoneOffset", "action", "bizStep",
                       "disposition", "eventID", "recordTime"):
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

    # Quantity lists
    quantities = _xml_collect_quantity_list(ev_element)
    if quantities:
        event.setdefault("extension", {})["quantityList"] = quantities

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


def _parse_epcis_xml(raw: bytes | str) -> list[dict]:
    """Parse EPCIS 2.0 XML document and return a list of event dicts.

    Supports both namespace-qualified and bare-element XML. Extracts all four
    event types and converts them into the same dict structure used by the
    JSON-LD path so downstream normalization works identically.
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
        logger.warning("epcis_xml_parse_failed error=%s", str(exc))
        return []

    event_elements = _xml_find_events(root)
    return [_xml_event_to_dict(ev) for ev in event_elements]


def _is_xml_content(raw: bytes) -> bool:
    """Detect whether raw bytes look like XML content."""
    stripped = raw.lstrip()
    return stripped[:5] == b"<?xml" or stripped[:1] == b"<"
