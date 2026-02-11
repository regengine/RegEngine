"""
Tax Engine & API Tests

Tests tax calculation, jurisdictions, exemptions,
reporting, and API endpoints.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app
from tax_engine import TaxEngine, TaxType, ExemptionReason, JURISDICTIONS

client = TestClient(app)


# ── Engine Unit Tests ──────────────────────────────────────────────

class TestTaxCalculation:
    def test_california_sales_tax(self):
        engine = TaxEngine()
        result = engine.calculate_tax("new_tenant", "us_ca", 100_000)
        assert result.tax_rate == 0.0875
        assert result.tax_amount_cents == 8_750
        assert result.total_cents == 108_750

    def test_new_york_tax(self):
        engine = TaxEngine()
        result = engine.calculate_tax("new_tenant", "us_ny", 200_000)
        assert result.tax_rate == 0.08
        assert result.tax_amount_cents == 16_000

    def test_uk_vat(self):
        engine = TaxEngine()
        result = engine.calculate_tax("new_tenant", "gb", 100_000)
        assert result.tax_type == TaxType.VAT
        assert result.tax_rate == 0.20
        assert result.tax_amount_cents == 20_000

    def test_oregon_exempt(self):
        engine = TaxEngine()
        result = engine.calculate_tax("new_tenant", "us_or", 100_000)
        assert result.tax_rate == 0.0
        assert result.tax_amount_cents == 0
        assert result.total_cents == 100_000

    def test_unknown_jurisdiction(self):
        engine = TaxEngine()
        with pytest.raises(ValueError, match="Unknown jurisdiction"):
            engine.calculate_tax("t1", "us_zz", 100_000)

    def test_exemption_applied(self):
        engine = TaxEngine()
        # medsecure has CA healthcare exemption
        result = engine.calculate_tax("medsecure", "us_ca", 100_000)
        assert result.is_exempt is True
        assert result.tax_amount_cents == 0

    def test_no_exemption_same_jurisdiction(self):
        engine = TaxEngine()
        # medsecure has no TX exemption
        result = engine.calculate_tax("medsecure", "us_tx", 100_000)
        assert result.is_exempt is False
        assert result.tax_amount_cents > 0


class TestJurisdictions:
    def test_list_all(self):
        engine = TaxEngine()
        jurs = engine.list_jurisdictions()
        assert len(jurs) == 12

    def test_filter_by_country(self):
        engine = TaxEngine()
        us = engine.list_jurisdictions(country="US")
        assert all(j.country == "US" for j in us)
        assert len(us) == 7

    def test_canada(self):
        engine = TaxEngine()
        ca = engine.list_jurisdictions(country="CA")
        assert len(ca) == 2


class TestExemptions:
    def test_add_exemption(self):
        engine = TaxEngine()
        ex = engine.add_exemption("t1", "Test Corp", "us_ca", ExemptionReason.NONPROFIT, "NP-001")
        assert ex.tenant_id == "t1"
        assert ex.verified is False

    def test_verify_exemption(self):
        engine = TaxEngine()
        ex = engine.add_exemption("t1", "Test Corp", "us_ca", ExemptionReason.NONPROFIT)
        verified = engine.verify_exemption(ex.id)
        assert verified.verified is True

    def test_verify_not_found(self):
        engine = TaxEngine()
        with pytest.raises(ValueError, match="not found"):
            engine.verify_exemption("txe_nope")

    def test_list_exemptions(self):
        engine = TaxEngine()
        exemptions = engine.list_exemptions()
        assert len(exemptions) >= 3

    def test_list_by_tenant(self):
        engine = TaxEngine()
        exemptions = engine.list_exemptions(tenant_id="acme_foods")
        assert len(exemptions) >= 1

    def test_invalid_jurisdiction(self):
        engine = TaxEngine()
        with pytest.raises(ValueError, match="Unknown"):
            engine.add_exemption("t1", "Test", "us_zz", ExemptionReason.NONPROFIT)


class TestTaxReport:
    def test_full_report(self):
        engine = TaxEngine()
        report = engine.get_tax_report()
        assert report["total_tax_cents"] > 0
        assert len(report["jurisdictions"]) >= 2

    def test_period_filter(self):
        engine = TaxEngine()
        report = engine.get_tax_report(period="2026-01")
        assert report["period"] == "2026-01"


# ── API Endpoint Tests ─────────────────────────────────────────────

class TestTaxAPI:
    def test_calculate(self):
        response = client.post("/v1/billing/tax/calculate", json={
            "tenant_id": "api_test", "jurisdiction_id": "us_ca", "subtotal_cents": 100_000,
        })
        assert response.status_code == 200
        assert response.json()["calculation"]["tax_amount_cents"] == 8_750

    def test_calculate_invalid_jurisdiction(self):
        response = client.post("/v1/billing/tax/calculate", json={
            "tenant_id": "t1", "jurisdiction_id": "us_zz", "subtotal_cents": 100_000,
        })
        assert response.status_code == 400

    def test_list_jurisdictions(self):
        response = client.get("/v1/billing/tax/jurisdictions")
        assert response.status_code == 200
        assert response.json()["total"] == 12

    def test_list_us_jurisdictions(self):
        response = client.get("/v1/billing/tax/jurisdictions?country=US")
        assert response.status_code == 200
        assert response.json()["total"] == 7

    def test_list_exemptions(self):
        response = client.get("/v1/billing/tax/exemptions")
        assert response.status_code == 200
        assert response.json()["total"] >= 3

    def test_add_exemption(self):
        response = client.post("/v1/billing/tax/exemptions", json={
            "tenant_id": "api_test", "tenant_name": "API Test",
            "jurisdiction_id": "us_fl", "reason": "education",
        })
        assert response.status_code == 200
        assert response.json()["exemption"]["verified"] is False

    def test_verify_exemption(self):
        create = client.post("/v1/billing/tax/exemptions", json={
            "tenant_id": "verify_test", "tenant_name": "Verify Test",
            "jurisdiction_id": "us_tx", "reason": "government",
        })
        ex_id = create.json()["exemption"]["id"]
        response = client.post(f"/v1/billing/tax/exemptions/{ex_id}/verify")
        assert response.status_code == 200
        assert response.json()["exemption"]["verified"] is True

    def test_tax_report(self):
        response = client.get("/v1/billing/tax/report")
        assert response.status_code == 200
        assert response.json()["total_tax_cents"] > 0

    def test_tax_report_period(self):
        response = client.get("/v1/billing/tax/report?period=2026-01")
        assert response.status_code == 200
        assert response.json()["period"] == "2026-01"
