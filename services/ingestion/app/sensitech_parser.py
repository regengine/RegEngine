"""
Sensitech TempTale CSV Parser.

Parses Sensitech TempTale temperature logger exports and converts them
to FSMA 204 CTE events (Cooling/Receiving) with temperature KDEs.

Sensitech TempTale CSV format (typical):
  Timestamp, Temperature (°C), Alarm Status, Serial Number
  2026-02-26 08:00:00, 2.1, OK, ST-12345
  2026-02-26 08:15:00, 2.3, OK, ST-12345
  2026-02-26 08:30:00, 6.8, ALARM, ST-12345
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .config import get_settings
from .webhook_models import (
    IngestEvent,
    IngestResponse,
    WebhookCTEType,
    WebhookPayload,
)
from .shared.upload_limits import read_upload_with_limit, MAX_CSV_FILE_SIZE_BYTES
from .webhook_compat import _verify_api_key, ingest_events

logger = logging.getLogger("sensitech-parser")

router = APIRouter(prefix="/api/v1/ingest/iot", tags=["IoT Import"])


class TemperatureReading(BaseModel):
    """A single parsed temperature reading."""
    timestamp: str
    temperature_celsius: float
    alarm_status: str = "OK"
    serial_number: Optional[str] = None


class TemperatureExcursion(BaseModel):
    """A temperature excursion detected during parsing."""
    timestamp: str
    temperature_celsius: float
    threshold_celsius: float
    serial_number: Optional[str] = None
    severity: str = "WARNING"  # WARNING or CRITICAL


class SensitechImportResponse(BaseModel):
    """Response from Sensitech import."""
    readings_parsed: int = 0
    events_created: int = 0
    excursions_detected: int = 0
    excursions: list[TemperatureExcursion] = Field(default_factory=list)
    min_temperature: Optional[float] = None
    max_temperature: Optional[float] = None
    avg_temperature: Optional[float] = None
    duration_hours: Optional[float] = None
    ingestion_result: Optional[IngestResponse] = None


def _parse_sensitech_csv(content: str) -> list[TemperatureReading]:
    """Parse Sensitech TempTale CSV format."""
    readings: list[TemperatureReading] = []

    reader = csv.reader(io.StringIO(content))

    # Auto-detect header row (look for "Timestamp" or "Time" column)
    header_row = None
    for row in reader:
        if not row:
            continue
        # Check if this row looks like a header
        first_cell = row[0].strip().lower()
        if any(keyword in first_cell for keyword in ["timestamp", "time", "date"]):
            header_row = [col.strip().lower() for col in row]
            break

    if header_row is None:
        # No header found — assume default column order
        # Reset reader
        reader = csv.reader(io.StringIO(content))
        header_row = ["timestamp", "temperature", "alarm_status", "serial_number"]

    # Find column indices
    time_idx = 0
    temp_idx = 1
    alarm_idx = None
    serial_idx = None

    for i, col in enumerate(header_row):
        if any(k in col for k in ["temp", "°c", "celsius", "reading"]):
            temp_idx = i
        elif any(k in col for k in ["alarm", "status", "alert"]):
            alarm_idx = i
        elif any(k in col for k in ["serial", "device", "sensor", "id"]):
            serial_idx = i

    # Parse data rows
    for row in reader:
        if not row or len(row) <= temp_idx:
            continue

        # Skip comment/empty rows
        if row[0].strip().startswith("#") or not row[0].strip():
            continue

        try:
            temp_str = row[temp_idx].strip().replace("°C", "").replace("°F", "").strip()
            temperature = float(temp_str)

            readings.append(TemperatureReading(
                timestamp=row[time_idx].strip(),
                temperature_celsius=temperature,
                alarm_status=row[alarm_idx].strip() if alarm_idx is not None and alarm_idx < len(row) else "OK",
                serial_number=row[serial_idx].strip() if serial_idx is not None and serial_idx < len(row) else None,
            ))
        except (ValueError, IndexError):
            continue  # Skip unparseable rows

    return readings


def _normalize_iso_timestamp_or_400(raw: str) -> str:
    """Coerce a Sensitech CSV timestamp into a valid ISO 8601 string, or raise 400.

    Accepts:
      - ISO 8601 variants (``YYYY-MM-DD``, ``YYYY-MM-DD HH:MM:SS``,
        ``YYYY-MM-DDTHH:MM:SS[Z|+HH:MM]``) — passed through unchanged.
      - Compact ``YYYYMMDD`` — expanded to midnight UTC.

    Bare times (e.g. ``08:00:00``), empty strings, and anything else
    that is not recognizably a date are rejected with 400 Bad Request,
    rather than allowed to fall through to Pydantic and surface as 500.
    """
    candidate = raw.strip() if raw else ""
    if not candidate:
        raise HTTPException(
            status_code=400,
            detail="Sensitech CSV has an empty timestamp — cannot create CTE event.",
        )

    if candidate.count("-") >= 2:
        normalized = candidate
    elif candidate.isdigit() and len(candidate) == 8:
        normalized = f"{candidate[:4]}-{candidate[4:6]}-{candidate[6:8]}T00:00:00Z"
    else:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Could not parse Sensitech timestamp {candidate!r} as a date. "
                "Expected ISO 8601 (e.g. '2026-02-26' or '2026-02-26T08:00:00') "
                "or compact YYYYMMDD (e.g. '20260226')."
            ),
        )

    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=400,
            detail=f"Could not parse Sensitech timestamp {candidate!r} as ISO 8601.",
        )
    return normalized


def _detect_excursions(
    readings: list[TemperatureReading],
    cold_threshold: float = 5.0,
    freeze_threshold: float = -1.0,
) -> list[TemperatureExcursion]:
    """Detect temperature excursions."""
    excursions: list[TemperatureExcursion] = []

    for r in readings:
        if r.temperature_celsius > cold_threshold:
            excursions.append(TemperatureExcursion(
                timestamp=r.timestamp,
                temperature_celsius=r.temperature_celsius,
                threshold_celsius=cold_threshold,
                serial_number=r.serial_number,
                severity="CRITICAL" if r.temperature_celsius > cold_threshold + 3 else "WARNING",
            ))
        elif r.temperature_celsius < freeze_threshold:
            excursions.append(TemperatureExcursion(
                timestamp=r.timestamp,
                temperature_celsius=r.temperature_celsius,
                threshold_celsius=freeze_threshold,
                serial_number=r.serial_number,
                severity="WARNING",
            ))

    return excursions


@router.post(
    "/sensitech",
    response_model=SensitechImportResponse,
    summary="Import Sensitech TempTale data",
    description=(
        "Parse a Sensitech TempTale CSV temperature log, detect excursions, "
        "and create CTE events linked to a specified Traceability Lot Code."
    ),
)
async def import_sensitech(
    file: UploadFile = File(..., description="Sensitech TempTale CSV export"),
    traceability_lot_code: str = Form(..., description="TLC to link temperature data to"),
    product_description: str = Form(..., description="Product name"),
    cte_type: str = Form("cooling", description="CTE type: cooling or receiving"),
    location_name: str = Form(..., description="Facility name where logger was deployed"),
    location_gln: Optional[str] = Form(None, description="Facility GLN (optional)"),
    cold_threshold: float = Form(5.0, description="Max temperature threshold (°C)"),
    _: None = Depends(_verify_api_key),
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
) -> SensitechImportResponse:
    """Import Sensitech temperature data and create CTE events."""

    # Validate CTE type
    if cte_type.lower() not in ("cooling", "receiving"):
        raise HTTPException(
            status_code=400,
            detail="cte_type must be 'cooling' or 'receiving' for temperature data"
        )

    # Parse CSV
    content = (await read_upload_with_limit(file, max_bytes=MAX_CSV_FILE_SIZE_BYTES, label="Sensitech CSV")).decode("utf-8-sig")
    readings = _parse_sensitech_csv(content)

    if not readings:
        raise HTTPException(status_code=400, detail="No temperature readings found in file")

    # Detect excursions
    excursions = _detect_excursions(readings, cold_threshold=cold_threshold)

    # Compute statistics
    temps = [r.temperature_celsius for r in readings]
    min_temp = min(temps)
    max_temp = max(temps)
    avg_temp = sum(temps) / len(temps)

    # Compute duration
    duration_hours = None
    try:
        first_ts = datetime.fromisoformat(readings[0].timestamp.replace("Z", "+00:00"))
        last_ts = datetime.fromisoformat(readings[-1].timestamp.replace("Z", "+00:00"))
        duration_hours = round((last_ts - first_ts).total_seconds() / 3600, 2)
    except (ValueError, AttributeError):
        pass

    # Create CTE events — one summary event for the full monitoring period
    cte = WebhookCTEType(cte_type.lower())
    date_field = f"{cte_type}_date"

    event_timestamp = _normalize_iso_timestamp_or_400(readings[0].timestamp)
    event_date = event_timestamp.split("T")[0].split(" ")[0]

    events = [
        IngestEvent(
            cte_type=cte,
            traceability_lot_code=traceability_lot_code,
            product_description=product_description,
            quantity=len(readings),
            unit_of_measure="readings",
            location_gln=location_gln,
            location_name=location_name,
            timestamp=event_timestamp,
            kdes={
                date_field: event_date,
                "temperature_min_celsius": min_temp,
                "temperature_max_celsius": max_temp,
                "temperature_avg_celsius": round(avg_temp, 2),
                "temperature_readings_count": len(readings),
                "temperature_excursions_count": len(excursions),
                "duration_hours": duration_hours,
                "sensor_serial": readings[0].serial_number,
                "data_source": "sensitech_temptale",
            },
        )
    ]

    # Ingest via webhook pipeline
    payload = WebhookPayload(source="sensitech", events=events)
    ingestion_result = await ingest_events(
        payload,
        x_regengine_api_key=x_regengine_api_key,
    )

    return SensitechImportResponse(
        readings_parsed=len(readings),
        events_created=ingestion_result.accepted,
        excursions_detected=len(excursions),
        excursions=excursions,
        min_temperature=min_temp,
        max_temperature=max_temp,
        avg_temperature=round(avg_temp, 2),
        duration_hours=duration_hours,
        ingestion_result=ingestion_result,
    )
