from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from shared.fsma_validation import verify_gs1_check_digit

from ..webhook_models import VALID_UNITS_OF_MEASURE
from .constants import _NON_X12_UOM_ALIASES, _X12_UOM_MAP

logger = logging.getLogger("edi-ingestion")


def _century_pivot() -> int:
    """YY < pivot → 20YY, else 19YY. Configurable via EDI_CENTURY_PIVOT."""
    try:
        return int(os.getenv("EDI_CENTURY_PIVOT", "50"))
    except ValueError:
        return 50


def _parse_edi_date_digits(digits: str) -> datetime:
    """Parse an EDI date (CCYYMMDD or YYMMDD) into a UTC datetime.

    Accepts 8-digit CCYYMMDD at full precision and 6-digit YYMMDD with
    a configurable century window (#1167). Raises ``ValueError`` on any
    other length or on invalid year/month/day components so the caller
    can surface a 400 instead of silently substituting ``now()`` —
    retransmitted archival EDI was being re-stamped as today's
    shipment and corrupting FSMA 204 lookback.
    """
    if len(digits) == 8:
        year = int(digits[:4])
        month = int(digits[4:6])
        day = int(digits[6:8])
    elif len(digits) == 6:
        yy = int(digits[:2])
        pivot = _century_pivot()
        year = 2000 + yy if yy < pivot else 1900 + yy
        month = int(digits[2:4])
        day = int(digits[4:6])
        logger.info(
            "edi_date_century_inferred yy=%02d pivot=%d -> %d",
            yy,
            pivot,
            year,
        )
    else:
        raise ValueError(f"EDI date must be 8-digit CCYYMMDD or 6-digit YYMMDD, got {len(digits)} digits")
    return datetime(year=year, month=month, day=day, tzinfo=timezone.utc)


def _resolve_unit_code(unit_value: Optional[str]) -> Optional[str]:
    """Resolve a raw X12 unit element to an FSMA vocabulary unit.

    Returns ``None`` when the value is blank or cannot be resolved, so
    callers can choose between coercing (``_normalize_unit``) and failing
    closed (``routes._valid_unit_or_none``) without the two drifting
    apart on which codes they accept (#2978).

    Lookup order: the X12 element-355 table, then the explicitly
    non-DE355 alias table, then the raw lowercased value (which lets a
    partner sending "cases" outright still match the vocabulary).
    """
    if unit_value is None:
        return None
    raw = str(unit_value).strip()
    if not raw:
        return None

    x12_code = re.sub(r"[^A-Za-z]", "", raw).upper()
    mapped = _X12_UOM_MAP.get(x12_code) or _NON_X12_UOM_ALIASES.get(x12_code) or raw.lower()
    return mapped if mapped in VALID_UNITS_OF_MEASURE else None


def _normalize_unit(unit_value: Optional[str]) -> str:
    if not unit_value:
        return "units"

    resolved = _resolve_unit_code(unit_value)
    if resolved is None:
        # #2978: the miss path used to be entirely silent, so a valid X12
        # unit that this table simply did not know about became "units"
        # with nothing in the logs to show the KDE had been degraded.
        logger.warning(
            "edi_uom_unmapped raw=%r coerced_to=units — unit is not an X12 "
            "element-355 code this route recognizes; the quantity KDE is "
            "numerically intact but semantically degraded",
            unit_value,
        )
        return "units"
    return resolved


def _safe_float(value: Optional[str], fallback: float = 1.0) -> float:
    if value is None:
        return fallback
    try:
        parsed = float(value)
        if parsed > 0:
            return parsed
    except (TypeError, ValueError):
        pass
    return fallback


def _valid_gln_or_none(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    clean = re.sub(r"\D", "", value)
    if len(clean) != 13:
        return None

    # Delegate the GS1 mod-10 check-digit math to the shared canonical helper so
    # this gate agrees with ``webhook_models.validate_gln`` (which IngestEvent
    # re-runs) and never disagrees on a 13-digit GLN.
    return clean if verify_gs1_check_digit(clean) else None


def _ship_timestamp_and_date(ship_date_raw: Optional[str], ship_time_raw: Optional[str]) -> tuple[str, str]:
    """Normalize an EDI shipment date/time into an ISO timestamp and date.

    #1167: unparseable dates now raise HTTP 400 rather than silently
    falling back to ``datetime.now()`` — retransmitted archival EDI was
    being re-stamped as today's shipment. Stale dates (> 90 days old)
    still snap to "now" for the ingest timestamp to keep webhook model
    bounds valid, but the original parsed date is preserved separately
    so downstream FSMA 204 lookback sees the real event date.
    """
    now = datetime.now(timezone.utc)

    if not ship_date_raw:
        return now.isoformat(), now.date().isoformat()

    clean_date = re.sub(r"\D", "", ship_date_raw)

    try:
        parsed = _parse_edi_date_digits(clean_date)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_edi_date",
                "raw": ship_date_raw,
                "message": (
                    f"EDI date could not be parsed as CCYYMMDD or YYMMDD: {exc}. "
                    "Silent fallback to now() was removed per #1167."
                ),
            },
        ) from exc

    clean_time = re.sub(r"\D", "", ship_time_raw or "")
    if len(clean_time) >= 4:
        try:
            hh = int(clean_time[:2])
            mm = int(clean_time[2:4])
            parsed = parsed.replace(hour=hh, minute=mm)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_edi_time",
                    "raw": ship_time_raw,
                    "message": f"EDI time not parseable: {exc}",
                },
            ) from exc

    # Keep webhook model bounds to avoid stale/future rejection — the
    # ingest timestamp snaps to "now" if the EDI claims a shipment
    # older than 90 days or > 24h in the future. The parsed event_date
    # is returned unchanged so FSMA 204 traceability sees the real date.
    if parsed < now - timedelta(days=90) or parsed > now + timedelta(hours=24):
        return now.isoformat(), parsed.date().isoformat()

    return parsed.isoformat(), parsed.date().isoformat()


def _verify_partner_id(x_partner_id: Optional[str]) -> None:
    required = os.getenv("EDI_REQUIRE_PARTNER_ID", "").lower() in {"1", "true", "yes"}
    if required and not x_partner_id:
        raise HTTPException(status_code=400, detail="X-Partner-ID header required for EDI ingest")

    allowlist_raw = os.getenv("EDI_PARTNER_ALLOWLIST", "")
    allowlist = {item.strip() for item in allowlist_raw.split(",") if item.strip()}
    if allowlist and x_partner_id and x_partner_id not in allowlist:
        raise HTTPException(status_code=403, detail="Partner not authorized for EDI ingest")
