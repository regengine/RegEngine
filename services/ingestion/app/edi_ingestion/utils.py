from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from app.webhook_models import VALID_UNITS_OF_MEASURE

from .constants import _X12_UOM_MAP


def _normalize_unit(unit_value: Optional[str]) -> str:
    if not unit_value:
        return "units"

    x12_code = re.sub(r"[^A-Za-z]", "", unit_value).upper()
    mapped = _X12_UOM_MAP.get(x12_code, unit_value.strip().lower())
    if mapped not in VALID_UNITS_OF_MEASURE:
        return "units"
    return mapped


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

    total = sum(
        int(digit) * (3 if index % 2 else 1)
        for index, digit in enumerate(reversed(clean[:-1]))
    )
    expected = (10 - (total % 10)) % 10
    return clean if int(clean[-1]) == expected else None


def _ship_timestamp_and_date(ship_date_raw: Optional[str], ship_time_raw: Optional[str]) -> tuple[str, str]:
    now = datetime.now(timezone.utc)

    if not ship_date_raw:
        return now.isoformat(), now.date().isoformat()

    clean_date = re.sub(r"\D", "", ship_date_raw)
    if len(clean_date) != 8:
        return now.isoformat(), now.date().isoformat()

    clean_time = re.sub(r"\D", "", ship_time_raw or "")
    if len(clean_time) >= 4:
        hh = int(clean_time[:2])
        mm = int(clean_time[2:4])
    else:
        hh = 0
        mm = 0

    try:
        parsed = datetime(
            year=int(clean_date[:4]),
            month=int(clean_date[4:6]),
            day=int(clean_date[6:8]),
            hour=hh,
            minute=mm,
            tzinfo=timezone.utc,
        )
    except ValueError:
        return now.isoformat(), now.date().isoformat()

    # Keep webhook model bounds to avoid stale/future rejection.
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
