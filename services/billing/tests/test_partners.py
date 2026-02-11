"""
Partner Engine & API Tests

Tests partner registration, referral tracking, commissions,
auto-tier upgrades, payouts, and API endpoints.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app
from partner_engine import PartnerEngine, PartnerTier, PartnerStatus

client = TestClient(app)


# ── Engine Unit Tests ──────────────────────────────────────────────

class TestPartnerRegistration:
    def test_register_silver(self):
        engine = PartnerEngine()
        partner = engine.register_partner("John", "TestCo", "john@test.com")
        assert partner.tier == PartnerTier.SILVER
        assert partner.commission_rate == 0.10
        assert partner.referral_code != ""

    def test_register_gold(self):
        engine = PartnerEngine()
        partner = engine.register_partner("Jane", "GoldCo", "jane@gold.com", tier=PartnerTier.GOLD)
        assert partner.tier == PartnerTier.GOLD
        assert partner.commission_rate == 0.15

    def test_list_partners(self):
        engine = PartnerEngine()
        partners = engine.list_partners()
        assert len(partners) >= 4

    def test_list_by_tier(self):
        engine = PartnerEngine()
        plat = engine.list_partners(tier=PartnerTier.PLATINUM)
        for p in plat:
            assert p.tier == PartnerTier.PLATINUM

    def test_get_partner(self):
        engine = PartnerEngine()
        partner = engine.get_partner("ptr_compliance01")
        assert partner is not None
        assert partner.company == "CompliancePro Consulting"


class TestReferrals:
    def test_record_referral(self):
        engine = PartnerEngine()
        partner = engine.register_partner("Test", "RefCo", "test@ref.com")
        referral = engine.record_referral(
            partner.id, "new_tenant", "New Tenant", "growth", 80_000
        )
        assert referral.commission_cents == 8_000  # 10% of 80K
        assert partner.total_referrals == 1
        assert partner.pending_payout_cents == 8_000

    def test_auto_upgrade_to_gold(self):
        engine = PartnerEngine()
        partner = engine.register_partner("Test", "UpgradeCo", "test@up.com")
        for i in range(5):
            engine.record_referral(partner.id, f"t{i}", f"Tenant {i}", "growth", 50_000)
        assert partner.tier == PartnerTier.GOLD
        assert partner.commission_rate == 0.15

    def test_auto_upgrade_to_platinum(self):
        engine = PartnerEngine()
        partner = engine.register_partner("Test", "PlatCo", "test@plat.com")
        for i in range(15):
            engine.record_referral(partner.id, f"t{i}", f"Tenant {i}", "growth", 50_000)
        assert partner.tier == PartnerTier.PLATINUM
        assert partner.commission_rate == 0.20

    def test_referral_not_found(self):
        engine = PartnerEngine()
        with pytest.raises(ValueError, match="not found"):
            engine.record_referral("ptr_nope", "t", "T", "growth", 1000)

    def test_list_referrals(self):
        engine = PartnerEngine()
        refs = engine.list_referrals()
        assert len(refs) >= 4

    def test_list_by_partner(self):
        engine = PartnerEngine()
        refs = engine.list_referrals(partner_id="ptr_compliance01")
        for r in refs:
            assert r.partner_id == "ptr_compliance01"


class TestPayouts:
    def test_create_payout(self):
        engine = PartnerEngine()
        partner = engine.get_partner("ptr_compliance01")
        assert partner.pending_payout_cents > 0
        payout = engine.create_payout(partner.id)
        assert payout.amount_cents == 144_000

    def test_process_payout(self):
        engine = PartnerEngine()
        payout = engine.create_payout("ptr_compliance01")
        processed = engine.process_payout(payout.id)
        assert processed.status.value == "paid"
        assert processed.paid_at is not None
        partner = engine.get_partner("ptr_compliance01")
        assert partner.pending_payout_cents == 0

    def test_no_pending_payout(self):
        engine = PartnerEngine()
        partner = engine.register_partner("NoPay", "NoPayCo", "no@pay.com")
        with pytest.raises(ValueError, match="No pending"):
            engine.create_payout(partner.id)

    def test_list_payouts(self):
        engine = PartnerEngine()
        payouts = engine.list_payouts()
        assert len(payouts) >= 3


class TestProgramSummary:
    def test_summary_fields(self):
        engine = PartnerEngine()
        summary = engine.get_program_summary()
        assert summary["total_partners"] >= 4
        assert summary["active_partners"] >= 4
        assert summary["total_earned_cents"] > 0
        assert "tier_breakdown" in summary
        assert "silver" in summary["tier_breakdown"]

    def test_tier_breakdown(self):
        engine = PartnerEngine()
        summary = engine.get_program_summary()
        plat = summary["tier_breakdown"]["platinum"]
        assert plat["count"] >= 1
        assert plat["commission_rate"] == "20%"


# ── API Endpoint Tests ─────────────────────────────────────────────

class TestPartnersAPI:
    def test_register(self):
        response = client.post("/v1/billing/partners", json={
            "name": "API Test", "company": "API Co", "email": "api@test.com"
        })
        assert response.status_code == 200
        assert response.json()["partner"]["tier"] == "silver"

    def test_list_partners(self):
        response = client.get("/v1/billing/partners")
        assert response.status_code == 200
        assert response.json()["total"] >= 4

    def test_get_partner(self):
        response = client.get("/v1/billing/partners/ptr_compliance01")
        assert response.status_code == 200
        assert response.json()["partner"]["company"] == "CompliancePro Consulting"

    def test_get_not_found(self):
        response = client.get("/v1/billing/partners/ptr_nope")
        assert response.status_code == 404

    def test_record_referral(self):
        response = client.post("/v1/billing/partners/ptr_techint03/referral", json={
            "tenant_id": "ref_test", "tenant_name": "Referral Test",
            "tier_id": "growth", "monthly_value_cents": 100_000,
        })
        assert response.status_code == 200
        assert response.json()["referral"]["commission_cents"] == 10_000

    def test_create_payout(self):
        response = client.post("/v1/billing/partners/ptr_foodsafe02/payout")
        assert response.status_code == 200
        assert response.json()["payout"]["amount_cents"] > 0

    def test_program_summary(self):
        response = client.get("/v1/billing/partners/summary")
        assert response.status_code == 200
        assert response.json()["total_partners"] >= 4

    def test_list_referrals(self):
        response = client.get("/v1/billing/partners/referrals")
        assert response.status_code == 200
        assert response.json()["total"] >= 4

    def test_list_payouts(self):
        response = client.get("/v1/billing/partners/payouts")
        assert response.status_code == 200
        assert response.json()["total"] >= 3
