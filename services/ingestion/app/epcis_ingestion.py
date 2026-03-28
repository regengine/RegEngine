"""EPCIS 2.0 ingestion and validation router.

Primary path persists events to Postgres via shared CTEPersistence.
Local/test fallback keeps in-memory behavior only when DB is unavailable
outside production.

Supports both JSON-LD and XML EPCIS 2.0 payloads. Extracts FSMA KDEs
(Key Data Elements) including TLC, product description, quantities,
readPoint, bizLocation, and FSMA-specific extensions. Handles
ObjectEvent, AggregationEvent, TransactionEvent, and TransformationEvent.
"""

from __future__ import annotations

import io
import json
import logging
import os
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text

from app.shared.tenant_resolution import resolve_tenant_id
from app.webhook_compat import _verify_api_key

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


def _audit_log_validation_failure(
    errors: list[dict],
    tenant_id: str | None,
    normalized: dict,
) -> None:
    """Fire-and-forget audit log for FSMA validation failures."""
    try:
        import asyncio
        from shared.audit_logging import (
            AuditLogger,
            AuditActor,
            AuditResource,
            AuditEventType,
            AuditEventCategory,
            AuditSeverity,
        )

        failed_fields = [e.get("loc", ["unknown"])[-1] for e in errors]
        audit = AuditLogger.get_instance()
        actor = AuditActor(
            actor_id="epcis-ingestion",
            actor_type="service",
            tenant_id=tenant_id,
        )
        resource = AuditResource(
            resource_type="fsma_event",
            resource_id=normalized.get("idempotency_key") or "unknown",
            tenant_id=tenant_id,
            attributes={"tlc": normalized.get("tlc"), "event_time": normalized.get("event_time")},
        )

        coro = audit.log(
            event_type=AuditEventType.DATA_CREATE,
            category=AuditEventCategory.DATA_MODIFICATION,
            severity=AuditSeverity.WARNING,
            actor=actor,
            action="fsma_event_validation",
            outcome="failure",
            resource=resource,
            message=f"FSMAEvent validation rejected: failed KDEs {failed_fields}",
            details={"validation_errors": errors, "tenant_id": tenant_id},
            tags=["fsma", "validation", "kde_rejection"],
        )
        # Best-effort: schedule on running loop or skip
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            pass  # No running loop — skip async audit (logged via stdlib above)
    except Exception:
        logger.debug("audit_log_validation_failure: could not emit audit event", exc_info=True)


def _validate_as_fsma_event(normalized: dict, tenant_id: str | None = None) -> dict | None:
    """Validate a normalized CTE dict against the FSMAEvent Pydantic model.

    Returns the validated model dict on success, or None if validation fails
    (errors are logged and audit-trailed but do not block ingestion).
    """
    try:
        from shared.schemas import FSMAEvent, FSMAEventType

        # Map internal event_type strings to FSMAEventType enum
        event_type_map = {
            "shipping": FSMAEventType.SHIPPING,
            "receiving": FSMAEventType.RECEIVING,
            "transformation": FSMAEventType.TRANSFORMATION,
            "initial_packing": FSMAEventType.CREATION,
            "creation": FSMAEventType.CREATION,
        }
        raw_type = (normalized.get("event_type") or "receiving").lower()
        fsma_type = event_type_map.get(raw_type, FSMAEventType.RECEIVING)

        fsma_event = FSMAEvent(
            event_type=fsma_type,
            tlc=normalized.get("tlc") or "UNKNOWN",
            product_description=normalized.get("product_description") or _default_product_description(normalized),
            quantity=normalized.get("quantity"),
            unit_of_measure=normalized.get("unit_of_measure"),
            location_gln=normalized.get("location_id"),
            event_time=normalized.get("event_time") or datetime.now(timezone.utc).isoformat(),
            source_gln=normalized.get("source_location_id"),
            destination_gln=normalized.get("dest_location_id"),
            reference_document_type="EPCIS",
            reference_document_number=None,
            tenant_id=tenant_id,
        )
        return fsma_event.model_dump()
    except ValidationError as exc:
        logger.warning("fsma_event_validation_failed tenant=%s errors=%s", tenant_id, exc.errors())
        _audit_log_validation_failure(exc.errors(), tenant_id, normalized)
        return None
    except ImportError:
        logger.debug("shared.schemas not available for FSMAEvent validation")
        return None

router = APIRouter(prefix="/api/v1/epcis", tags=["EPCIS 2.0 Ingestion"])


# Backward-compatible names retained for tests and non-production fallback.
_epcis_store: dict[str, dict] = {}
_epcis_idempotency_index: dict[str, str] = {}


def _is_production() -> bool:
    from shared.env import is_production
    return is_production()


# Safety: Allow in-memory fallback only outside production.
# This prevents unintended data loss if DB unavailability is transient.
def _allow_in_memory_fallback() -> bool:
    explicit = os.getenv("ALLOW_EPCIS_IN_MEMORY_FALLBACK")
    if explicit is not None:
        return explicit.lower() in {"1", "true", "yes"}
    return not _is_production()


def _get_db_session():
    from shared.database import SessionLocal

    return SessionLocal()


_resolve_tenant_id = resolve_tenant_id


def _extract_lot_data(ilmd: dict | None) -> tuple[str, str]:
    if not ilmd:
        return "", ""
    lot_code = str(ilmd.get("cbvmda:lotNumber") or ilmd.get("lotNumber") or "")
    tlc = str(ilmd.get("fsma:traceabilityLotCode") or lot_code)
    return lot_code, tlc


def _extract_location_id(payload: dict, key: str) -> str:
    raw = payload.get(key, {})
    if isinstance(raw, dict):
        value = raw.get("id")
        return str(value) if value else ""
    return ""


def _extract_party_id(payload: dict, key: str, nested_key: str) -> str:
    items = payload.get(key, [])
    if not isinstance(items, list) or not items:
        return ""
    first = items[0] if isinstance(items[0], dict) else {}
    value = first.get(nested_key)
    return str(value) if value else ""


def _validate_gln_format(gln: str) -> bool:
    """Validate a GLN using GS1 check digit algorithm."""
    if not gln or not gln.isdigit() or len(gln) != 13:
        return False
    total = sum(
        int(digit) * (3 if index % 2 else 1)
        for index, digit in enumerate(reversed(gln[:-1]))
    )
    expected = (10 - (total % 10)) % 10
    return int(gln[-1]) == expected


def _validate_tlc_format(tlc: str) -> bool:
    """Validate TLC has minimum required length (3+ chars)."""
    return bool(tlc) and len(tlc.strip()) >= 3


def _validate_epcis(event: dict) -> list[str]:
    errors: list[str] = []
    required = ["type", "eventTime", "action", "bizStep"]
    for field in required:
        if not event.get(field):
            errors.append(f"Missing required EPCIS field '{field}'")

    if event.get("type") not in {"ObjectEvent", "AggregationEvent", "TransactionEvent", "TransformationEvent"}:
        errors.append("Unsupported EPCIS event type")

    lot_code, tlc = _extract_lot_data(event.get("ilmd") or event.get("extension", {}).get("ilmd"))
    if not tlc and not lot_code:
        errors.append("Missing traceability lot code (fsma:traceabilityLotCode or cbvmda:lotNumber)")
    elif tlc and not _validate_tlc_format(tlc):
        errors.append(f"TLC '{tlc}' is too short (minimum 3 characters)")

    return errors


def _validate_epcis_glns(normalized: dict) -> list[str]:
    """Validate GLN format on location fields, returning warnings."""
    warnings: list[str] = []
    gln_fields = ["location_id", "source_location_id", "dest_location_id"]
    for field in gln_fields:
        value = normalized.get(field)
        if value and value.isdigit() and len(value) == 13 and not _validate_gln_format(value):
            warnings.append(f"Invalid GLN check digit in {field}: {value}")
    return warnings


def _event_idempotency_key(event: dict) -> str:
    explicit = event.get("eventID")
    if explicit:
        return str(explicit)
    normalized = json.dumps(event, sort_keys=True, separators=(",", ":"))
    return sha256(normalized.encode("utf-8")).hexdigest()


def _normalize_epcis_to_cte(event: dict) -> dict:
    event_type_map = {
        "urn:epcglobal:cbv:bizstep:receiving": "receiving",
        "urn:epcglobal:cbv:bizstep:shipping": "shipping",
        "urn:epcglobal:cbv:bizstep:transforming": "transformation",
        "urn:epcglobal:cbv:bizstep:commissioning": "initial_packing",
        "urn:epcglobal:cbv:bizstep:packing": "initial_packing",
    }

    ilmd = event.get("ilmd") or event.get("extension", {}).get("ilmd") or {}
    lot_code, tlc = _extract_lot_data(ilmd)
    epc_list = event.get("epcList", [])
    product_id = epc_list[0] if isinstance(epc_list, list) and epc_list else None
    biz_step = str(event.get("bizStep") or "")

    quantity = None
    unit = None
    quantity_list = event.get("extension", {}).get("quantityList", [])
    if quantity_list and isinstance(quantity_list, list) and isinstance(quantity_list[0], dict):
        quantity = quantity_list[0].get("quantity")
        unit = quantity_list[0].get("uom")

    return {
        "event_type": event_type_map.get(biz_step, "receiving"),
        "epcis_event_type": event.get("type"),
        "epcis_action": event.get("action"),
        "epcis_biz_step": event.get("bizStep"),
        "event_time": event.get("eventTime"),
        "event_timezone": event.get("eventTimeZoneOffset", "+00:00"),
        "lot_code": lot_code,
        "tlc": tlc,
        "product_id": product_id,
        "location_id": _extract_location_id(event, "bizLocation") or _extract_location_id(event, "readPoint"),
        "source_location_id": _extract_party_id(event, "sourceList", "source"),
        "dest_location_id": _extract_party_id(event, "destinationList", "destination"),
        "quantity": quantity,
        "unit_of_measure": unit,
        "data_source": "api",
        "validation_status": "valid",
    }


def _extract_kdes(event: dict) -> list[dict]:
    ilmd = event.get("ilmd") or event.get("extension", {}).get("ilmd") or {}
    kdes: list[dict] = []
    for key, value in ilmd.items():
        if value is None:
            continue
        kde_name = key.split(":", 1)[-1]
        kdes.append(
            {
                "kde_type": kde_name,
                "kde_value": str(value),
                "required": kde_name in {"traceabilityLotCode", "lotNumber"},
            }
        )
    return kdes


def _kde_completeness(kdes: list[dict]) -> float:
    required_count = sum(1 for kde in kdes if kde["required"]) or 1
    populated_required = sum(1 for kde in kdes if kde["required"] and kde["kde_value"])
    return round(populated_required / required_count, 2)


def _compliance_alerts(normalized: dict, kdes: list[dict]) -> list[dict]:
    alerts: list[dict] = []

    if not normalized.get("tlc"):
        alerts.append(
            {
                "severity": "critical",
                "alert_type": "missing_kde",
                "message": "Traceability lot code is missing",
            }
        )

    if normalized.get("event_type") in {"shipping", "receiving"} and (
        not normalized.get("source_location_id") or not normalized.get("dest_location_id")
    ):
        alerts.append(
            {
                "severity": "warning",
                "alert_type": "incomplete_route",
                "message": "Shipping/receiving event is missing source or destination identifiers",
            }
        )

    if not kdes:
        alerts.append(
            {
                "severity": "warning",
                "alert_type": "missing_kde",
                "message": "No ILMD KDE fields were provided",
            }
        )

    return alerts


def _safe_iso(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        return value
    return datetime.now(timezone.utc).isoformat()


def _default_product_description(normalized: dict) -> str:
    product_id = normalized.get("product_id")
    if product_id:
        return f"EPCIS Product {product_id}"
    return "EPCIS Traceability Event"


def _build_kde_map(event: dict, normalized: dict, idempotency_key: str) -> dict[str, Any]:
    kde_map = {kde["kde_type"]: kde["kde_value"] for kde in _extract_kdes(event)}

    kde_map["epcis_document_json"] = json.dumps(event, sort_keys=True, separators=(",", ":"))
    kde_map["epcis_idempotency_key"] = idempotency_key

    if normalized.get("product_id"):
        kde_map["product_id"] = normalized["product_id"]
    if normalized.get("source_location_id"):
        kde_map["ship_from_gln"] = normalized["source_location_id"]
    if normalized.get("dest_location_id"):
        kde_map["ship_to_gln"] = normalized["dest_location_id"]

    return kde_map


def _query_alert_rows(db_session, tenant_id: str, event_id: str) -> list[dict]:
    # Allowlisted column identifiers for fsma.compliance_alerts dynamic SQL
    _ALLOWED_COLS = frozenset(
        {
            "tenant_id",
            "org_id",
            "cte_event_id",
            "event_id",
            "message",
            "description",
            "alert_type",
            "severity",
            "created_at",
            "id",
            "title",
            "resolved",
            "acknowledged",
            "resolved_at",
            "acknowledged_at",
            "resolved_by",
            "acknowledged_by",
            "details",
            "metadata",
            "entity_id",
        }
    )

    raw_columns = {
        row[0]
        for row in db_session.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'fsma'
                  AND table_name = 'compliance_alerts'
                """
            )
        ).fetchall()
    }
    # Only allow known-safe column names to prevent SQL injection
    columns = raw_columns & _ALLOWED_COLS
    if not columns:
        return []

    tenant_col = (
        "tenant_id"
        if "tenant_id" in columns
        else ("org_id" if "org_id" in columns else None)
    )
    event_col = (
        "cte_event_id"
        if "cte_event_id" in columns
        else ("event_id" if "event_id" in columns else None)
    )
    if tenant_col is None or event_col is None:
        return []

    message_expr = (
        "message"
        if "message" in columns
        else ("description" if "description" in columns else "alert_type")
    )
    # All interpolated identifiers are guaranteed members of _ALLOWED_COLS
    rows = db_session.execute(
        text(
            f"""
            SELECT severity, alert_type, {message_expr} AS message
            FROM fsma.compliance_alerts
            WHERE {tenant_col} = :tenant_id
              AND {event_col} = :event_id
            ORDER BY created_at DESC
            """
        ),
        {"tenant_id": tenant_id, "event_id": event_id},
    ).fetchall()
    return [
        {"severity": row.severity, "alert_type": row.alert_type, "message": row.message}
        for row in rows
    ]


def _parse_epcis_document(kdes: dict[str, Any], normalized: dict[str, Any]) -> dict:
    raw_json = kdes.get("epcis_document_json")
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            logger.warning("epcis_document_json_parse_failed")

    ilmd: dict[str, Any] = {}
    if normalized.get("lot_code"):
        ilmd["cbvmda:lotNumber"] = normalized["lot_code"]
    if normalized.get("tlc"):
        ilmd["fsma:traceabilityLotCode"] = normalized["tlc"]

    event: dict[str, Any] = {
        "type": normalized.get("epcis_event_type") or "ObjectEvent",
        "eventTime": normalized.get("event_time") or datetime.now(timezone.utc).isoformat(),
        "action": normalized.get("epcis_action") or "OBSERVE",
        "bizStep": normalized.get("epcis_biz_step") or "urn:epcglobal:cbv:bizstep:receiving",
        "ilmd": ilmd,
    }
    if normalized.get("source_location_id"):
        event["sourceList"] = [
            {"type": "urn:epcglobal:cbv:sdt:possessing_party", "source": normalized["source_location_id"]}
        ]
    if normalized.get("dest_location_id"):
        event["destinationList"] = [
            {"type": "urn:epcglobal:cbv:sdt:possessing_party", "destination": normalized["dest_location_id"]}
        ]
    return event


def _fetch_event_from_db(tenant_id: str, event_id: str) -> Optional[dict]:
    db_session = _get_db_session()
    try:
        row = db_session.execute(
            text(
                """
                SELECT
                    id::text AS id,
                    ingested_at,
                    idempotency_key,
                    event_type,
                    epcis_event_type,
                    epcis_action,
                    epcis_biz_step,
                    event_timestamp,
                    traceability_lot_code,
                    source,
                    location_gln,
                    quantity,
                    unit_of_measure
                FROM fsma.cte_events
                WHERE tenant_id = :tenant_id
                  AND id = :event_id
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "event_id": event_id},
        ).fetchone()
        if not row:
            return None

        kde_rows = db_session.execute(
            text(
                """
                SELECT kde_key, kde_value, is_required
                FROM fsma.cte_kdes
                WHERE tenant_id = :tenant_id
                  AND cte_event_id = :event_id
                """
            ),
            {"tenant_id": tenant_id, "event_id": event_id},
        ).fetchall()

        kdes = [
            {"kde_type": kde.kde_key, "kde_value": kde.kde_value, "required": bool(kde.is_required)}
            for kde in kde_rows
        ]
        kde_map = {kde["kde_type"]: kde["kde_value"] for kde in kdes}

        normalized = {
            "event_type": row.event_type,
            "epcis_event_type": row.epcis_event_type,
            "epcis_action": row.epcis_action,
            "epcis_biz_step": row.epcis_biz_step,
            "event_time": _safe_iso(row.event_timestamp),
            "lot_code": kde_map.get("lotNumber", ""),
            "tlc": row.traceability_lot_code,
            "product_id": kde_map.get("product_id"),
            "location_id": row.location_gln,
            "source_location_id": kde_map.get("ship_from_gln"),
            "dest_location_id": kde_map.get("ship_to_gln"),
            "quantity": row.quantity,
            "unit_of_measure": row.unit_of_measure,
            "data_source": row.source,
            "validation_status": "valid",
        }

        alerts = _query_alert_rows(db_session, tenant_id, row.id)
        return {
            "id": row.id,
            "ingested_at": _safe_iso(row.ingested_at),
            "idempotency_key": row.idempotency_key,
            "epcis_document": _parse_epcis_document(kde_map, normalized),
            "normalized_cte": normalized,
            "kdes": kdes,
            "alerts": alerts,
            "kde_completeness": _kde_completeness(kdes),
        }
    finally:
        db_session.close()


def _list_events_from_db(
    tenant_id: str,
    start_date: Optional[str],
    end_date: Optional[str],
    product_id: Optional[str],
) -> list[dict]:
    db_session = _get_db_session()
    try:
        where = ["tenant_id = :tenant_id"]
        params: dict[str, Any] = {"tenant_id": tenant_id}

        if start_date:
            where.append("event_timestamp >= :start_date")
            params["start_date"] = start_date
        if end_date:
            where.append("event_timestamp < :end_date")
            params["end_date"] = end_date

        rows = db_session.execute(
            text(
                f"""
                SELECT
                    id::text AS id,
                    event_type,
                    epcis_event_type,
                    epcis_action,
                    epcis_biz_step,
                    event_timestamp,
                    traceability_lot_code,
                    source,
                    location_gln,
                    quantity,
                    unit_of_measure
                FROM fsma.cte_events
                WHERE {' AND '.join(where)}
                ORDER BY event_timestamp DESC
                LIMIT 2000
                """
            ),
            params,
        ).fetchall()

        events: list[dict] = []
        for row in rows:
            kde_rows = db_session.execute(
                text(
                    """
                    SELECT kde_key, kde_value
                    FROM fsma.cte_kdes
                    WHERE tenant_id = :tenant_id
                      AND cte_event_id = :event_id
                    """
                ),
                {"tenant_id": tenant_id, "event_id": row.id},
            ).fetchall()
            kde_map = {kde.kde_key: kde.kde_value for kde in kde_rows}

            normalized = {
                "event_type": row.event_type,
                "epcis_event_type": row.epcis_event_type,
                "epcis_action": row.epcis_action,
                "epcis_biz_step": row.epcis_biz_step,
                "event_time": _safe_iso(row.event_timestamp),
                "lot_code": kde_map.get("lotNumber", ""),
                "tlc": row.traceability_lot_code,
                "product_id": kde_map.get("product_id"),
                "location_id": row.location_gln,
                "source_location_id": kde_map.get("ship_from_gln"),
                "dest_location_id": kde_map.get("ship_to_gln"),
                "quantity": row.quantity,
                "unit_of_measure": row.unit_of_measure,
                "data_source": row.source,
                "validation_status": "valid",
            }

            if product_id and normalized.get("product_id") != product_id:
                continue

            events.append(_parse_epcis_document(kde_map, normalized))

        return events
    finally:
        db_session.close()


def _ingest_single_event_fallback(event: dict) -> tuple[dict, int]:
    errors = _validate_epcis(event)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    idempotency_key = _event_idempotency_key(event)
    existing_event_id = _epcis_idempotency_index.get(idempotency_key)
    if existing_event_id:
        existing_record = _epcis_store[existing_event_id]
        return (
            {
                "status": 200,
                "cte_id": existing_event_id,
                "validation_status": existing_record["normalized_cte"]["validation_status"],
                "kde_completeness": existing_record.get("kde_completeness", 1.0),
                "alerts": existing_record["alerts"],
                "idempotent": True,
            },
            200,
        )

    event_id = str(uuid4())
    normalized = _normalize_epcis_to_cte(event)
    kdes = _extract_kdes(event)
    alerts = _compliance_alerts(normalized, kdes)
    alerts.extend(_validate_epcis_glns(normalized))

    # Validate against FSMAEvent Pydantic model before storing
    fsma_validated = _validate_as_fsma_event(normalized)
    if fsma_validated:
        normalized["fsma_validation_status"] = "passed"
    else:
        normalized["fsma_validation_status"] = "failed"
        alerts.append({
            "severity": "warning",
            "alert_type": "fsma_validation",
            "message": "Event did not pass FSMAEvent schema validation",
        })

    stored = {
        "id": event_id,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": idempotency_key,
        "epcis_document": event,
        "normalized_cte": normalized,
        "kdes": kdes,
        "alerts": alerts,
        "kde_completeness": _kde_completeness(kdes),
    }
    _epcis_store[event_id] = stored
    _epcis_idempotency_index[idempotency_key] = event_id

    return (
        {
            "status": 201,
            "cte_id": event_id,
            "validation_status": "warning" if alerts else "valid",
            "kde_completeness": stored["kde_completeness"],
            "alerts": alerts,
            "idempotent": False,
        },
        201,
    )


def _ingest_single_event_db(tenant_id: str, event: dict) -> tuple[dict, int]:
    from shared.cte_persistence import CTEPersistence

    errors = _validate_epcis(event)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    idempotency_key = _event_idempotency_key(event)
    normalized = _normalize_epcis_to_cte(event)
    kdes = _extract_kdes(event)
    alerts = _compliance_alerts(normalized, kdes)
    alerts.extend(_validate_epcis_glns(normalized))
    kde_map = _build_kde_map(event, normalized, idempotency_key)

    # Validate against FSMAEvent Pydantic model before DB persistence
    fsma_validated = _validate_as_fsma_event(normalized, tenant_id)
    if fsma_validated:
        kde_map["fsma_validation_status"] = "passed"
    else:
        kde_map["fsma_validation_status"] = "failed"
        alerts.append({
            "severity": "warning",
            "alert_type": "fsma_validation",
            "message": "Event did not pass FSMAEvent schema validation",
        })

    event_time = normalized.get("event_time") or datetime.now(timezone.utc).isoformat()
    quantity = normalized.get("quantity")
    try:
        quantity_value = float(quantity) if quantity is not None else 1.0
    except (TypeError, ValueError):
        quantity_value = 1.0
    if quantity_value <= 0:
        quantity_value = 1.0

    db_session = _get_db_session()
    try:
        persistence = CTEPersistence(db_session)
        result = persistence.store_event(
            tenant_id=tenant_id,
            event_type=normalized["event_type"],
            traceability_lot_code=normalized["tlc"],
            product_description=_default_product_description(normalized),
            quantity=quantity_value,
            unit_of_measure=normalized.get("unit_of_measure") or "units",
            event_timestamp=event_time,
            source="epcis",
            source_event_id=str(event.get("eventID") or idempotency_key),
            location_gln=normalized.get("location_id"),
            location_name=None,
            kdes=kde_map,
            alerts=alerts,
            epcis_event_type=normalized.get("epcis_event_type"),
            epcis_action=normalized.get("epcis_action"),
            epcis_biz_step=normalized.get("epcis_biz_step"),
        )
        db_session.commit()

        # Canonical normalization — write to traceability_events + evaluate rules
        if not result.idempotent:
            try:
                from shared.canonical_event import normalize_epcis_event
                from shared.canonical_persistence import CanonicalEventStore
                canonical = normalize_epcis_event(event, tenant_id)
                canonical_store = CanonicalEventStore(db_session, dual_write=False)
                canonical_store.persist_event(canonical)
                # Auto-evaluate rules
                from shared.rules_engine import RulesEngine
                engine = RulesEngine(db_session)
                event_data = {
                    "event_id": str(canonical.event_id),
                    "event_type": canonical.event_type.value,
                    "traceability_lot_code": canonical.traceability_lot_code,
                    "product_reference": canonical.product_reference,
                    "quantity": canonical.quantity,
                    "unit_of_measure": canonical.unit_of_measure,
                    "from_facility_reference": canonical.from_facility_reference,
                    "to_facility_reference": canonical.to_facility_reference,
                    "from_entity_reference": canonical.from_entity_reference,
                    "to_entity_reference": canonical.to_entity_reference,
                    "kdes": canonical.kdes,
                }
                engine.evaluate_event(event_data, persist=True, tenant_id=tenant_id)
                db_session.commit()
            except Exception as canon_err:
                logger.warning("epcis_canonical_write_skipped: %s", str(canon_err))

    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.close()

    status_code = 200 if result.idempotent else 201
    return (
        {
            "status": status_code,
            "cte_id": result.event_id,
            "validation_status": "warning" if alerts else "valid",
            "kde_completeness": _kde_completeness(kdes),
            "alerts": alerts,
            "idempotent": result.idempotent,
        },
        status_code,
    )


def _ingest_single_event(tenant_id: str, event: dict) -> tuple[dict, int]:
    try:
        return _ingest_single_event_db(tenant_id, event)
    except Exception as exc:
        if not _allow_in_memory_fallback():
            logger.error("epcis_db_persistence_failed_no_fallback error=%s", str(exc))
            raise HTTPException(
                status_code=503,
                detail="Database unavailable — EPCIS ingest cannot proceed.",
            ) from exc

        logger.warning("epcis_db_persistence_failed_using_fallback error=%s", str(exc))
        return _ingest_single_event_fallback(event)


class BatchIngestRequest(BaseModel):
    events: list[dict] = Field(default_factory=list)


@router.post("/events", status_code=201, summary="Ingest EPCIS 2.0 event")
async def ingest_epcis_event(
    event: dict,
    tenant_id: Optional[str] = Query(default=None, description="Optional tenant override"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
    _: None = Depends(_verify_api_key),
):
    resolved_tenant = _resolve_tenant_id(tenant_id, x_tenant_id, x_regengine_api_key)
    if not resolved_tenant:
        raise HTTPException(status_code=400, detail="Tenant context required")

    payload, status_code = _ingest_single_event(resolved_tenant, event)
    return JSONResponse(content=payload, status_code=status_code)


@router.post("/events/batch", summary="Batch ingest EPCIS events")
async def ingest_epcis_batch(
    request: BatchIngestRequest,
    tenant_id: Optional[str] = Query(default=None, description="Optional tenant override"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
    _: None = Depends(_verify_api_key),
):
    if not request.events:
        raise HTTPException(status_code=400, detail="Batch ingest requires at least one event")

    resolved_tenant = _resolve_tenant_id(tenant_id, x_tenant_id, x_regengine_api_key)
    if not resolved_tenant:
        raise HTTPException(status_code=400, detail="Tenant context required")

    created: list[dict] = []
    failed: list[dict] = []
    processed: list[dict] = []

    for idx, event in enumerate(request.events):
        try:
            payload, status_code = _ingest_single_event(resolved_tenant, event)
            processed.append({"index": idx, "status_code": status_code, **payload})
            if status_code == 201:
                created.append(payload)
        except HTTPException as exc:
            failed.append({"index": idx, "detail": exc.detail})

    response_payload = {
        "total": len(request.events),
        "created": len(created),
        "failed": len(failed),
        "results": processed,
        "errors": failed,
    }

    successful = len(processed)
    if failed and successful:
        return JSONResponse(content=response_payload, status_code=207)
    if failed and not successful:
        return JSONResponse(content=response_payload, status_code=400)
    return JSONResponse(content=response_payload, status_code=201)


@router.get("/events/{event_id}", summary="Get EPCIS event by id")
async def get_epcis_event(
    event_id: str,
    tenant_id: Optional[str] = Query(default=None, description="Optional tenant override"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
    _: None = Depends(_verify_api_key),
):
    resolved_tenant = _resolve_tenant_id(tenant_id, x_tenant_id, x_regengine_api_key)
    if not resolved_tenant:
        raise HTTPException(status_code=400, detail="Tenant context required")

    event = None
    try:
        event = _fetch_event_from_db(resolved_tenant, event_id)
    except Exception as exc:
        if not _allow_in_memory_fallback():
            raise HTTPException(status_code=503, detail="Database unavailable") from exc
        logger.warning("epcis_get_db_failed_using_fallback error=%s", str(exc))

    if event is None and _allow_in_memory_fallback():
        event = _epcis_store.get(event_id)

    if not event:
        raise HTTPException(status_code=404, detail=f"EPCIS event '{event_id}' not found")
    return event


@router.get("/export", summary="Export all ingested events as EPCIS 2.0")
async def export_epcis_events(
    start_date: str | None = Query(default=None, description="Filter events at or after this ISO timestamp"),
    end_date: str | None = Query(default=None, description="Filter events before this ISO timestamp"),
    product_id: str | None = Query(default=None, description="Filter by EPC product identifier"),
    tenant_id: Optional[str] = Query(default=None, description="Optional tenant override"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
    _: None = Depends(_verify_api_key),
):
    resolved_tenant = _resolve_tenant_id(tenant_id, x_tenant_id, x_regengine_api_key)
    if not resolved_tenant:
        raise HTTPException(status_code=400, detail="Tenant context required")

    events: list[dict] = []
    try:
        events = _list_events_from_db(resolved_tenant, start_date, end_date, product_id)
    except Exception as exc:
        if not _allow_in_memory_fallback():
            raise HTTPException(status_code=503, detail="Database unavailable") from exc
        logger.warning("epcis_export_db_failed_using_fallback error=%s", str(exc))

    if not events and _allow_in_memory_fallback():
        def _parse_iso(value: str | None) -> datetime | None:
            if not value:
                return None
            parsed = value.replace("Z", "+00:00")
            return datetime.fromisoformat(parsed)

        start_dt = _parse_iso(start_date)
        end_dt = _parse_iso(end_date)

        filtered_records: list[dict] = []
        for entry in _epcis_store.values():
            normalized = entry.get("normalized_cte", {})
            event_time = normalized.get("event_time")
            if event_time:
                event_dt = _parse_iso(str(event_time))
                if start_dt and event_dt and event_dt < start_dt:
                    continue
                if end_dt and event_dt and event_dt >= end_dt:
                    continue
            if product_id and normalized.get("product_id") != product_id:
                continue
            filtered_records.append(entry)
        events = [entry["epcis_document"] for entry in filtered_records]

    return {
        "@context": ["https://ref.gs1.org/standards/epcis/2.0.0/epcis-context.jsonld"],
        "type": "EPCISDocument",
        "schemaVersion": "2.0",
        "creationDate": datetime.now(timezone.utc).isoformat(),
        "epcisBody": {"eventList": events},
        "metadata": {
            "source": "regengine-epcis-ingestion",
            "event_count": len(events),
            "filters": {
                "start_date": start_date,
                "end_date": end_date,
                "product_id": product_id,
            },
        },
    }


@router.post("/validate", summary="Validate EPCIS event payload")
async def validate_epcis_event(
    event: dict,
    _: None = Depends(_verify_api_key),
):
    errors = _validate_epcis(event)
    normalized = _normalize_epcis_to_cte(event) if not errors else None
    return {
        "valid": not errors,
        "errors": errors,
        "normalized_cte": normalized,
    }


@router.post("/events/xml", status_code=201, summary="Ingest EPCIS 2.0 XML document")
async def ingest_epcis_xml(
    request: Request,
    tenant_id: Optional[str] = Query(default=None, description="Optional tenant override"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
    _: None = Depends(_verify_api_key),
):
    """Ingest an EPCIS 2.0 XML document containing one or more events.

    Parses the XML, extracts ObjectEvent, AggregationEvent, TransactionEvent,
    and TransformationEvent elements, then ingests each through the standard
    EPCIS pipeline with FSMAEvent validation.
    """
    resolved_tenant = _resolve_tenant_id(tenant_id, x_tenant_id, x_regengine_api_key)
    if not resolved_tenant:
        raise HTTPException(status_code=400, detail="Tenant context required")

    raw_body = await request.body()
    if not raw_body:
        raise HTTPException(status_code=400, detail="Empty XML payload")

    if not _is_xml_content(raw_body):
        raise HTTPException(status_code=400, detail="Payload does not appear to be XML")

    events = _parse_epcis_xml(raw_body)
    if not events:
        raise HTTPException(
            status_code=422,
            detail="No EPCIS events found in XML document",
        )

    created: list[dict] = []
    failed: list[dict] = []
    processed: list[dict] = []

    for idx, event in enumerate(events):
        try:
            payload, status_code = _ingest_single_event(resolved_tenant, event)
            processed.append({"index": idx, "status_code": status_code, **payload})
            if status_code == 201:
                created.append(payload)
        except HTTPException as exc:
            failed.append({"index": idx, "detail": exc.detail})

    response_payload = {
        "total": len(events),
        "created": len(created),
        "failed": len(failed),
        "results": processed,
        "errors": failed,
        "format": "EPCIS_XML_2.0",
    }

    successful = len(processed)
    if failed and successful:
        return JSONResponse(content=response_payload, status_code=207)
    if failed and not successful:
        return JSONResponse(content=response_payload, status_code=400)
    return JSONResponse(content=response_payload, status_code=201)
