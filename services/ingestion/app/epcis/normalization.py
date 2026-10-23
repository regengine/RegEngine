"""EPCIS event normalization and CTE mapping.

Converts raw EPCIS events into the canonical CTE (Critical Tracking Event)
format, computes idempotency keys, extracts KDEs, and generates compliance
alerts.
"""

from __future__ import annotations

import json
import logging
import re
from hashlib import sha256
from typing import Any

from fastapi import HTTPException

from .extraction import (
    _extract_event_lot,
    _extract_location_id,
    _extract_party_id,
    _lot_from_identifier,
)

logger = logging.getLogger("epcis-ingestion")


# FSMA 204 CTE mapping — bizStep URI → canonical CTE event_type (#1153).
# Covers CBV 2.0 bizSteps and FSMA-specific URIs. Unmapped values are
# rejected in `_normalize_epcis_to_cte` rather than silently defaulted to
# "receiving", which previously misclassified `growing` and unrelated
# bizSteps as inbound receipts and corrupted recall lookback graphs.
_EVENT_TYPE_MAP: dict[str, str] = {
    # CBV bizSteps used by FSMA-participating partners
    "urn:epcglobal:cbv:bizstep:receiving": "receiving",
    "urn:epcglobal:cbv:bizstep:shipping": "shipping",
    "urn:epcglobal:cbv:bizstep:transforming": "transformation",
    "urn:epcglobal:cbv:bizstep:commissioning": "initial_packing",
    "urn:epcglobal:cbv:bizstep:packing": "initial_packing",
    "urn:epcglobal:cbv:bizstep:harvesting": "harvesting",
    "urn:epcglobal:cbv:bizstep:planting": "growing",
    "urn:epcglobal:cbv:bizstep:storing": "cooling",
    "urn:epcglobal:cbv:bizstep:landing": "first_land_based_receiving",
    # FSMA 204 explicit CTE URIs
    "urn:fsma:traceability:growing": "growing",
    "urn:fsma:traceability:harvesting": "harvesting",
    "urn:fsma:traceability:cooling": "cooling",
    "urn:fsma:traceability:initial_packing": "initial_packing",
    "urn:fsma:traceability:first_land_based_receiving": "first_land_based_receiving",
    "urn:fsma:traceability:shipping": "shipping",
    "urn:fsma:traceability:receiving": "receiving",
    "urn:fsma:traceability:transformation": "transformation",
}


_CBV_BIZSTEP_PREFIX = "urn:epcglobal:cbv:bizstep:"
# CBV 2.0 bare names are a single token (underscores, no spaces).
_BARE_BIZSTEP_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _canonical_bizstep(value: object) -> str:
    """Map a bizStep to the ``urn:epcglobal:cbv:bizstep:<name>`` lookup key.

    EPCIS 2.0 JSON-LD leaves CBV names unexpanded (``receiving``). The GS1
    Web vocabulary writes ``https://ref.gs1.org/cbv/BizStep-receiving``.
    Both are the same CBV bizStep as the URN. FSMA URIs and anything else
    are returned unchanged so an unknown value still fails the lookup.
    """
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if lowered.startswith(_CBV_BIZSTEP_PREFIX):
        return _CBV_BIZSTEP_PREFIX + lowered[len(_CBV_BIZSTEP_PREFIX) :]
    if lowered.startswith("urn:"):
        return raw
    for scheme in ("https://", "http://"):
        marker = f"{scheme}ref.gs1.org/cbv/bizstep-"
        if lowered.startswith(marker):
            name = lowered[len(marker) :].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
            if name:
                return _CBV_BIZSTEP_PREFIX + name
            return raw
    if _BARE_BIZSTEP_RE.fullmatch(raw):
        return _CBV_BIZSTEP_PREFIX + lowered
    return raw


def _event_idempotency_key(event: dict) -> str:
    explicit = event.get("eventID")
    if explicit:
        return str(explicit)
    normalized = json.dumps(event, sort_keys=True, separators=(",", ":"))
    return sha256(normalized.encode("utf-8")).hexdigest()


def _quantity_list(event: dict) -> list:
    """First populated quantity list, in the same order as the canonical writer.

    ``extension.quantityList`` is the EPCIS 1.x wrapper. The 2.0 member is
    top-level ``quantityList``. An AggregationEvent puts the same elements
    on ``childQuantityList`` and has no ``quantityList``. A
    TransformationEvent has neither; its quantity is the output list, with
    the input list only when the output list is absent (#2970).

    The first *truthy* candidate wins, including a wrong-shaped value, so
    a non-list does not silently fall through to a later list.
    """
    extension = event.get("extension")
    extension_list = extension.get("quantityList") if isinstance(extension, dict) else None
    for candidate in (
        extension_list,
        event.get("quantityList"),
        event.get("childQuantityList"),
        event.get("outputQuantityList"),
        event.get("inputQuantityList"),
    ):
        if candidate:
            return candidate if isinstance(candidate, list) else []
    return []


def _quantity_element(event: dict) -> dict | None:
    """Quantity element for the CTE.

    When the list contains a lot-level class (LGTIN or Digital Link), use
    that element's quantity: it is the quantity of the lot being traced.
    A leading serialized class (an SGTIN pattern with a count and no unit)
    is a different identifier and is not the lot quantity. Otherwise the
    first element, matching the historical ``quantityList[0]`` rule.
    """
    quantity_list = _quantity_list(event)
    if not quantity_list or not isinstance(quantity_list[0], dict):
        return None
    for element in quantity_list:
        if isinstance(element, dict) and _lot_from_identifier(element.get("epcClass")):
            return element
    return quantity_list[0]


def _normalize_epcis_to_cte(event: dict) -> dict:
    lot_code, tlc = _extract_event_lot(event)
    epc_list = event.get("epcList", [])
    product_id = epc_list[0] if isinstance(epc_list, list) and epc_list else None
    received_biz_step = event.get("bizStep")
    biz_step = _canonical_bizstep(received_biz_step)

    event_type = _EVENT_TYPE_MAP.get(biz_step)
    if event_type is None:
        logger.warning("unmapped_epcis_bizstep uri=%s", received_biz_step)
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unmapped_bizstep",
                "bizStep": "" if received_biz_step is None else received_biz_step,
                "message": (
                    "bizStep has no FSMA 204 CTE mapping. Supply a CBV or "
                    "FSMA URI for one of: growing, harvesting, cooling, "
                    "initial_packing, first_land_based_receiving, "
                    "transformation, shipping, receiving."
                ),
                "allowed_bizsteps": sorted(_EVENT_TYPE_MAP.keys()),
            },
        )

    quantity = None
    unit = None
    element = _quantity_element(event)
    if element is not None:
        quantity = element.get("quantity")
        unit = element.get("uom")

    return {
        "event_type": event_type,
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
