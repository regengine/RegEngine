"""
Dunning Engine & API Tests

Tests case management, retry logic, escalation workflow,
write-offs, and API endpoints.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app
from dunning_engine import DunningEngine, DunningStatus, DunningStage

client = TestClient(app)


# ── Engine Unit Tests ──────────────────────────────────────────────

class TestCaseManagement:
    def test_open_case(self):
        engine = DunningEngine()
        case = engine.open_case("t1", "Test Corp", "inv_001", "INV-001", 100_000)
        assert case.tenant_id == "t1"
        assert case.status == DunningStatus.ACTIVE
        assert case.stage == DunningStage.REMINDER
        assert case.amount_due_cents == 100_000

    def test_list_cases(self):
        engine = DunningEngine()
        cases = engine.list_cases()
        assert len(cases) >= 4

    def test_list_by_status(self):
        engine = DunningEngine()
        active = engine.list_cases(status=DunningStatus.ACTIVE)
        for c in active:
            assert c.status == DunningStatus.ACTIVE

    def test_list_by_stage(self):
        engine = DunningEngine()
        reminders = engine.list_cases(stage=DunningStage.REMINDER)
        for c in reminders:
            assert c.stage == DunningStage.REMINDER

    def test_get_case(self):
        engine = DunningEngine()
        case = engine.get_case("dun_medsecure_01")
        assert case is not None
        assert case.tenant_name == "MedSecure Health"

    def test_get_not_found(self):
        engine = DunningEngine()
        assert engine.get_case("dun_nope") is None


class TestRetryAndEscalation:
    def test_retry_returns_attempt(self):
        engine = DunningEngine()
        case = engine.open_case("t1", "Test", "inv_001", "INV-001", 50_000)
        attempt = engine.retry_payment(case.id)
        assert attempt.attempt_number == 1
        assert attempt.amount_cents == 50_000

    def test_cannot_retry_written_off(self):
        engine = DunningEngine()
        with pytest.raises(ValueError, match="written_off"):
            engine.retry_payment("dun_oldco_01")

    def test_escalate_case(self):
        engine = DunningEngine()
        case = engine.open_case("t1", "Test", "inv_001", "INV-001", 50_000)
        assert case.stage == DunningStage.REMINDER
        engine.escalate_case(case.id)
        assert case.stage == DunningStage.FIRST_NOTICE

    def test_escalate_through_stages(self):
        engine = DunningEngine()
        case = engine.open_case("t1", "Test", "inv_001", "INV-001", 50_000)
        engine.escalate_case(case.id)
        assert case.stage == DunningStage.FIRST_NOTICE
        engine.escalate_case(case.id)
        assert case.stage == DunningStage.SECOND_NOTICE

    def test_cannot_escalate_written_off(self):
        engine = DunningEngine()
        with pytest.raises(ValueError, match="written_off"):
            engine.escalate_case("dun_oldco_01")

    def test_write_off(self):
        engine = DunningEngine()
        case = engine.open_case("t1", "Test", "inv_001", "INV-001", 50_000)
        written = engine.write_off(case.id)
        assert written.status == DunningStatus.WRITTEN_OFF
        assert written.resolved_at is not None


class TestDunningSummary:
    def test_summary_fields(self):
        engine = DunningEngine()
        summary = engine.get_summary()
        assert summary["total_cases"] >= 4
        assert summary["active_cases"] >= 2
        assert summary["recovered_cases"] >= 1
        assert "stage_breakdown" in summary
        assert "escalation_schedule" in summary
        assert len(summary["escalation_schedule"]) == 6


# ── API Endpoint Tests ─────────────────────────────────────────────

class TestDunningAPI:
    def test_open_case(self):
        response = client.post("/v1/billing/dunning", json={
            "tenant_id": "api_test", "tenant_name": "API Test",
            "invoice_id": "inv_api", "amount_due_cents": 75_000,
        })
        assert response.status_code == 200

    def test_list_cases(self):
        response = client.get("/v1/billing/dunning")
        assert response.status_code == 200
        assert response.json()["total"] >= 4

    def test_get_case(self):
        response = client.get("/v1/billing/dunning/dun_medsecure_01")
        assert response.status_code == 200

    def test_get_not_found(self):
        response = client.get("/v1/billing/dunning/dun_nope")
        assert response.status_code == 404

    def test_summary(self):
        response = client.get("/v1/billing/dunning/summary")
        assert response.status_code == 200
        assert response.json()["total_cases"] >= 4

    def test_retry(self):
        create = client.post("/v1/billing/dunning", json={
            "tenant_id": "retry_test", "tenant_name": "Retry Test",
            "invoice_id": "inv_retry", "amount_due_cents": 25_000,
        })
        case_id = create.json()["case"]["id"]
        response = client.post(f"/v1/billing/dunning/{case_id}/retry")
        assert response.status_code == 200
        assert "attempt" in response.json()

    def test_escalate(self):
        create = client.post("/v1/billing/dunning", json={
            "tenant_id": "esc_test", "tenant_name": "Escalate Test",
            "invoice_id": "inv_esc", "amount_due_cents": 30_000,
        })
        case_id = create.json()["case"]["id"]
        response = client.post(f"/v1/billing/dunning/{case_id}/escalate")
        assert response.status_code == 200
        assert response.json()["case"]["stage"] == "first_notice"

    def test_write_off(self):
        create = client.post("/v1/billing/dunning", json={
            "tenant_id": "wo_test", "tenant_name": "Write-off Test",
            "invoice_id": "inv_wo", "amount_due_cents": 10_000,
        })
        case_id = create.json()["case"]["id"]
        response = client.post(f"/v1/billing/dunning/{case_id}/write-off")
        assert response.status_code == 200
        assert response.json()["case"]["status"] == "written_off"
