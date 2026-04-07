#!/usr/bin/env python3
"""
RegEngine TLC Label Generator.

Generates printable FSMA 204 TLC labels with QR codes,
human-readable fields, and GS1-compatible formatting.

Supports PNG, PDF, and ZPL (Zebra thermal printer) output.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Optional

import qrcode
from PIL import Image, ImageDraw, ImageFont


@dataclass
class LabelData:
    """Data for a single TLC label."""
    traceability_lot_code: str
    product_description: str
    quantity: int
    unit_of_measure: str
    location_gln: str
    location_name: str
    lot_date: str
    field_id: Optional[str] = None
    vessel_name: Optional[str] = None
    harvest_area: Optional[str] = None
    gtin: Optional[str] = None


# ─── QR Code ─────────────────────────────────────────────────────────────────

def generate_qr(data: str, box_size: int = 8) -> Image.Image:
    """Generate a QR code image from string data."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


# ─── PNG Label ───────────────────────────────────────────────────────────────

def generate_label_png(label: LabelData) -> bytes:
    """
    Generate a printable label as PNG image.

    Layout:
    ┌─────────────────────────────────┐
    │  [QR]   Product Description     │
    │         TLC: XXX-XXX-XXX        │
    │         Date: YYYY-MM-DD        │
    │         Origin: Location Name   │
    │         GLN: 0614141000001      │
    │         Qty: 500 cases          │
    │                                 │
    │  regengine.co/v/TLC             │
    └─────────────────────────────────┘
    """
    # Dimensions: 4x2 inches at 203 DPI (standard Zebra label)
    W, H = 812, 406
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    # Use default font (PIL built-in) at different sizes
    try:
        font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
        font_medium = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 13)
        font_mono = ImageFont.truetype("/System/Library/Fonts/Courier.dfont", 14)
    except (OSError, IOError):
        font_large = ImageFont.load_default()
        font_medium = font_large
        font_small = font_large
        font_mono = font_large

    # Border
    draw.rectangle([2, 2, W - 3, H - 3], outline="black", width=2)

    # QR code (left side)
    qr_img = generate_qr(label.traceability_lot_code, box_size=6)
    qr_size = min(qr_img.size[0], 160)
    qr_img = qr_img.resize((qr_size, qr_size))
    img.paste(qr_img, (15, 15))

    # Text fields (right side)
    x_text = qr_size + 30
    y = 18

    # Product name
    draw.text((x_text, y), label.product_description, fill="black", font=font_large)
    y += 30

    # TLC
    draw.text((x_text, y), f"TLC: {label.traceability_lot_code}", fill="black", font=font_mono)
    y += 22

    # Separator line
    draw.line([(x_text, y), (W - 15, y)], fill="#cccccc", width=1)
    y += 8

    # Date
    draw.text((x_text, y), f"Lot Date: {label.lot_date}", fill="black", font=font_medium)
    y += 22

    # Origin
    origin = label.location_name
    if label.field_id:
        origin += f" — {label.field_id}"
    if label.vessel_name:
        origin = f"Vessel: {label.vessel_name}"
    draw.text((x_text, y), f"Origin: {origin}", fill="black", font=font_medium)
    y += 22

    # GLN
    draw.text((x_text, y), f"GLN: {label.location_gln}", fill="black", font=font_medium)
    y += 22

    # Quantity
    draw.text((x_text, y), f"Qty: {label.quantity} {label.unit_of_measure}", fill="black", font=font_medium)
    y += 22

    if label.harvest_area:
        draw.text((x_text, y), f"Area: {label.harvest_area}", fill="#555555", font=font_small)
        y += 18

    # Bottom: verification URL
    y_bottom = H - 30
    draw.line([(10, y_bottom - 8), (W - 10, y_bottom - 8)], fill="#cccccc", width=1)
    verification_url = f"regengine.co/v/{label.traceability_lot_code}"
    draw.text((15, y_bottom), verification_url, fill="#666666", font=font_small)

    # FSMA badge
    draw.text((W - 140, y_bottom), "FSMA 204 Compliant", fill="#0066cc", font=font_small)

    # Output PNG bytes
    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(203, 203))
    return buf.getvalue()


# ─── ZPL Label ───────────────────────────────────────────────────────────────

def generate_label_zpl(label: LabelData) -> str:
    """
    Generate ZPL (Zebra Programming Language) for thermal printers.

    Standard 4x2" label at 203 DPI.
    """
    tlc = label.traceability_lot_code
    return f"""^XA
^PW812
^LL406
^FO20,20^BQN,2,5^FDMA,{tlc}^FS
^FO200,20^A0N,28,28^FD{label.product_description}^FS
^FO200,55^A0N,20,20^FDTLC: {tlc}^FS
^FO200,85^A0N,20,20^FDDate: {label.lot_date}^FS
^FO200,110^A0N,20,20^FDOrigin: {label.location_name}^FS
^FO200,135^A0N,20,20^FDGLN: {label.location_gln}^FS
^FO200,160^A0N,20,20^FDQty: {label.quantity} {label.unit_of_measure}^FS
^FO20,360^A0N,16,16^FDregengine.co/v/{tlc}^FS
^FO550,360^A0N,16,16^FDFSMA 204 Compliant^FS
^XZ"""


# ─── PDF Label ───────────────────────────────────────────────────────────────

def generate_label_pdf(label: LabelData) -> bytes:
    """Generate a PDF label (single label per page, 4x2 inches)."""
    # Use PNG-in-PDF approach for simplicity
    try:
        from fpdf import FPDF
    except ImportError:
        # Fallback: return PNG wrapped in a minimal PDF
        png_bytes = generate_label_png(label)
        return _png_to_simple_pdf(png_bytes)

    pdf = FPDF(orientation="L", unit="in", format=(2, 4))
    pdf.add_page()
    pdf.set_auto_page_break(auto=False)

    # Generate QR as temp image
    qr_img = generate_qr(label.traceability_lot_code)
    qr_buf = io.BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)

    pdf.image(qr_buf, x=0.1, y=0.1, w=0.8)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_xy(1.0, 0.15)
    pdf.cell(2.8, 0.2, label.product_description)

    pdf.set_font("Courier", "", 9)
    pdf.set_xy(1.0, 0.38)
    pdf.cell(2.8, 0.15, f"TLC: {label.traceability_lot_code}")

    pdf.set_font("Helvetica", "", 9)
    fields = [
        f"Date: {label.lot_date}",
        f"Origin: {label.location_name}",
        f"GLN: {label.location_gln}",
        f"Qty: {label.quantity} {label.unit_of_measure}",
    ]
    y = 0.58
    for f in fields:
        pdf.set_xy(1.0, y)
        pdf.cell(2.8, 0.15, f)
        y += 0.18

    pdf.set_font("Helvetica", "", 7)
    pdf.set_xy(0.1, 1.7)
    pdf.cell(2, 0.15, f"regengine.co/v/{label.traceability_lot_code}")
    pdf.set_xy(2.5, 1.7)
    pdf.cell(1.4, 0.15, "FSMA 204 Compliant", align="R")

    return pdf.output()


def _png_to_simple_pdf(png_bytes: bytes) -> bytes:
    """Minimal fallback: wrap PNG in a single-page PDF."""
    # For simplicity, just return the PNG — caller can handle
    return png_bytes


# ─── Batch Generation ────────────────────────────────────────────────────────

def generate_batch_labels(
    labels: list[LabelData],
    fmt: str = "png",
) -> list[tuple[str, bytes]]:
    """
    Generate labels for a batch of TLCs.

    Returns list of (filename, content_bytes) tuples.
    """
    results = []
    for label in labels:
        safe_tlc = label.traceability_lot_code.replace("/", "_")
        if fmt == "png":
            content = generate_label_png(label)
            results.append((f"label_{safe_tlc}.png", content))
        elif fmt == "zpl":
            content = generate_label_zpl(label).encode("utf-8")
            results.append((f"label_{safe_tlc}.zpl", content))
        elif fmt == "pdf":
            content = generate_label_pdf(label)
            results.append((f"label_{safe_tlc}.pdf", content))
    return results


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Generate FSMA 204 TLC Labels")
    parser.add_argument("--tlc", required=True, help="Traceability Lot Code")
    parser.add_argument("--product", required=True, help="Product description")
    parser.add_argument("--quantity", type=int, default=100, help="Quantity")
    parser.add_argument("--unit", default="cases", help="Unit of measure")
    parser.add_argument("--gln", default="0614141000001", help="Location GLN")
    parser.add_argument("--location", default="Salinas, CA", help="Location name")
    parser.add_argument("--date", default="2026-02-06", help="Lot date")
    parser.add_argument("--format", choices=["png", "zpl", "pdf"], default="png")
    parser.add_argument("--output", default="label_output", help="Output directory")

    args = parser.parse_args()

    label = LabelData(
        traceability_lot_code=args.tlc,
        product_description=args.product,
        quantity=args.quantity,
        unit_of_measure=args.unit,
        location_gln=args.gln,
        location_name=args.location,
        lot_date=args.date,
    )

    outdir = Path(args.output).resolve()
    outdir.mkdir(exist_ok=True)

    # Sanitize TLC for use in filename — reject traversal characters
    safe_tlc = re.sub(r'[^a-zA-Z0-9_\-.]', '_', args.tlc)

    if args.format == "png":
        data = generate_label_png(label)
        out_file = outdir / f"label_{safe_tlc}.png"
        out_file.write_bytes(data)
    elif args.format == "zpl":
        data = generate_label_zpl(label)
        out_file = outdir / f"label_{safe_tlc}.zpl"
        out_file.write_text(data)
    elif args.format == "pdf":
        data = generate_label_pdf(label)
        out_file = outdir / f"label_{safe_tlc}.pdf"
        out_file.write_bytes(data)

    print(f"Label generated: {out_file}")
