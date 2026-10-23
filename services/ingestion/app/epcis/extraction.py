"""EPCIS field extraction utilities.

Extracts lot data, location identifiers, and party identifiers from
EPCIS event payloads.
"""

from __future__ import annotations

import re
from urllib.parse import unquote

# EPCIS 1.x class-level lot id. The lot is everything after the second dot;
# GS1 percent-encodes reserved characters inside it.
_LGTIN_RE = re.compile(r"^urn:epc:class:lgtin:\d+\.\d+\.(.+)$", re.IGNORECASE)


def _present_ilmd_text(value: object) -> str | None:
    """String form of an ILMD value, or None when the field is blank.

    ``None`` and ``""`` fall through so a namespaced key can lose to the
    bare key. Other values are stringified and not stripped: a numeric
    lot (``42``) and a whitespace lot stay distinguishable from missing.
    """
    if value is None or value == "":
        return None
    return str(value)


def _lookup_ilmd(ilmd: dict, preferred: tuple[str, ...], local_name: str) -> str:
    """Read one ILMD field, preferring the keys the JSON-LD path writes.

    The XML parser emits ``cbvmda:lotNumber`` when it recognises the CBV
    master-data namespace, and plain ``lotNumber`` when it does not. Any
    other prefix with the same local name is accepted so a document is
    not rejected for a prefix the parser happened to keep.
    """
    for key in preferred:
        if key not in ilmd:
            continue
        text = _present_ilmd_text(ilmd[key])
        if text is not None:
            return text
    for key, value in ilmd.items():
        if not isinstance(key, str) or key in preferred:
            continue
        if key.split(":")[-1] != local_name:
            continue
        text = _present_ilmd_text(value)
        if text is not None:
            return text
    return ""


def _extract_lot_data(ilmd: dict | None) -> tuple[str, str]:
    if not ilmd:
        return "", ""
    lot_code = _lookup_ilmd(ilmd, ("cbvmda:lotNumber", "lotNumber"), "lotNumber")
    tlc = _lookup_ilmd(ilmd, ("fsma:traceabilityLotCode", "traceabilityLotCode"), "traceabilityLotCode")
    if not tlc:
        tlc = lot_code
    return lot_code, tlc


def _lot_from_identifier(value: object) -> tuple[str, str] | None:
    """``(lot_code, tlc)`` when ``value`` is a lot-level GS1 identifier.

    ``tlc`` is the identifier string itself (the full LGTIN URI, or the
    full Digital Link URI). ``lot_code`` is only the lot component.
    Serialized SGTINs and EPC patterns are not lot-level ids: a serial
    does not identify the lot FSMA 204 traces.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    lgtin = _LGTIN_RE.match(text)
    if lgtin:
        lot = unquote(lgtin.group(1))
        if lot:
            return lot, text
        return None
    return _lot_from_digital_link(text)


def _lot_from_digital_link(text: str) -> tuple[str, str] | None:
    """GS1 Digital Link ``/01/<gtin>/10/<lot>`` with no serial AI (21).

    A ``/21/`` component identifies one item, not the lot. The lot
    component is percent-decoded; ``tlc`` stays the original string.
    """
    path = text.split("?", 1)[0].split("#", 1)[0]
    segments = [segment for segment in path.split("/") if segment]
    try:
        gtin_at = segments.index("01")
    except ValueError:
        return None
    if gtin_at + 3 >= len(segments):
        return None
    gtin = segments[gtin_at + 1]
    if not gtin.isdigit() or not 8 <= len(gtin) <= 14:
        return None
    # The standard path is /01/<gtin>/10/<lot>, not an AI pair with
    # something between the GTIN and the lot.
    if segments[gtin_at + 2] != "10":
        return None
    if "21" in segments[gtin_at + 2 :]:
        return None
    lot = unquote(segments[gtin_at + 3]).strip()
    if not lot:
        return None
    return lot, text


def _identifier_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    found: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            found.append(item.strip())
        elif isinstance(item, dict):
            epc_class = item.get("epcClass")
            if isinstance(epc_class, str) and epc_class.strip():
                found.append(epc_class.strip())
    return found


def _lot_level_identifiers(event: dict) -> list[str]:
    """Identifiers that may carry the lot, output-only for a transformation.

    A TransformationEvent's inputs are the ingredients. The FSMA TLC
    belongs to the output lot, so input EPC and quantity lists are ignored.
    """
    if event.get("type") == "TransformationEvent":
        return _identifier_strings(event.get("outputQuantityList")) + _identifier_strings(event.get("outputEPCList"))
    extension = event.get("extension")
    extension_quantities = extension.get("quantityList") if isinstance(extension, dict) else None
    return (
        _identifier_strings(extension_quantities)
        + _identifier_strings(event.get("quantityList"))
        + _identifier_strings(event.get("childQuantityList"))
        + _identifier_strings(event.get("outputQuantityList"))
        + _identifier_strings(event.get("epcList"))
        + _identifier_strings(event.get("childEPCs"))
        + _identifier_strings(event.get("outputEPCList"))
    )


def _ilmd_dict(event: dict) -> dict | None:
    """ILMD dict, top-level first, then ``extension.ilmd``.

    An empty dict is falsy, matching the previous ``ilmd or extension``
    fallback: a blank top-level ``ilmd`` must not hide a populated
    extension block.
    """
    ilmd = event.get("ilmd")
    if isinstance(ilmd, dict) and ilmd:
        return ilmd
    extension = event.get("extension")
    if isinstance(extension, dict):
        nested = extension.get("ilmd")
        if isinstance(nested, dict) and nested:
            return nested
    if isinstance(ilmd, dict):
        return ilmd
    return None


def _extract_event_lot(event: dict) -> tuple[str, str]:
    """ILMD lot/TLC, otherwise the first lot-level GS1 identifier.

    ILMD ``fsma:traceabilityLotCode`` / ``lotNumber`` wins. When neither
    is present, an LGTIN class or a Digital Link ``/01/<gtin>/10/<lot>``
    supplies ``lot_code`` and the full identifier string as ``tlc``.
    """
    lot_code, tlc = _extract_lot_data(_ilmd_dict(event))
    if tlc or lot_code:
        return lot_code, tlc
    for identifier in _lot_level_identifiers(event):
        parsed = _lot_from_identifier(identifier)
        if parsed:
            return parsed
    return "", ""


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
