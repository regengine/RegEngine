"""
FastAPI router for TLC label generation.

POST /api/v1/labels/generate     — single label
POST /api/v1/labels/generate-batch — batch from seed data
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Optional

from regengine.labels import LabelData, generate_label_png, generate_label_zpl, generate_label_pdf

router = APIRouter(prefix="/api/v1/labels", tags=["labels"])


class LabelRequest(BaseModel):
    """Request body for label generation."""
    traceability_lot_code: str = Field(..., description="TLC to encode")
    product_description: str = Field(..., description="Product name")
    quantity: int = Field(100, description="Lot quantity")
    unit_of_measure: str = Field("cases", description="UOM")
    location_gln: str = Field(..., description="GLN of origin facility")
    location_name: str = Field(..., description="Human-readable location")
    lot_date: str = Field(..., description="YYYY-MM-DD")
    field_id: Optional[str] = None
    vessel_name: Optional[str] = None
    harvest_area: Optional[str] = None
    format: str = Field("png", description="Output format: png, zpl, pdf")


class BatchRequest(BaseModel):
    """Request for generating sequential labels."""
    tlc_prefix: str = Field(..., description="TLC prefix for sequential generation")
    product_description: str
    count: int = Field(10, ge=1, le=1000)
    quantity_per: int = Field(1, description="Quantity per label")
    unit_of_measure: str = Field("cases")
    location_gln: str
    location_name: str
    lot_date: str
    format: str = Field("png")


MEDIA_TYPES = {
    "png": "image/png",
    "pdf": "application/pdf",
    "zpl": "text/plain",
}


@router.post("/generate")
async def generate_label(req: LabelRequest) -> Response:
    """Generate a single TLC label."""
    label = LabelData(
        traceability_lot_code=req.traceability_lot_code,
        product_description=req.product_description,
        quantity=req.quantity,
        unit_of_measure=req.unit_of_measure,
        location_gln=req.location_gln,
        location_name=req.location_name,
        lot_date=req.lot_date,
        field_id=req.field_id,
        vessel_name=req.vessel_name,
        harvest_area=req.harvest_area,
    )

    try:
        if req.format == "png":
            content = generate_label_png(label)
        elif req.format == "zpl":
            content = generate_label_zpl(label).encode("utf-8")
        elif req.format == "pdf":
            content = generate_label_pdf(label)
        else:
            raise HTTPException(400, f"Unknown format: {req.format}")
    except Exception as e:
        raise HTTPException(500, f"Label generation failed: {e}")

    return Response(
        content=content,
        media_type=MEDIA_TYPES.get(req.format, "application/octet-stream"),
        headers={
            "Content-Disposition": f'inline; filename="label_{req.traceability_lot_code}.{req.format}"',
        },
    )


@router.post("/generate-batch")
async def generate_batch(req: BatchRequest) -> Response:
    """Generate sequential TLC labels as a ZIP archive."""
    import io
    import zipfile

    labels = []
    for i in range(req.count):
        tlc = f"{req.tlc_prefix}-{i + 1:04d}"
        labels.append(LabelData(
            traceability_lot_code=tlc,
            product_description=req.product_description,
            quantity=req.quantity_per,
            unit_of_measure=req.unit_of_measure,
            location_gln=req.location_gln,
            location_name=req.location_name,
            lot_date=req.lot_date,
        ))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label in labels:
            safe_tlc = label.traceability_lot_code.replace("/", "_")
            if req.format == "png":
                content = generate_label_png(label)
                zf.writestr(f"label_{safe_tlc}.png", content)
            elif req.format == "zpl":
                content = generate_label_zpl(label)
                zf.writestr(f"label_{safe_tlc}.zpl", content)
            elif req.format == "pdf":
                content = generate_label_pdf(label)
                zf.writestr(f"label_{safe_tlc}.pdf", content)

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="labels_{req.tlc_prefix}.zip"',
        },
    )
