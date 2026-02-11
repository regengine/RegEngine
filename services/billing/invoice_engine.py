"""
Billing Service — Invoice Generation & Payment History Engine

Handles automated invoice creation, payment recording, aging analysis,
and revenue recognition. In-memory store for sandbox mode.
"""

from __future__ import annotations

import structlog
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4
from enum import Enum
from pydantic import BaseModel, Field

from models import PRICING_TIERS, BillingCycle

logger = structlog.get_logger(__name__)


# ── Enums ──────────────────────────────────────────────────────────

class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"
    PARTIALLY_PAID = "partially_paid"


class PaymentMethod(str, Enum):
    CREDIT_CARD = "credit_card"
    ACH = "ach"
    WIRE = "wire"
    CHECK = "check"


class PaymentStatus(str, Enum):
    SUCCEEDED = "succeeded"
    PENDING = "pending"
    FAILED = "failed"
    REFUNDED = "refunded"


# ── Models ─────────────────────────────────────────────────────────

class InvoiceLineItem(BaseModel):
    description: str
    quantity: int = 1
    unit_price_cents: int = 0
    total_cents: int = 0
    category: str = "subscription"  # subscription | overage | credit | one_time


class Invoice(BaseModel):
    id: str = Field(default_factory=lambda: f"inv_{uuid4().hex[:12]}")
    number: str = ""
    tenant_id: str
    tenant_name: str = ""
    # Financial
    subtotal_cents: int = 0
    discount_cents: int = 0
    tax_cents: int = 0
    total_cents: int = 0
    amount_paid_cents: int = 0
    amount_due_cents: int = 0
    currency: str = "usd"
    # Line items
    line_items: list[InvoiceLineItem] = []
    # Status
    status: InvoiceStatus = InvoiceStatus.DRAFT
    # Dates
    issue_date: datetime = Field(default_factory=datetime.utcnow)
    due_date: Optional[datetime] = None
    paid_date: Optional[datetime] = None
    # Metadata
    billing_period_start: Optional[datetime] = None
    billing_period_end: Optional[datetime] = None
    notes: str = ""
    stripe_invoice_id: Optional[str] = None


class Payment(BaseModel):
    id: str = Field(default_factory=lambda: f"pay_{uuid4().hex[:12]}")
    invoice_id: str
    tenant_id: str
    tenant_name: str = ""
    amount_cents: int
    method: PaymentMethod = PaymentMethod.CREDIT_CARD
    status: PaymentStatus = PaymentStatus.SUCCEEDED
    # Card details (masked)
    card_last4: str = ""
    card_brand: str = ""
    # Metadata
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    stripe_payment_id: Optional[str] = None
    notes: str = ""


# ── Invoice Engine ─────────────────────────────────────────────────

class InvoiceEngine:
    """Invoice generation and payment ledger management."""

    def __init__(self):
        self._invoices: dict[str, Invoice] = {}
        self._payments: dict[str, Payment] = {}
        self._invoice_counter = 1000
        self._seed_demo_data()

    def _next_invoice_number(self) -> str:
        self._invoice_counter += 1
        return f"INV-2026-{self._invoice_counter:04d}"

    def _seed_demo_data(self):
        """Create realistic invoice and payment history."""
        now = datetime.utcnow()

        invoices_data = [
            # Acme Foods — 6 months of history
            {"tenant_id": "acme_foods", "tenant_name": "Acme Foods Inc.", "tier": "enterprise", "months_ago": 6, "status": InvoiceStatus.PAID, "overage_docs": 0},
            {"tenant_id": "acme_foods", "tenant_name": "Acme Foods Inc.", "tier": "enterprise", "months_ago": 5, "status": InvoiceStatus.PAID, "overage_docs": 1200},
            {"tenant_id": "acme_foods", "tenant_name": "Acme Foods Inc.", "tier": "enterprise", "months_ago": 4, "status": InvoiceStatus.PAID, "overage_docs": 800},
            {"tenant_id": "acme_foods", "tenant_name": "Acme Foods Inc.", "tier": "enterprise", "months_ago": 3, "status": InvoiceStatus.PAID, "overage_docs": 2400},
            {"tenant_id": "acme_foods", "tenant_name": "Acme Foods Inc.", "tier": "enterprise", "months_ago": 2, "status": InvoiceStatus.PAID, "overage_docs": 1600},
            {"tenant_id": "acme_foods", "tenant_name": "Acme Foods Inc.", "tier": "enterprise", "months_ago": 1, "status": InvoiceStatus.SENT, "overage_docs": 3200},
            # MedSecure
            {"tenant_id": "medsecure", "tenant_name": "MedSecure Health", "tier": "scale", "months_ago": 3, "status": InvoiceStatus.PAID, "overage_docs": 0},
            {"tenant_id": "medsecure", "tenant_name": "MedSecure Health", "tier": "scale", "months_ago": 2, "status": InvoiceStatus.PAID, "overage_docs": 5600},
            {"tenant_id": "medsecure", "tenant_name": "MedSecure Health", "tier": "scale", "months_ago": 1, "status": InvoiceStatus.OVERDUE, "overage_docs": 8200},
            # SafetyFirst
            {"tenant_id": "safetyfirst", "tenant_name": "SafetyFirst Manufacturing", "tier": "growth", "months_ago": 2, "status": InvoiceStatus.PAID, "overage_docs": 0},
            {"tenant_id": "safetyfirst", "tenant_name": "SafetyFirst Manufacturing", "tier": "growth", "months_ago": 1, "status": InvoiceStatus.SENT, "overage_docs": 500},
        ]

        card_brands = ["visa", "mastercard", "amex"]
        card_last4s = ["4242", "8888", "3782"]

        for i, inv_data in enumerate(invoices_data):
            tier = PRICING_TIERS.get(inv_data["tier"])
            monthly_price = (tier.annual_price or tier.monthly_price or 5000) * 100 if tier else 500_000
            months_ago = inv_data["months_ago"]

            # Build line items
            line_items = [
                InvoiceLineItem(
                    description=f"{(tier.name if tier else 'Enterprise')} Plan — Monthly",
                    quantity=1,
                    unit_price_cents=monthly_price,
                    total_cents=monthly_price,
                    category="subscription",
                )
            ]

            overage_cents = 0
            if inv_data["overage_docs"] > 0:
                overage_cents = inv_data["overage_docs"] * 10  # $0.10/doc
                line_items.append(
                    InvoiceLineItem(
                        description=f"Document processing overage ({inv_data['overage_docs']:,} docs)",
                        quantity=inv_data["overage_docs"],
                        unit_price_cents=10,
                        total_cents=overage_cents,
                        category="overage",
                    )
                )

            subtotal = monthly_price + overage_cents
            tax = int(subtotal * 0.0875)  # 8.75% tax
            total = subtotal + tax

            issue_date = now - timedelta(days=30 * months_ago)
            due_date = issue_date + timedelta(days=30)

            invoice = Invoice(
                id=f"inv_seed_{i:04d}",
                number=self._next_invoice_number(),
                tenant_id=inv_data["tenant_id"],
                tenant_name=inv_data["tenant_name"],
                subtotal_cents=subtotal,
                tax_cents=tax,
                total_cents=total,
                amount_paid_cents=total if inv_data["status"] == InvoiceStatus.PAID else 0,
                amount_due_cents=0 if inv_data["status"] == InvoiceStatus.PAID else total,
                line_items=line_items,
                status=inv_data["status"],
                issue_date=issue_date,
                due_date=due_date,
                paid_date=issue_date + timedelta(days=12) if inv_data["status"] == InvoiceStatus.PAID else None,
                billing_period_start=issue_date,
                billing_period_end=issue_date + timedelta(days=30),
            )
            self._invoices[invoice.id] = invoice

            # Create payment record for paid invoices
            if inv_data["status"] == InvoiceStatus.PAID:
                payment = Payment(
                    id=f"pay_seed_{i:04d}",
                    invoice_id=invoice.id,
                    tenant_id=inv_data["tenant_id"],
                    tenant_name=inv_data["tenant_name"],
                    amount_cents=total,
                    method=PaymentMethod.CREDIT_CARD,
                    status=PaymentStatus.SUCCEEDED,
                    card_last4=card_last4s[i % 3],
                    card_brand=card_brands[i % 3],
                    processed_at=invoice.paid_date or issue_date + timedelta(days=12),
                    stripe_payment_id=f"pi_sandbox_{uuid4().hex[:12]}",
                )
                self._payments[payment.id] = payment

    # ── Invoice CRUD ───────────────────────────────────────────

    def create_invoice(self, tenant_id: str, tenant_name: str, tier_id: str,
                       overage_items: list[dict] | None = None,
                       discount_cents: int = 0, notes: str = "") -> Invoice:
        """Generate a new invoice for a tenant."""
        tier = PRICING_TIERS.get(tier_id)
        monthly_price = (tier.annual_price or tier.monthly_price or 5000) * 100 if tier else 500_000

        line_items = [
            InvoiceLineItem(
                description=f"{(tier.name if tier else 'Enterprise')} Plan — Monthly",
                quantity=1,
                unit_price_cents=monthly_price,
                total_cents=monthly_price,
                category="subscription",
            )
        ]

        overage_total = 0
        for item in (overage_items or []):
            item_total = item.get("quantity", 0) * item.get("unit_price_cents", 10)
            overage_total += item_total
            line_items.append(InvoiceLineItem(
                description=item.get("description", "Overage"),
                quantity=item.get("quantity", 0),
                unit_price_cents=item.get("unit_price_cents", 10),
                total_cents=item_total,
                category="overage",
            ))

        subtotal = monthly_price + overage_total
        tax = int(subtotal * 0.0875)
        total = subtotal + tax - discount_cents

        now = datetime.utcnow()
        invoice = Invoice(
            number=self._next_invoice_number(),
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            subtotal_cents=subtotal,
            discount_cents=discount_cents,
            tax_cents=tax,
            total_cents=total,
            amount_due_cents=total,
            line_items=line_items,
            status=InvoiceStatus.DRAFT,
            issue_date=now,
            due_date=now + timedelta(days=30),
            billing_period_start=now,
            billing_period_end=now + timedelta(days=30),
            notes=notes,
        )
        self._invoices[invoice.id] = invoice
        logger.info("invoice_created", invoice_id=invoice.id, number=invoice.number, total=total)
        return invoice

    def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        return self._invoices.get(invoice_id)

    def list_invoices(self, tenant_id: str | None = None,
                      status: InvoiceStatus | None = None) -> list[Invoice]:
        invoices = list(self._invoices.values())
        if tenant_id:
            invoices = [i for i in invoices if i.tenant_id == tenant_id]
        if status:
            invoices = [i for i in invoices if i.status == status]
        return sorted(invoices, key=lambda i: i.issue_date, reverse=True)

    def send_invoice(self, invoice_id: str) -> Invoice:
        """Mark invoice as sent."""
        invoice = self._invoices.get(invoice_id)
        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")
        if invoice.status != InvoiceStatus.DRAFT:
            raise ValueError(f"Can only send draft invoices, current: {invoice.status.value}")
        invoice.status = InvoiceStatus.SENT
        logger.info("invoice_sent", invoice_id=invoice_id)
        return invoice

    def void_invoice(self, invoice_id: str) -> Invoice:
        """Void an invoice."""
        invoice = self._invoices.get(invoice_id)
        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")
        if invoice.status == InvoiceStatus.PAID:
            raise ValueError("Cannot void a paid invoice")
        invoice.status = InvoiceStatus.VOID
        invoice.amount_due_cents = 0
        logger.info("invoice_voided", invoice_id=invoice_id)
        return invoice

    # ── Payment Recording ──────────────────────────────────────

    def record_payment(self, invoice_id: str, amount_cents: int,
                       method: PaymentMethod = PaymentMethod.CREDIT_CARD,
                       card_last4: str = "4242", card_brand: str = "visa",
                       notes: str = "") -> Payment:
        """Record a payment against an invoice."""
        invoice = self._invoices.get(invoice_id)
        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")
        if invoice.status in (InvoiceStatus.VOID, InvoiceStatus.PAID):
            raise ValueError(f"Cannot pay a {invoice.status.value} invoice")

        payment = Payment(
            invoice_id=invoice_id,
            tenant_id=invoice.tenant_id,
            tenant_name=invoice.tenant_name,
            amount_cents=amount_cents,
            method=method,
            status=PaymentStatus.SUCCEEDED,
            card_last4=card_last4,
            card_brand=card_brand,
            notes=notes,
        )
        self._payments[payment.id] = payment

        invoice.amount_paid_cents += amount_cents
        invoice.amount_due_cents = max(0, invoice.total_cents - invoice.amount_paid_cents)

        if invoice.amount_due_cents == 0:
            invoice.status = InvoiceStatus.PAID
            invoice.paid_date = datetime.utcnow()
        else:
            invoice.status = InvoiceStatus.PARTIALLY_PAID

        logger.info("payment_recorded", payment_id=payment.id, invoice_id=invoice_id, amount=amount_cents)
        return payment

    def list_payments(self, tenant_id: str | None = None) -> list[Payment]:
        payments = list(self._payments.values())
        if tenant_id:
            payments = [p for p in payments if p.tenant_id == tenant_id]
        return sorted(payments, key=lambda p: p.processed_at, reverse=True)

    # ── Aging Report ───────────────────────────────────────────

    def get_aging_report(self) -> dict:
        """Accounts receivable aging report."""
        now = datetime.utcnow()
        buckets = {"current": 0, "1_30": 0, "31_60": 0, "61_90": 0, "90_plus": 0}
        bucket_invoices: dict[str, list] = {k: [] for k in buckets}

        for invoice in self._invoices.values():
            if invoice.status in (InvoiceStatus.PAID, InvoiceStatus.VOID, InvoiceStatus.DRAFT):
                continue

            days_outstanding = (now - invoice.issue_date).days
            amount = invoice.amount_due_cents

            if days_outstanding <= 0:
                bucket = "current"
            elif days_outstanding <= 30:
                bucket = "1_30"
            elif days_outstanding <= 60:
                bucket = "31_60"
            elif days_outstanding <= 90:
                bucket = "61_90"
            else:
                bucket = "90_plus"

            buckets[bucket] += amount
            bucket_invoices[bucket].append({
                "invoice_id": invoice.id,
                "number": invoice.number,
                "tenant_name": invoice.tenant_name,
                "amount_due_cents": amount,
                "amount_due_display": f"${amount / 100:,.2f}",
                "days_outstanding": days_outstanding,
            })

        total_outstanding = sum(buckets.values())
        return {
            "aging_buckets": {
                k: {"amount_cents": v, "amount_display": f"${v / 100:,.2f}",
                     "invoice_count": len(bucket_invoices[k]),
                     "invoices": bucket_invoices[k]}
                for k, v in buckets.items()
            },
            "total_outstanding_cents": total_outstanding,
            "total_outstanding_display": f"${total_outstanding / 100:,.2f}",
            "overdue_count": sum(1 for i in self._invoices.values()
                                if i.status == InvoiceStatus.OVERDUE),
        }

    # ── Revenue Summary ────────────────────────────────────────

    def get_revenue_summary(self) -> dict:
        """Revenue collected, outstanding, and trends."""
        total_collected = sum(p.amount_cents for p in self._payments.values()
                             if p.status == PaymentStatus.SUCCEEDED)
        total_invoiced = sum(i.total_cents for i in self._invoices.values()
                            if i.status != InvoiceStatus.VOID)
        total_outstanding = sum(i.amount_due_cents for i in self._invoices.values()
                               if i.status in (InvoiceStatus.SENT, InvoiceStatus.OVERDUE, InvoiceStatus.PARTIALLY_PAID))

        paid_count = sum(1 for i in self._invoices.values() if i.status == InvoiceStatus.PAID)
        total_count = sum(1 for i in self._invoices.values() if i.status != InvoiceStatus.VOID)
        collection_rate = round(paid_count / max(total_count, 1) * 100, 1)

        return {
            "total_collected_cents": total_collected,
            "total_collected_display": f"${total_collected / 100:,.2f}",
            "total_invoiced_cents": total_invoiced,
            "total_invoiced_display": f"${total_invoiced / 100:,.2f}",
            "total_outstanding_cents": total_outstanding,
            "total_outstanding_display": f"${total_outstanding / 100:,.2f}",
            "collection_rate_pct": collection_rate,
            "invoices_paid": paid_count,
            "invoices_total": total_count,
            "payments_count": len(self._payments),
        }


# Singleton
invoice_engine = InvoiceEngine()
