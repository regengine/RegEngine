"""
Contract Engine & API Tests

Tests deal lifecycle, quote generation, SLA tracking,
pipeline summaries, and API endpoints.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app
from contract_engine import ContractEngine, DealStage, ContractType, DISCOUNT_RULES

client = TestClient(app)


# ── Engine Unit Tests ──────────────────────────────────────────────

class TestContractCreation:
    """Test creating contracts."""

    def test_create_basic(self):
        engine = ContractEngine()
        contract = engine.create_contract("t1", "Test Corp", "growth")
        assert contract.tenant_id == "t1"
        assert contract.tenant_name == "Test Corp"
        assert contract.stage == DealStage.DRAFT
        assert contract.tier_id == "growth"

    def test_create_enterprise(self):
        engine = ContractEngine()
        contract = engine.create_contract(
            "t2", "Big Co", "enterprise",
            contract_type=ContractType.ENTERPRISE,
            term_years=3,
            notes="Strategic deal"
        )
        assert contract.contract_type == ContractType.ENTERPRISE
        assert contract.term_years == 3
        assert contract.sla.uptime_pct == 99.99
        assert contract.annual_contract_value_cents > 0

    def test_list_contracts(self):
        engine = ContractEngine()
        contracts = engine.list_contracts()
        assert len(contracts) >= 6  # seed data


class TestDealStageTransitions:
    """Test deal pipeline progression."""

    def test_valid_transition(self):
        engine = ContractEngine()
        contract = engine.create_contract("t1", "Test", "growth")
        updated = engine.advance_stage(contract.id, DealStage.PROPOSED)
        assert updated.stage == DealStage.PROPOSED

    def test_full_pipeline(self):
        engine = ContractEngine()
        contract = engine.create_contract("t1", "Test", "growth")
        engine.advance_stage(contract.id, DealStage.PROPOSED)
        engine.advance_stage(contract.id, DealStage.NEGOTIATING)
        engine.advance_stage(contract.id, DealStage.APPROVED)
        engine.advance_stage(contract.id, DealStage.ACTIVE)
        assert contract.stage == DealStage.ACTIVE
        assert contract.start_date is not None
        assert contract.end_date is not None

    def test_invalid_transition_raises(self):
        engine = ContractEngine()
        contract = engine.create_contract("t1", "Test", "growth")
        with pytest.raises(ValueError, match="Cannot transition"):
            engine.advance_stage(contract.id, DealStage.ACTIVE)

    def test_churn_from_any_stage(self):
        engine = ContractEngine()
        contract = engine.create_contract("t1", "Test", "growth")
        updated = engine.advance_stage(contract.id, DealStage.CHURNED)
        assert updated.stage == DealStage.CHURNED

    def test_contract_not_found(self):
        engine = ContractEngine()
        with pytest.raises(ValueError, match="not found"):
            engine.advance_stage("ctr_nonexistent", DealStage.PROPOSED)


class TestQuoteGeneration:
    """Test quote creation and discount modeling."""

    def test_basic_quote(self):
        engine = ContractEngine()
        contract = engine.create_contract("t1", "Test", "enterprise")
        quote = engine.generate_quote(contract.id)
        assert quote.base_price_cents > 0
        assert quote.final_annual_cents > 0
        assert quote.total_contract_value_cents > 0

    def test_multi_year_discount(self):
        engine = ContractEngine()
        contract = engine.create_contract("t1", "Test", "enterprise", term_years=2)
        quote = engine.generate_quote(contract.id)
        assert quote.total_discount_pct == 0.10  # 2-year = 10%
        assert len(quote.discounts) == 1

    def test_three_year_discount(self):
        engine = ContractEngine()
        contract = engine.create_contract("t1", "Test", "enterprise", term_years=3)
        quote = engine.generate_quote(contract.id)
        assert quote.total_discount_pct == 0.18  # 3-year = 18%

    def test_stacked_discounts(self):
        engine = ContractEngine()
        contract = engine.create_contract("t1", "Test", "enterprise", term_years=2)
        quote = engine.generate_quote(contract.id, discount_codes=["partner_channel"])
        # 10% multi-year + 8% partner = 18%
        assert quote.total_discount_pct == 0.18
        assert len(quote.discounts) == 2

    def test_discount_cap_at_35(self):
        engine = ContractEngine()
        contract = engine.create_contract("t1", "Test", "enterprise", term_years=3)
        quote = engine.generate_quote(
            contract.id,
            discount_codes=["volume_100", "partner_channel"],
            custom_discount_pct=0.10,
        )
        # 18% + 20% + 8% + 10% = 56% → capped at 35%
        assert quote.total_discount_pct == 0.35

    def test_quote_updates_contract_value(self):
        engine = ContractEngine()
        contract = engine.create_contract("t1", "Test", "enterprise")
        quote = engine.generate_quote(contract.id)
        assert contract.annual_contract_value_cents == quote.final_annual_cents
        assert len(contract.quotes) == 1

    def test_quote_not_found(self):
        engine = ContractEngine()
        with pytest.raises(ValueError, match="not found"):
            engine.generate_quote("ctr_nonexistent")


class TestPipeline:
    """Test pipeline summary."""

    def test_pipeline_stages(self):
        engine = ContractEngine()
        pipeline = engine.get_pipeline()
        assert "pipeline" in pipeline
        assert "draft" in pipeline["pipeline"]
        assert "active" in pipeline["pipeline"]
        assert pipeline["total_pipeline_value_cents"] > 0

    def test_weighted_pipeline(self):
        engine = ContractEngine()
        pipeline = engine.get_pipeline()
        assert pipeline["weighted_pipeline_cents"] == int(
            pipeline["total_pipeline_value_cents"] * 0.35
        )


class TestSLAStatus:
    """Test SLA compliance tracking."""

    def test_active_contracts_have_sla(self):
        engine = ContractEngine()
        statuses = engine.get_sla_status()
        assert len(statuses) >= 2  # acme_foods + medsecure
        for status in statuses:
            assert "compliance" in status
            assert status["uptime_actual"] > 0

    def test_sla_fields(self):
        engine = ContractEngine()
        statuses = engine.get_sla_status()
        status = statuses[0]
        assert "sla_level" in status
        assert "uptime_target" in status
        assert "response_target_hours" in status
        assert "breaches" in status


class TestRenewals:
    """Test renewal forecasting."""

    def test_upcoming_renewals(self):
        engine = ContractEngine()
        renewals = engine.get_upcoming_renewals(days_ahead=1000)
        assert isinstance(renewals, list)
        for r in renewals:
            assert "days_until_renewal" in r
            assert "urgency" in r
            assert "acv_display" in r

    def test_renewals_sorted_by_date(self):
        engine = ContractEngine()
        renewals = engine.get_upcoming_renewals(days_ahead=1000)
        if len(renewals) >= 2:
            assert renewals[0]["days_until_renewal"] <= renewals[-1]["days_until_renewal"]


# ── API Endpoint Tests ─────────────────────────────────────────────

class TestContractsAPI:
    """Test contracts router endpoints."""

    def test_create_contract(self):
        response = client.post("/v1/billing/contracts", json={
            "tenant_id": "api_test",
            "tenant_name": "API Test Corp",
            "tier_id": "scale",
            "term_years": 2,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["contract"]["tenant_name"] == "API Test Corp"
        assert data["contract"]["stage"] == "draft"

    def test_list_contracts(self):
        response = client.get("/v1/billing/contracts")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 6

    def test_list_by_stage(self):
        response = client.get("/v1/billing/contracts?stage=active")
        assert response.status_code == 200
        data = response.json()
        for c in data["contracts"]:
            assert c["stage"] == "active"

    def test_get_contract(self):
        response = client.get("/v1/billing/contracts/ctr_acme001")
        assert response.status_code == 200
        data = response.json()
        assert data["contract"]["tenant_name"] == "Acme Foods Inc."

    def test_get_contract_not_found(self):
        response = client.get("/v1/billing/contracts/ctr_nonexistent")
        assert response.status_code == 404

    def test_advance_stage(self):
        # First create a contract
        create_resp = client.post("/v1/billing/contracts", json={
            "tenant_id": "stage_test",
            "tenant_name": "Stage Test",
            "tier_id": "growth",
        })
        contract_id = create_resp.json()["contract"]["id"]

        response = client.patch(
            f"/v1/billing/contracts/{contract_id}/stage",
            json={"new_stage": "proposed"},
        )
        assert response.status_code == 200
        assert response.json()["contract"]["stage"] == "proposed"

    def test_invalid_stage_transition(self):
        create_resp = client.post("/v1/billing/contracts", json={
            "tenant_id": "bad_stage",
            "tenant_name": "Bad Stage Test",
            "tier_id": "growth",
        })
        contract_id = create_resp.json()["contract"]["id"]

        response = client.patch(
            f"/v1/billing/contracts/{contract_id}/stage",
            json={"new_stage": "active"},
        )
        assert response.status_code == 400

    def test_generate_quote(self):
        response = client.post(
            "/v1/billing/contracts/ctr_acme001/quote",
            json={"discount_codes": ["partner_channel"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["quote"]["total_contract_value_cents"] > 0
        assert data["quote"]["total_discount_pct"] > 0

    def test_pipeline(self):
        response = client.get("/v1/billing/contracts/pipeline")
        assert response.status_code == 200
        data = response.json()
        assert "pipeline" in data
        assert data["total_pipeline_value_cents"] > 0

    def test_sla_status(self):
        response = client.get("/v1/billing/contracts/sla-status")
        assert response.status_code == 200
        data = response.json()
        assert "statuses" in data
        assert data["summary"]["total"] >= 2

    def test_renewals(self):
        response = client.get("/v1/billing/contracts/renewals?days=365")
        assert response.status_code == 200
        data = response.json()
        assert "renewals" in data
        assert "total_acv_at_risk_display" in data
