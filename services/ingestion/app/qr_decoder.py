"""QR/Barcode decoding endpoints for GS1 Digital Link and GS1 AI payloads."""

from __future__ import annotations

import io
import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.authz import IngestionPrincipal, require_permission
from shared.funnel_events import emit_funnel_event

logger = logging.getLogger("qr-decoder")

router = APIRouter(prefix="/api/v1/qr", tags=["QR & GS1"])

_GROUP_SEPARATOR = chr(29)
_AI_FIXED_LENGTH = {
    "01": 14,  # GTIN
    "13": 6,   # packaging date
    "17": 6,   # expiration date
}
_AI_VARIABLE = {"10", "21"}  # lot, serial
_AI_SUPPORTED = set(_AI_FIXED_LENGTH.keys()) | _AI_VARIABLE


class QRDecodedFields(BaseModel):
    """Structured GS1 fields decoded from image payloads."""

    gtin: Optional[str] = None
    traceability_lot_code: Optional[str] = None
    serial: Optional[str] = None
    expiry_date: Optional[str] = None
    pack_date: Optional[str] = None
    source_format: str = "unknown"
    valid_gtin: Optional[bool] = None


class QRDecodeResponse(BaseModel):
    """Response payload for QR decode endpoint."""

    raw_value: str
    fields: QRDecodedFields
    fsma_compatible: bool = Field(
        ...,
        description="True when payload includes a valid GTIN or traceability lot code.",
    )


def _is_valid_gtin_check_digit(gtin: str) -> bool:
    if not re.fullmatch(r"\d{14}", gtin):
        return False

    digits = [int(char) for char in gtin]
    check_digit = digits[-1]

    total = 0
    weight = 3
    for digit in reversed(digits[:-1]):
        total += digit * weight
        weight = 1 if weight == 3 else 3

    expected = (10 - (total % 10)) % 10
    return expected == check_digit


def _parse_yymmdd(value: str) -> Optional[str]:
    if not re.fullmatch(r"\d{6}", value):
        return None

    year = 2000 + int(value[0:2])
    month = int(value[2:4])
    day = int(value[4:6])

    try:
        parsed = datetime(year=year, month=month, day=day)
    except ValueError:
        return None

    return parsed.strftime("%Y-%m-%d")


def _normalize_payload(payload: str) -> str:
    return payload.strip().replace(" ", "").replace("(", "").replace(")", "")


def _is_supported_ai(ai: str) -> bool:
    return ai in _AI_SUPPORTED


def _looks_like_ai_at(payload: str, index: int) -> bool:
    ai = payload[index:index + 2]
    if not _is_supported_ai(ai):
        return False
    if ai in _AI_FIXED_LENGTH:
        return index + 2 + _AI_FIXED_LENGTH[ai] <= len(payload)
    return index + 2 <= len(payload)


def _find_next_field_boundary(payload: str, start: int) -> int:
    for idx in range(start, len(payload)):
        if payload[idx] == _GROUP_SEPARATOR:
            return idx
        if _looks_like_ai_at(payload, idx):
            return idx
    return len(payload)


def _parse_digital_link(payload: str) -> Optional[QRDecodedFields]:
    cleaned = payload.strip()
    if not cleaned:
        return None

    if cleaned.startswith("/"):
        path = cleaned.split("?", 1)[0].split("#", 1)[0]
    else:
        try:
            parsed = urlparse(cleaned)
        except ValueError:
            return None
        if parsed.scheme not in {"http", "https"}:
            return None
        path = parsed.path

    segments = [segment for segment in path.split("/") if segment]
    if "01" not in segments:
        return None

    fields = QRDecodedFields(source_format="digital_link")
    for idx in range(len(segments) - 1):
        ai = segments[idx]
        value = unquote(segments[idx + 1]).strip()
        if not value:
            continue

        if ai == "01" and not fields.gtin:
            fields.gtin = value
        elif ai == "10" and not fields.traceability_lot_code:
            fields.traceability_lot_code = value
        elif ai == "21" and not fields.serial:
            fields.serial = value
        elif ai == "17" and not fields.expiry_date:
            fields.expiry_date = _parse_yymmdd(value)
        elif ai == "13" and not fields.pack_date:
            fields.pack_date = _parse_yymmdd(value)

    if not fields.gtin and not fields.traceability_lot_code and not fields.serial:
        return None

    if fields.gtin:
        fields.valid_gtin = _is_valid_gtin_check_digit(fields.gtin)
    return fields


def _parse_gs1_ai(payload: str) -> QRDecodedFields:
    fields = QRDecodedFields(source_format="gs1_ai")
    normalized = _normalize_payload(payload)
    index = 0

    while index < len(normalized):
        if normalized[index] == _GROUP_SEPARATOR:
            index += 1
            continue

        ai = normalized[index:index + 2]
        if not _is_supported_ai(ai):
            index += 1
            continue

        if ai in _AI_FIXED_LENGTH:
            length = _AI_FIXED_LENGTH[ai]
            value = normalized[index + 2:index + 2 + length]
            if len(value) == length:
                if ai == "01" and not fields.gtin:
                    fields.gtin = value
                elif ai == "13" and not fields.pack_date:
                    fields.pack_date = _parse_yymmdd(value)
                elif ai == "17" and not fields.expiry_date:
                    fields.expiry_date = _parse_yymmdd(value)
            index += 2 + length
            continue

        start = index + 2
        end = _find_next_field_boundary(normalized, start)
        value = normalized[start:end]
        if value:
            if ai == "10" and not fields.traceability_lot_code:
                fields.traceability_lot_code = value
            elif ai == "21" and not fields.serial:
                fields.serial = value
        index = end

    if fields.gtin:
        fields.valid_gtin = _is_valid_gtin_check_digit(fields.gtin)
    return fields


def _parse_gs1_payload(payload: str) -> QRDecodedFields:
    digital_link = _parse_digital_link(payload)
    if digital_link is not None:
        return digital_link

    return _parse_gs1_ai(payload)


def _decode_image_bytes(image_bytes: bytes) -> str:
    try:
        from PIL import Image  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment-specific dependency
        raise HTTPException(
            status_code=500,
            detail="Pillow is required for QR decoding",
        ) from exc

    try:
        from pyzbar.pyzbar import decode as pyzbar_decode  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment-specific dependency
        raise HTTPException(
            status_code=500,
            detail="pyzbar is required for QR decoding",
        ) from exc

    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid image payload") from exc

    decoded_items = pyzbar_decode(image)
    if not decoded_items:
        raise HTTPException(status_code=422, detail="No barcode or QR code detected in image")

    first = decoded_items[0]
    decoded_value = first.data.decode("utf-8", errors="replace").strip()
    if not decoded_value:
        raise HTTPException(status_code=422, detail="Decoded barcode payload was empty")
    return decoded_value


@router.post(
    "/decode",
    response_model=QRDecodeResponse,
    summary="Decode GS1 QR/barcode image",
    description=(
        "Decodes an uploaded barcode/QR image and returns structured GS1 fields "
        "(GTIN, lot, serial, expiry, pack date)."
    ),
)
async def decode_qr_image(
    file: UploadFile = File(..., description="Image containing a QR/barcode"),
    principal: IngestionPrincipal = Depends(require_permission("scan.decode")),
) -> QRDecodeResponse:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Upload must be an image content type")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image payload too large (max 10MB)")

    raw_value = _decode_image_bytes(image_bytes)
    fields = _parse_gs1_payload(raw_value)
    fsma_compatible = bool(
        fields.traceability_lot_code or (fields.gtin and fields.valid_gtin is not False)
    )

    emit_funnel_event(
        tenant_id=principal.tenant_id,
        event_name="first_scan",
        metadata={
            "source_format": fields.source_format,
            "fsma_compatible": fsma_compatible,
        },
    )

    return QRDecodeResponse(
        raw_value=raw_value,
        fields=fields,
        fsma_compatible=fsma_compatible,
    )
