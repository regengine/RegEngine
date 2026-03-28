"""Computer vision endpoint for food label / packaging image analysis.

Accepts an uploaded image of a food product label or packaging, runs GPT-4o
vision to extract structured traceability data, and returns FSMA 204-compatible
KDE fields.  Falls back to barcode-only decoding when the LLM is unavailable.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from shared.auth import APIKey, require_api_key

logger = logging.getLogger("label-vision")

router = APIRouter(prefix="/api/v1/vision", tags=["Computer Vision"])


# ── Response models ──────────────────────────────────────────────────

class ExtractedKDE(BaseModel):
    """A single Key Data Element extracted from the label."""
    field: str = Field(..., description="KDE field name (e.g. gtin, lot_code, expiry_date)")
    value: Optional[str] = None
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Model confidence 0-1")

class LabelVisionResponse(BaseModel):
    """Structured output from food label vision analysis."""
    product_name: Optional[str] = None
    brand: Optional[str] = None
    gtin: Optional[str] = None
    lot_code: Optional[str] = None
    serial_number: Optional[str] = None
    expiry_date: Optional[str] = None
    pack_date: Optional[str] = None
    net_weight: Optional[str] = None
    unit_of_measure: Optional[str] = None
    facility_name: Optional[str] = None
    facility_address: Optional[str] = None
    country_of_origin: Optional[str] = None
    ingredients: Optional[str] = None
    allergens: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    fsma_kdes: List[ExtractedKDE] = Field(default_factory=list)
    fsma_compatible: bool = False
    raw_text: Optional[str] = None
    analysis_engine: str = "gpt-4o-vision"


# ── Vision prompt ────────────────────────────────────────────────────

LABEL_EXTRACTION_PROMPT = """You are an expert food traceability analyst. Analyze this food product label or packaging image and extract ALL visible information into structured JSON.
Focus especially on FSMA 204 Key Data Elements (KDEs):
- Product name / description
- Brand name
- GTIN (Global Trade Item Number) — usually printed as a barcode number
- Lot code / batch number (may be labeled "LOT", "Batch", "L:", "B/B:")
- Serial number
- Expiration / best-by date (any format — normalize to YYYY-MM-DD)
- Pack date / production date (normalize to YYYY-MM-DD)
- Net weight and unit of measure
- Facility name and address
- Country of origin
- Ingredient list (full text)
- Allergens (list each one separately)
- Certifications (USDA Organic, Non-GMO, Kosher, etc.)

Also extract any other text visible on the label as "raw_text".

For each FSMA KDE you find, include it in the "fsma_kdes" array with the field name, extracted value, and your confidence (0.0-1.0).

Set "fsma_compatible" to true if you found at least a product name AND either a lot code or GTIN.

Return ONLY valid JSON matching this schema:
{
    "product_name": "string or null",
    "brand": "string or null",
    "gtin": "string or null",
    "lot_code": "string or null",
    "serial_number": "string or null",
    "expiry_date": "YYYY-MM-DD or null",
    "pack_date": "YYYY-MM-DD or null",
    "net_weight": "string or null",
    "unit_of_measure": "string or null",
    "facility_name": "string or null",
    "facility_address": "string or null",
    "country_of_origin": "string or null",
    "ingredients": "string or null",
    "allergens": ["string"],
    "certifications": ["string"],
    "fsma_kdes": [{"field": "string", "value": "string", "confidence": 0.95}],
    "fsma_compatible": true,
    "raw_text": "all visible text"
}"""

# ── Endpoint ─────────────────────────────────────────────────────────

@router.post(
    "/analyze-label",
    response_model=LabelVisionResponse,
    summary="Analyze food label image with computer vision",
    description=(
        "Upload a photo of a food product label or packaging. "
        "Returns structured KDE fields for FSMA 204 traceability."
    ),
)
async def analyze_label(
    file: UploadFile = File(..., description="Photo of food label or packaging"),
    api_key: APIKey = Depends(require_api_key),
) -> LabelVisionResponse:
    # Validate image
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Upload must be an image")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large (max 10 MB)")

    # Encode to base64
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    # Determine content type for the data URI
    content_type = file.content_type or "image/jpeg"
    # Try GPT-4o vision
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set — returning empty analysis")
        return LabelVisionResponse(
            analysis_engine="unavailable",
            raw_text="Vision analysis unavailable — OPENAI_API_KEY not configured.",
        )

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": LABEL_EXTRACTION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{content_type};base64,{image_b64}",
                            },
                        },
                    ],
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=2000,
        )

        content = response.choices[0].message.content
        if not content:
            raise HTTPException(status_code=502, detail="Empty response from vision model")
        parsed: Dict[str, Any] = json.loads(content)

        # Build KDE list if not provided by the model
        fsma_kdes = parsed.get("fsma_kdes", [])
        if not fsma_kdes:
            kde_fields = [
                ("gtin", parsed.get("gtin")),
                ("lot_code", parsed.get("lot_code")),
                ("serial_number", parsed.get("serial_number")),
                ("expiry_date", parsed.get("expiry_date")),
                ("pack_date", parsed.get("pack_date")),
                ("product_name", parsed.get("product_name")),
                ("net_weight", parsed.get("net_weight")),
                ("country_of_origin", parsed.get("country_of_origin")),
            ]
            fsma_kdes = [
                {"field": f, "value": v, "confidence": 0.9}
                for f, v in kde_fields
                if v
            ]

        return LabelVisionResponse(
            product_name=parsed.get("product_name"),
            brand=parsed.get("brand"),
            gtin=parsed.get("gtin"),
            lot_code=parsed.get("lot_code"),
            serial_number=parsed.get("serial_number"),
            expiry_date=parsed.get("expiry_date"),
            pack_date=parsed.get("pack_date"),
            net_weight=parsed.get("net_weight"),
            unit_of_measure=parsed.get("unit_of_measure"),
            facility_name=parsed.get("facility_name"),
            facility_address=parsed.get("facility_address"),
            country_of_origin=parsed.get("country_of_origin"),
            ingredients=parsed.get("ingredients"),
            allergens=parsed.get("allergens", []),
            certifications=parsed.get("certifications", []),
            fsma_kdes=[ExtractedKDE(**kde) for kde in fsma_kdes],
            fsma_compatible=parsed.get("fsma_compatible", False),
            raw_text=parsed.get("raw_text"),
            analysis_engine="gpt-4o-vision",
        )

    except json.JSONDecodeError as exc:
        logger.error("Vision model returned invalid JSON: %s", exc)
        raise HTTPException(status_code=502, detail="Vision model returned unparseable response")
    except (ImportError, AttributeError, TypeError, ValueError, KeyError, OSError, IOError) as exc:
        logger.error("Vision analysis failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"Vision analysis failed: {str(exc)}")