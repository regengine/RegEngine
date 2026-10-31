"""SEL-598 lossless EPCIS lot identity (H2).

Canonical stored identity is the full LGTIN or GS1 Digital Link (AI 01 + 10).
The bare lot token is derived for UI, gap reports, and export rebuild paths.
Round-trip acceptance is exact equality on the canonical full ID.

Feature flag: ``LOT_IDENTITY_LOSSLESS`` (default enabled). Set to ``0`` /
``false`` to restore segment-only canonical writes (rollback).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import unquote

_LGTIN_RE = re.compile(r"^urn:epc:class:lgtin:(\d+)\.(\d+)\.(.+)$", re.IGNORECASE)
_SGTIN_RE = re.compile(r"^urn:epc:id:sgtin:(\d+)\.(\d+)\.(.+)$", re.IGNORECASE)
_DL_CLASS_RE = re.compile(
    r"^https://id\.gs1\.org/01/(\d{8,14})/10/([^/?#]+)$",
    re.IGNORECASE,
)


def lossless_enabled() -> bool:
    raw = (os.environ.get("LOT_IDENTITY_LOSSLESS") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class LotIdentity:
    """Normalized lot identity for ingest, canonical store, and export."""

    canonical_id: str
    lot_token: str
    gtin: Optional[str]
    is_full_class_uri: bool


def _company_item_to_gtin14(company: str, item: str) -> Optional[str]:
    """Rebuild GTIN-14 from EPC Pure Identity company.item (SGTIN/LGTIN).

    Company prefix + item reference must sum to 13 digits. The first digit of
    the item reference is the Indicator; the remaining item digits follow the
    company prefix; then append the GS1 check digit.
    Example: ``0614141.123452`` → ``10614141234520`` (not ``00614141123452``).
    """
    if not company.isdigit() or not item.isdigit() or not item:
        return None
    if len(company) + len(item) != 13:
        return None
    indicator = item[0]
    item_without_indicator = item[1:]
    digits13 = indicator + company + item_without_indicator
    if len(digits13) != 13:
        return None
    return digits13 + _gs1_check_digit(digits13)


def _gs1_check_digit(digits13: str) -> str:
    total = 0
    for i, ch in enumerate(digits13):
        n = int(ch)
        total += n * (3 if (i % 2 == 0) else 1)
    return str((10 - (total % 10)) % 10)


def normalize_gtin14(raw: str) -> Optional[str]:
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return None
    if len(digits) < 8 or len(digits) > 14:
        return None
    digits = digits.zfill(14)
    body, check = digits[:-1], digits[-1]
    if _gs1_check_digit(body) != check:
        # Still return zero-padded digits for dual-read rebuild; caller may validate
        return digits
    return digits


def parse_class_uri(value: object) -> Optional[LotIdentity]:
    """Parse a full LGTIN or Digital Link class URI into LotIdentity."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or "0000000.000000" in text:
        return None

    m = _LGTIN_RE.match(text)
    if m:
        company, item, lot_raw = m.group(1), m.group(2), m.group(3)
        lot = unquote(lot_raw)
        if not lot:
            return None
        gtin = _company_item_to_gtin14(company, item)
        return LotIdentity(
            canonical_id=text,
            lot_token=lot,
            gtin=gtin,
            is_full_class_uri=True,
        )

    m = _DL_CLASS_RE.match(text)
    if m:
        gtin_raw, lot_raw = m.group(1), m.group(2)
        lot = unquote(lot_raw).strip()
        if not lot:
            return None
        gtin = normalize_gtin14(gtin_raw) or gtin_raw.zfill(14)
        return LotIdentity(
            canonical_id=text,
            lot_token=lot,
            gtin=gtin,
            is_full_class_uri=True,
        )

    return None


def is_full_class_uri(value: object) -> bool:
    parsed = parse_class_uri(value)
    return bool(parsed and parsed.is_full_class_uri)


def lot_token_only(value: object) -> Optional[str]:
    """Derived bare lot segment; never treat a full class URI as the token."""
    parsed = parse_class_uri(value)
    if parsed:
        return parsed.lot_token
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    # Legacy LGTIN/SGTIN segment helper for non-class schemes already truncated
    lowered = text.lower()
    if "lgtin" in lowered or "sgtin" in lowered:
        parts = text.rsplit(".", 1)
        if len(parts) == 2 and parts[1]:
            return unquote(parts[1])
        return None
    # Reject values that look like URIs but failed class parse
    if "://" in text or text.lower().startswith("urn:epc:"):
        return None
    return text


def normalize_epcis_lot(
    value: object,
    *,
    gtin: Optional[str] = None,
    prefer_full: Optional[bool] = None,
) -> Optional[LotIdentity]:
    """Normalize any lot-ish value into LotIdentity.

    When ``prefer_full`` is None, uses ``lossless_enabled()``.
    Dual-read: bare lot + GTIN rebuilds a Digital Link canonical ID.
    """
    use_full = lossless_enabled() if prefer_full is None else prefer_full

    parsed = parse_class_uri(value)
    if parsed:
        if use_full:
            return parsed
        return LotIdentity(
            canonical_id=parsed.lot_token,
            lot_token=parsed.lot_token,
            gtin=parsed.gtin or (normalize_gtin14(gtin) if gtin else None),
            is_full_class_uri=False,
        )

    # SGTIN is instance-level; expose serial as token but not a class URI
    if isinstance(value, str):
        sm = _SGTIN_RE.match(value.strip())
        if sm:
            serial = unquote(sm.group(3))
            g = _company_item_to_gtin14(sm.group(1), sm.group(2))
            return LotIdentity(
                canonical_id=serial if use_full else serial,
                lot_token=serial,
                gtin=g or (normalize_gtin14(gtin) if gtin else None),
                is_full_class_uri=False,
            )

    token = lot_token_only(value)
    if not token:
        return None

    gtin14 = normalize_gtin14(gtin) if gtin else None
    if use_full and gtin14:
        # Rebuild Digital Link; do not invent GTIN when absent
        from urllib.parse import quote

        canonical = f"https://id.gs1.org/01/{gtin14}/10/{quote(token, safe='-._~')}"
        return LotIdentity(
            canonical_id=canonical,
            lot_token=token,
            gtin=gtin14,
            is_full_class_uri=True,
        )

    return LotIdentity(
        canonical_id=token,
        lot_token=token,
        gtin=gtin14,
        is_full_class_uri=False,
    )


def resolve_stored_lot(
    *,
    epc_or_class: Any = None,
    ilmd_tlc: Any = None,
    flat_tlc: Any = None,
    gtin: Optional[str] = None,
) -> LotIdentity:
    """Resolve identity with SEL-598 precedence for canonical write.

    Prefer a full class URI from EPC/quantity class, then ILMD TLC when it is
    already a full URI, then rebuild from GTIN + derived token, else bare token.
    """
    for candidate in (epc_or_class, ilmd_tlc, flat_tlc):
        parsed = parse_class_uri(candidate)
        if parsed and lossless_enabled():
            return parsed
        if parsed and not lossless_enabled():
            return LotIdentity(
                canonical_id=parsed.lot_token,
                lot_token=parsed.lot_token,
                gtin=parsed.gtin or (normalize_gtin14(gtin) if gtin else None),
                is_full_class_uri=False,
            )

    # ILMD / flat may carry bare lot while EPC carries the class URI (handled above)
    for candidate in (ilmd_tlc, flat_tlc, epc_or_class):
        identity = normalize_epcis_lot(candidate, gtin=gtin)
        if identity:
            return identity

    raise ValueError(
        "EPCIS event carries no lot identifier (ILMD traceabilityLotCode or lotNumber, "
        "an LGTIN or SGTIN EPC, or traceability_lot_code); refusing to fabricate one"
    )
