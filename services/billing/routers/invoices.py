"""
Invoices Router — Invoice generation and payment history API.

Endpoints for creating, sending, and paying invoices,
plus aging reports and revenue summaries.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field
from typing import Optional

from invoice_engine import invoice_engine, InvoiceStatus, PaymentMethod
from utils import format_cents, paginate

router = APIRouter(prefix="/v1/billing/invoices", tags=["Invoices"])


# ── Request Models ─────────────────────────────────────────────────

class CreateInvoiceRequest(BaseModel):
    tenant_id: str
    tenant_name: str
    tier_id: str = "growth"
    overage_items: list[dict] = []
    discount_cents: int = Field(default=0, ge=0)
    notes: str = ""


class RecordPaymentRequest(BaseModel):
    amount_cents: int = Field(..., gt=0)
    method: PaymentMethod = PaymentMethod.CREDIT_CARD
    card_last4: str = "4242"
    card_brand: str = "visa"
    notes: str = ""


# ── Endpoints ──────────────────────────────────────────────────────

@router.post("")
async def create_invoice(request: CreateInvoiceRequest):
    """Generate a new invoice for a tenant."""
    invoice = invoice_engine.create_invoice(
        tenant_id=request.tenant_id,
        tenant_name=request.tenant_name,
        tier_id=request.tier_id,
        overage_items=request.overage_items,
        discount_cents=request.discount_cents,
        notes=request.notes,
    )
    return {
        "invoice": invoice.model_dump(),
        "message": f"Invoice {invoice.number} created: {format_cents(invoice.total_cents)}",
    }


@router.get("")
async def list_invoices(
    tenant_id: Optional[str] = Query(None),
    status: Optional[InvoiceStatus] = Query(None),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
):
    """List invoices with optional filters and pagination."""
    invoices = invoice_engine.list_invoices(tenant_id=tenant_id, status=status)
    result = paginate([i.model_dump() for i in invoices], page=page, page_size=page_size)
    return {
        "invoices": result["items"],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "total_pages": result["total_pages"],
        "has_next": result["has_next"],
        "has_prev": result["has_prev"],
    }


@router.get("/aging")
async def aging_report():
    """Accounts receivable aging report."""
    return invoice_engine.get_aging_report()


@router.get("/revenue-summary")
async def revenue_summary():
    """Revenue collection summary."""
    return invoice_engine.get_revenue_summary()


@router.get("/payments")
async def list_payments(tenant_id: Optional[str] = Query(None)):
    """Payment history."""
    payments = invoice_engine.list_payments(tenant_id=tenant_id)
    return {
        "payments": [p.model_dump() for p in payments],
        "total": len(payments),
    }


@router.get("/{invoice_id}")
async def get_invoice(invoice_id: str = Path(...)):
    """Get invoice details."""
    invoice = invoice_engine.get_invoice(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found")
    return {"invoice": invoice.model_dump()}


@router.post("/{invoice_id}/send")
async def send_invoice(invoice_id: str = Path(...)):
    """Mark invoice as sent to customer."""
    try:
        invoice = invoice_engine.send_invoice(invoice_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "invoice": invoice.model_dump(),
        "message": f"Invoice {invoice.number} sent",
    }


@router.post("/{invoice_id}/void")
async def void_invoice(invoice_id: str = Path(...)):
    """Void an invoice."""
    try:
        invoice = invoice_engine.void_invoice(invoice_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "invoice": invoice.model_dump(),
        "message": f"Invoice {invoice.number} voided",
    }


@router.post("/{invoice_id}/pay")
async def pay_invoice(
    request: RecordPaymentRequest,
    invoice_id: str = Path(...),
):
    """Record a payment against an invoice."""
    try:
        payment = invoice_engine.record_payment(
            invoice_id=invoice_id,
            amount_cents=request.amount_cents,
            method=request.method,
            card_last4=request.card_last4,
            card_brand=request.card_brand,
            notes=request.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    invoice = invoice_engine.get_invoice(invoice_id)
    return {
        "payment": payment.model_dump(),
        "invoice_status": invoice.status.value if invoice else "unknown",
        "amount_remaining_cents": invoice.amount_due_cents if invoice else 0,
        "message": f"Payment of {format_cents(request.amount_cents)} recorded",
    }
