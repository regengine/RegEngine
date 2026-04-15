"""EPCIS field extraction utilities.

Extracts lot data, location identifiers, and party identifiers from
EPCIS event payloads.
"""

from __future__ import annotations


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
