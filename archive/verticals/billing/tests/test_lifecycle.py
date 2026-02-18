"""
Lifecycle Engine & API Tests

Tests proration, plan changes, trials, cancellation,
and API endpoints.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app
from lifecycle_engine import LifecycleEngine, ChangeType, CancellationReason, PLAN_CATALOG

client = TestClient(app)


# ── Engine Unit Tests ──────────────────────────────────────────────

class TestProration:
    def test_upgrade_proration(self):
        engine = LifecycleEngine()
        result = engine.calculate_proration("starter", "professional", 15)
        assert result.days_remaining == 15
        assert result.new_plan_charge_cents > result.old_plan_credit_cents
        assert result.net_amount_cents > 0

    def test_downgrade_proration(self):
        engine = LifecycleEngine()
        result = engine.calculate_proration("enterprise", "starter", 20)
        assert result.net_amount_cents < 0

    def test_same_plan_zero_net(self):
        engine = LifecycleEngine()
        result = engine.calculate_proration("professional", "professional", 10)
        assert result.net_amount_cents == 0

    def test_unknown_plan(self):
        engine = LifecycleEngine()
        with pytest.raises(ValueError, match="Unknown plan"):
            engine.calculate_proration("starter", "nonexistent", 10)

    def test_full_period(self):
        engine = LifecycleEngine()
        result = engine.calculate_proration("starter", "enterprise", 30, 30)
        assert result.old_plan_credit_cents == PLAN_CATALOG["starter"]["monthly_cents"]


class TestPlanChanges:
    def test_upgrade(self):
        engine = LifecycleEngine()
        change = engine.change_plan("t1", "Test", "starter", "professional")
        assert change.change_type == ChangeType.UPGRADE
        assert change.proration is not None

    def test_downgrade(self):
        engine = LifecycleEngine()
        change = engine.change_plan("t1", "Test", "enterprise", "professional")
        assert change.change_type == ChangeType.DOWNGRADE

    def test_cancellation(self):
        engine = LifecycleEngine()
        change = engine.change_plan("t1", "Test", "starter", "none",
                                     cancel_reason=CancellationReason.TOO_EXPENSIVE)
        assert change.change_type == ChangeType.CANCELLATION
        assert change.cancel_reason == CancellationReason.TOO_EXPENSIVE

    def test_scheduled_change(self):
        engine = LifecycleEngine()
        change = engine.change_plan("t1", "Test", "professional", "starter", schedule=True)
        assert change.status.value == "scheduled"

    def test_list_changes(self):
        engine = LifecycleEngine()
        changes = engine.list_changes()
        assert len(changes) >= 5

    def test_list_by_type(self):
        engine = LifecycleEngine()
        upgrades = engine.list_changes(change_type=ChangeType.UPGRADE)
        for c in upgrades:
            assert c.change_type == ChangeType.UPGRADE

    def test_get_change(self):
        engine = LifecycleEngine()
        change = engine.get_change("chg_acme_up01")
        assert change is not None
        assert change.tenant_name == "Acme Foods Inc."


class TestTrials:
    def test_list_trials(self):
        engine = LifecycleEngine()
        trials = engine.list_trials()
        assert len(trials) >= 3

    def test_active_only(self):
        engine = LifecycleEngine()
        active = engine.list_trials(active_only=True)
        for t in active:
            assert t.days_remaining > 0 and not t.converted

    def test_start_trial(self):
        engine = LifecycleEngine()
        trial = engine.start_trial("new_t", "New Tenant", "professional", 14)
        assert trial.plan == "professional"
        assert trial.days_remaining == 14

    def test_invalid_plan(self):
        engine = LifecycleEngine()
        with pytest.raises(ValueError, match="Unknown plan"):
            engine.start_trial("t1", "Test", "nonexistent")


class TestLifecycleSummary:
    def test_summary(self):
        engine = LifecycleEngine()
        summary = engine.get_summary()
        assert summary["total_changes"] >= 5
        assert summary["upgrades"] >= 2
        assert summary["cancellations"] >= 1
        assert summary["active_trials"] >= 2
        assert "plan_catalog" in summary


# ── API Endpoint Tests ─────────────────────────────────────────────

class TestLifecycleAPI:
    def test_change_plan(self):
        response = client.post("/v1/billing/lifecycle/change", json={
            "tenant_id": "api_test", "tenant_name": "API Test",
            "from_plan": "starter", "to_plan": "professional",
        })
        assert response.status_code == 200
        assert response.json()["change"]["change_type"] == "upgrade"

    def test_prorate(self):
        response = client.post("/v1/billing/lifecycle/prorate", json={
            "from_plan": "starter", "to_plan": "enterprise", "days_remaining": 20,
        })
        assert response.status_code == 200
        assert response.json()["proration"]["net_amount_cents"] > 0

    def test_list_changes(self):
        response = client.get("/v1/billing/lifecycle/changes")
        assert response.status_code == 200
        assert response.json()["total"] >= 5

    def test_get_change(self):
        response = client.get("/v1/billing/lifecycle/changes/chg_acme_up01")
        assert response.status_code == 200

    def test_get_not_found(self):
        response = client.get("/v1/billing/lifecycle/changes/chg_nope")
        assert response.status_code == 404

    def test_list_trials(self):
        response = client.get("/v1/billing/lifecycle/trials")
        assert response.status_code == 200
        assert response.json()["total"] >= 3

    def test_start_trial(self):
        response = client.post("/v1/billing/lifecycle/trials", json={
            "tenant_id": "trial_api", "tenant_name": "Trial API", "plan": "enterprise",
        })
        assert response.status_code == 200

    def test_summary(self):
        response = client.get("/v1/billing/lifecycle/summary")
        assert response.status_code == 200
        assert response.json()["total_changes"] >= 5

    def test_plans(self):
        response = client.get("/v1/billing/lifecycle/plans")
        assert response.status_code == 200
        assert len(response.json()["plans"]) == 4
