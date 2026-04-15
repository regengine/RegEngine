"""EPCIS event normalization and CTE mapping.

Converts raw EPCIS events into the canonical CTE (Critical Tracking Event)
format, computes idempotency keys, extracts KDEs, and generates compliance
alerts.
"""

from __future__ import annotations

import json
import logging
from hashlib import sha256
from typing import Any

from services.ingestion.app.epcis.extraction import (
    _extract_location_id,
    _extract_lot_data,
    _extract_party_id,
)

logger = logging.getLogger("epcis-ingestion")


def _event_idempotency_key(event: dict) -> str:
    explicit = event.get("eventID")
    if explicit:
        return str(explicit)
    normalized = json.dumps(event, sort_keys=True, separators=(",", ":"))
    return sha256(normalized.encode("utf-8")).hexdigest()


def _fallback_event_type(biz_step: str) -> str:
    """Log a warning for unmapped bizStep URIs and default to 'receiving'."""
    if biz_step:
        logger.warning("unmapped_epcis_bizstep uri=%s — defaulting to 'receiving'", biz_step)
    return "receiving"


def _normalize_epcis_to_cte(event: dict) -> dict:
    event_type_map = {
        "urn:epcglobal:cbv:bizstep:receiving": "receiving",
        "urn:epcglobal:cbv:bizstep:shipping": "shipping",
        "urn:epcglobal:cbv:bizstep:transforming": "transformation",
        "urn:epcglobal:cbv:bizstep:commissioning": "initial_packing",
        "urn:epcglobal:cbv:bizstep:packing": "initial_packing",
        "urn:epcglobal:cbv:bizstep:harvesting": "harvesting",
        "urn:epcglobal:cbv:bizstep:storing": "cooling",
        "urn:epcglobal:cbv:bizstep:landing": "first_land_based_receiving",
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
        "event_type": event_type_map.get(biz_step) or _fallback_event_type(biz_step),
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
