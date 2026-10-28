"""SEL-598 lossless EPCIS lot identity (Preview).

Canonical stored identity is the full LGTIN URN or GS1 Digital Link
(``/01/<gtin>/10/<lot>``). The bare lot token is derived for UI, gap
reports, and Digital Link rebuild. Legacy extraction and canonical
ingest must agree.

Feature flag: ``LOT_IDENTITY_LOSSLESS=0`` restores segment-only writes
on the canonical path (rollback only; default is on).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional
from urllib.parse import quote, unquote

_LGTIN_RE = re.compile(
    r"^urn:epc:class:lgtin:(\d{6,12})\.(\d+)\.([A-Za-z0-9_~!$&'()*+,;=:@%\-]+)$",
    re.IGNORECASE,
)
_DL_RE = re.compile(
    r"^https://id\.gs1\.org/01/(\d{14})/10/([^/?#]+)$",
    re.IGNORECASE,
)


def lossless_enabled() -> bool:
    return os.environ.get("LOT_IDENTITY_LOSSLESS", "1") != "0"


@dataclass(frozen=True)
class LotIdentity:
    """One lot identity after normalization.

    ``canonical_id`` is the full class URI / Digital Link when known,
    otherwise the raw TLC string (never invent a URI).
    ``lot_token`` is always the bare lot segment for rebuild and UI.
    ``gtin`` is the 14-digit GTIN when present or derivable.
    """

    canonical_id: str
    lot_token: str
    gtin: Optional[str] = None
    source: str = "unknown"


def parse_class_uri(value: object) -> Optional[LotIdentity]:
    """Parse an LGTIN URN or GS1 Digital Link into a LotIdentity."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    m = _LGTIN_RE.fullmatch(text)
    if m:
        company, item, lot_enc = m.group(1), m.group(2), m.group(3)
        if len(company) + len(item) != 13:
            return None
        lot = unquote(lot_enc)
        # Company+item are 13 digits; GTIN-14 needs indicator digit. Prefer
        # rebuilding via Digital Link only when we already have 14 digits
        # elsewhere; keep the LGTIN string as canonical.
        return LotIdentity(canonical_id=text, lot_token=lot, gtin=None, source="lgtin")
    m = _DL_RE.fullmatch(text)
    if m:
        gtin, lot_enc = m.group(1), m.group(2)
        lot = unquote(lot_enc)
        return LotIdentity(canonical_id=text, lot_token=lot, gtin=gtin, source="digital_link")
    return None


def derive_lot_token(value: object) -> Optional[str]:
    """Bare lot segment: from a class URI if present, else the raw string."""
    parsed = parse_class_uri(value)
    if parsed:
        return parsed.lot_token
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def identity_from_parts(
    *,
    class_uri: object = None,
    tlc: object = None,
    gtin: object = None,
) -> Optional[LotIdentity]:
    """Build identity preferring a full class URI, else TLC + optional GTIN."""
    parsed = parse_class_uri(class_uri)
    if parsed:
        gtin_s = parsed.gtin
        if not gtin_s and isinstance(gtin, str) and gtin.strip():
            digits = re.sub(r"\D", "", gtin.strip())
            gtin_s = digits if len(digits) == 14 else parsed.gtin
            if gtin_s and not parsed.gtin:
                return LotIdentity(
                    canonical_id=parsed.canonical_id,
                    lot_token=parsed.lot_token,
                    gtin=gtin_s,
                    source=parsed.source,
                )
        return parsed

    # TLC itself may be a full URI (legacy lossless path).
    parsed = parse_class_uri(tlc)
    if parsed:
        if parsed.gtin is None and isinstance(gtin, str) and gtin.strip():
            digits = re.sub(r"\D", "", gtin.strip())
            if len(digits) == 14:
                return LotIdentity(
                    canonical_id=parsed.canonical_id,
                    lot_token=parsed.lot_token,
                    gtin=digits,
                    source=parsed.source,
                )
        return parsed

    token = derive_lot_token(tlc)
    if not token:
        return None
    gtin_s: Optional[str] = None
    if isinstance(gtin, str) and gtin.strip():
        digits = re.sub(r"\D", "", gtin.strip())
        if digits:
            gtin_s = digits
    # When we have GTIN+token, Digital Link is the preferred canonical form.
    if gtin_s and len(gtin_s) == 14:
        dl = f"https://id.gs1.org/01/{gtin_s}/10/{quote(token, safe='-._~')}"
        return LotIdentity(canonical_id=dl, lot_token=token, gtin=gtin_s, source="gtin_tlc")
    return LotIdentity(canonical_id=token, lot_token=token, gtin=gtin_s, source="bare_tlc")


def normalize_from_epcis_event(epcis_data: Mapping[str, Any]) -> LotIdentity:
    """Resolve lot identity from an EPCIS event dict (ILMD, then class URIs).

    Precedence matches legacy ``epcis/extraction`` and the canonical
    ``_epcis_traceability_lot_code`` order: ILMD TLC / lotNumber, then
    LGTIN among EPCs or quantity classes, then SGTIN serial (as last
    resort token only), then flattened top-level keys.

    When ILMD carries a bare TLC and a matching class URI / Digital Link
    is on the same event, the full URI is the canonical id (SEL-598).
    """
    ilmd = epcis_data.get("ilmd")
    if not isinstance(ilmd, dict):
        ilmd = {}

    def _list(key: str) -> list:
        value = epcis_data.get(key)
        return list(value) if isinstance(value, list) else []

    epcs = _list("epcList") + _list("outputEPCList")
    extension = epcis_data.get("extension")
    extension = extension if isinstance(extension, dict) else {}
    classes: list[Any] = []
    for q in (
        _list("outputQuantityList")
        + _list("quantityList")
        + (list(extension.get("quantityList") or []) if isinstance(extension.get("quantityList"), list) else [])
    ):
        if isinstance(q, dict) and q.get("epcClass"):
            classes.append(q.get("epcClass"))

    class_idents: list[LotIdentity] = []
    for candidate in epcs + classes:
        parsed = parse_class_uri(candidate)
        if parsed:
            class_idents.append(parsed)

    gtin_hint: Optional[str] = next((c.gtin for c in class_idents if c.gtin), None)

    def _prefer_class_uri(ident: LotIdentity) -> LotIdentity:
        if parse_class_uri(ident.canonical_id):
            return ident
        for other in class_idents:
            if other.lot_token == ident.lot_token:
                gtin = other.gtin or ident.gtin or gtin_hint
                return LotIdentity(
                    canonical_id=other.canonical_id,
                    lot_token=other.lot_token,
                    gtin=gtin,
                    source=other.source,
                )
        if not lossless_enabled():
            return LotIdentity(
                canonical_id=ident.lot_token,
                lot_token=ident.lot_token,
                gtin=ident.gtin or gtin_hint,
                source="bare_segment",
            )
        return ident

    for key in ("fsma:traceabilityLotCode", "traceabilityLotCode", "cbvmda:lotNumber", "lotNumber"):
        value = ilmd.get(key)
        if value is not None and str(value).strip():
            ident = identity_from_parts(tlc=str(value).strip(), gtin=gtin_hint)
            if ident:
                return _prefer_class_uri(ident)

    for parsed in class_idents:
        if not lossless_enabled():
            return LotIdentity(
                canonical_id=parsed.lot_token,
                lot_token=parsed.lot_token,
                gtin=parsed.gtin or gtin_hint,
                source="bare_segment",
            )
        return parsed

    # SGTIN serial is not a lot-level FSMA id; keep as last-resort token only
    # so existing canonical callers do not start fabricating UNKNOWN.
    for epc in epcs:
        text = str(epc or "")
        if "sgtin" in text.lower():
            parts = text.rsplit(".", 1)
            if len(parts) == 2 and parts[1]:
                return LotIdentity(
                    canonical_id=parts[1],
                    lot_token=parts[1],
                    gtin=gtin_hint,
                    source="sgtin_segment",
                )

    for key in ("traceability_lot_code", "lotNumber"):
        value = epcis_data.get(key)
        if value is not None and str(value).strip():
            ident = identity_from_parts(tlc=str(value).strip(), gtin=gtin_hint)
            if ident:
                return _prefer_class_uri(ident)

    raise ValueError(
        "EPCIS event carries no lot identifier (ILMD traceabilityLotCode or lotNumber, "
        "an LGTIN class URI or Digital Link, or traceability_lot_code); refusing to fabricate one"
    )


def epc_class_for_export(row: Mapping[str, Any]) -> Optional[str]:
    """Prefer a stored full class URI; else build from GTIN + derived lot token.

    Never pass a full URI as the ``{lot}`` argument to a Digital Link rebuild.
    """
    for key in ("epc_class", "product_id", "canonical_epc_class", "traceability_lot_code"):
        value = row.get(key)
        parsed = parse_class_uri(value)
        if parsed:
            return parsed.canonical_id

    gtin_raw = row.get("gtin") or row.get("product_id")
    tlc = row.get("traceability_lot_code")
    token = derive_lot_token(tlc)
    if token and parse_class_uri(token):
        # derive_lot_token returned something that is still a URI — use parse.
        return parse_class_uri(token).canonical_id  # type: ignore[union-attr]

    ident = identity_from_parts(tlc=token or tlc, gtin=gtin_raw)
    if ident and ident.source in {"digital_link", "gtin_tlc", "lgtin"}:
        return ident.canonical_id
    if ident and ident.gtin and len(ident.gtin) == 14 and ident.lot_token:
        return f"https://id.gs1.org/01/{ident.gtin}/10/{quote(ident.lot_token, safe='-._~')}"
    return None
