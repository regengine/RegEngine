"""
Invoice Engine & API Tests

Tests invoice creation, payment recording, aging reports,
revenue summaries, and API endpoints.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app
from invoice_engine import InvoiceEngine, InvoiceStatus, PaymentMethod

client = TestClient(app)


# ── Engine Unit Tests ──────────────────────────────────────────────

class TestInvoiceCreation:
    def test_create_basic(self):
        engine = InvoiceEngine()
        invoice = engine.create_invoice("t1", "Test Corp", "growth")
        assert invoice.tenant_id == "t1"
        assert invoice.status == InvoiceStatus.DRAFT
        assert invoice.total_cents > 0
        assert invoice.number.startswith("INV-2026-")
        assert len(invoice.line_items) == 1

    def test_create_with_overage(self):
        engine = InvoiceEngine()
        invoice = engine.create_invoice("t1", "Test Corp", "growth", overage_items=[
            {"description": "API overage", "quantity": 1000, "unit_price_cents": 5},
        ])
        assert len(invoice.line_items) == 2
        assert invoice.line_items[1].category == "overage"
        assert invoice.subtotal_cents > invoice.line_items[0].total_cents

    def test_create_with_discount(self):
        engine = InvoiceEngine()
        invoice = engine.create_invoice("t1", "Test Corp", "growth", discount_cents=5000)
        assert invoice.discount_cents == 5000

    def test_list_invoices(self):
        engine = InvoiceEngine()
        invoices = engine.list_invoices()
        assert len(invoices) >= 11  # seed data

    def test_list_by_tenant(self):
        engine = InvoiceEngine()
        invoices = engine.list_invoices(tenant_id="acme_foods")
        assert len(invoices) == 6
        for i in invoices:
            assert i.tenant_id == "acme_foods"

    def test_list_by_status(self):
        engine = InvoiceEngine()
        paid = engine.list_invoices(status=InvoiceStatus.PAID)
        for i in paid:
            assert i.status == InvoiceStatus.PAID


class TestInvoiceWorkflow:
    def test_send_draft(self):
        engine = InvoiceEngine()
        invoice = engine.create_invoice("t1", "Test", "growth")
        sent = engine.send_invoice(invoice.id)
        assert sent.status == InvoiceStatus.SENT

    def test_cannot_send_non_draft(self):
        engine = InvoiceEngine()
        invoice = engine.create_invoice("t1", "Test", "growth")
        engine.send_invoice(invoice.id)
        with pytest.raises(ValueError, match="draft"):
            engine.send_invoice(invoice.id)

    def test_void_invoice(self):
        engine = InvoiceEngine()
        invoice = engine.create_invoice("t1", "Test", "growth")
        voided = engine.void_invoice(invoice.id)
        assert voided.status == InvoiceStatus.VOID
        assert voided.amount_due_cents == 0

    def test_cannot_void_paid(self):
        engine = InvoiceEngine()
        invoice = engine.create_invoice("t1", "Test", "growth")
        engine.send_invoice(invoice.id)
        engine.record_payment(invoice.id, invoice.total_cents)
        with pytest.raises(ValueError, match="paid"):
            engine.void_invoice(invoice.id)

    def test_invoice_not_found(self):
        engine = InvoiceEngine()
        with pytest.raises(ValueError, match="not found"):
            engine.send_invoice("inv_nonexistent")


class TestPaymentRecording:
    def test_full_payment(self):
        engine = InvoiceEngine()
        invoice = engine.create_invoice("t1", "Test", "growth")
        engine.send_invoice(invoice.id)
        payment = engine.record_payment(invoice.id, invoice.total_cents)
        assert payment.status.value == "succeeded"
        assert invoice.status == InvoiceStatus.PAID
        assert invoice.amount_due_cents == 0

    def test_partial_payment(self):
        engine = InvoiceEngine()
        invoice = engine.create_invoice("t1", "Test", "growth")
        engine.send_invoice(invoice.id)
        engine.record_payment(invoice.id, 1000)
        assert invoice.status == InvoiceStatus.PARTIALLY_PAID
        assert invoice.amount_due_cents > 0

    def test_cannot_pay_void(self):
        engine = InvoiceEngine()
        invoice = engine.create_invoice("t1", "Test", "growth")
        engine.void_invoice(invoice.id)
        with pytest.raises(ValueError, match="void"):
            engine.record_payment(invoice.id, 1000)

    def test_list_payments(self):
        engine = InvoiceEngine()
        payments = engine.list_payments()
        assert len(payments) >= 8  # seed data


class TestReports:
    def test_aging_report(self):
        engine = InvoiceEngine()
        report = engine.get_aging_report()
        assert "aging_buckets" in report
        assert "total_outstanding_cents" in report
        assert report["total_outstanding_cents"] >= 0

    def test_revenue_summary(self):
        engine = InvoiceEngine()
        summary = engine.get_revenue_summary()
        assert summary["total_collected_cents"] > 0
        assert summary["total_invoiced_cents"] > 0
        assert summary["collection_rate_pct"] > 0


# ── API Endpoint Tests ─────────────────────────────────────────────

class TestInvoicesAPI:
    def test_create_invoice(self):
        response = client.post("/v1/billing/invoices", json={
            "tenant_id": "api_test",
            "tenant_name": "API Test Corp",
            "tier_id": "growth",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["invoice"]["status"] == "draft"

    def test_list_invoices(self):
        response = client.get("/v1/billing/invoices")
        assert response.status_code == 200
        assert response.json()["total"] >= 11

    def test_get_invoice(self):
        response = client.get("/v1/billing/invoices/inv_seed_0000")
        assert response.status_code == 200

    def test_get_not_found(self):
        response = client.get("/v1/billing/invoices/inv_nope")
        assert response.status_code == 404

    def test_send_invoice(self):
        create = client.post("/v1/billing/invoices", json={
            "tenant_id": "send_test", "tenant_name": "Send Test", "tier_id": "growth"
        })
        inv_id = create.json()["invoice"]["id"]
        response = client.post(f"/v1/billing/invoices/{inv_id}/send")
        assert response.status_code == 200
        assert response.json()["invoice"]["status"] == "sent"

    def test_void_invoice(self):
        create = client.post("/v1/billing/invoices", json={
            "tenant_id": "void_test", "tenant_name": "Void Test", "tier_id": "growth"
        })
        inv_id = create.json()["invoice"]["id"]
        response = client.post(f"/v1/billing/invoices/{inv_id}/void")
        assert response.status_code == 200
        assert response.json()["invoice"]["status"] == "void"

    def test_pay_invoice(self):
        create = client.post("/v1/billing/invoices", json={
            "tenant_id": "pay_test", "tenant_name": "Pay Test", "tier_id": "starter"
        })
        inv_id = create.json()["invoice"]["id"]
        total = create.json()["invoice"]["total_cents"]
        client.post(f"/v1/billing/invoices/{inv_id}/send")
        response = client.post(f"/v1/billing/invoices/{inv_id}/pay", json={
            "amount_cents": total,
        })
        assert response.status_code == 200
        assert response.json()["invoice_status"] == "paid"

    def test_aging_report(self):
        response = client.get("/v1/billing/invoices/aging")
        assert response.status_code == 200
        assert "aging_buckets" in response.json()

    def test_revenue_summary(self):
        response = client.get("/v1/billing/invoices/revenue-summary")
        assert response.status_code == 200
        assert response.json()["total_collected_cents"] > 0

    def test_payments_list(self):
        response = client.get("/v1/billing/invoices/payments")
        assert response.status_code == 200
        assert response.json()["total"] >= 8
