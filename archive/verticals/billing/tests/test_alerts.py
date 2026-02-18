"""
Alerts Engine & API Tests

Tests alert rules, event firing, acknowledgment,
webhooks, and API endpoints.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app
from alerts_engine import AlertsEngine, AlertType, AlertSeverity, AlertChannel, WebhookStatus

client = TestClient(app)


# ── Engine Unit Tests ──────────────────────────────────────────────

class TestAlertRules:
    def test_list_rules(self):
        engine = AlertsEngine()
        rules = engine.list_rules()
        assert len(rules) >= 6

    def test_create_rule(self):
        engine = AlertsEngine()
        rule = engine.create_rule(
            name="Test Rule", alert_type=AlertType.CREDIT_LOW,
            severity=AlertSeverity.WARNING, channels=[AlertChannel.EMAIL],
        )
        assert rule.name == "Test Rule"
        assert rule.enabled is True

    def test_toggle_rule(self):
        engine = AlertsEngine()
        rule = engine.toggle_rule("rule_pay_fail")
        assert rule.enabled is False
        engine.toggle_rule("rule_pay_fail")
        assert rule.enabled is True

    def test_toggle_not_found(self):
        engine = AlertsEngine()
        with pytest.raises(ValueError, match="not found"):
            engine.toggle_rule("rule_nope")


class TestAlertEvents:
    def test_list_events(self):
        engine = AlertsEngine()
        events = engine.list_events()
        assert len(events) >= 5

    def test_filter_by_type(self):
        engine = AlertsEngine()
        events = engine.list_events(alert_type=AlertType.PAYMENT_FAILED)
        assert all(e.alert_type == AlertType.PAYMENT_FAILED for e in events)

    def test_filter_by_severity(self):
        engine = AlertsEngine()
        critical = engine.list_events(severity=AlertSeverity.CRITICAL)
        assert all(e.severity == AlertSeverity.CRITICAL for e in critical)

    def test_unacknowledged_only(self):
        engine = AlertsEngine()
        unacked = engine.list_events(unacknowledged_only=True)
        assert all(not e.acknowledged for e in unacked)

    def test_fire_alert(self):
        engine = AlertsEngine()
        event = engine.fire_alert(
            alert_type=AlertType.PAYMENT_FAILED,
            title="Test Alert", message="Test message",
            severity=AlertSeverity.CRITICAL,
        )
        assert event.title == "Test Alert"
        assert len(event.channels_notified) > 0

    def test_acknowledge(self):
        engine = AlertsEngine()
        event = engine.acknowledge_event("evt_pay_medsecure")
        assert event.acknowledged is True

    def test_acknowledge_not_found(self):
        engine = AlertsEngine()
        with pytest.raises(ValueError, match="not found"):
            engine.acknowledge_event("evt_nope")


class TestWebhooks:
    def test_list_webhooks(self):
        engine = AlertsEngine()
        webhooks = engine.list_webhooks()
        assert len(webhooks) >= 3

    def test_filter_by_status(self):
        engine = AlertsEngine()
        failed = engine.list_webhooks(status=WebhookStatus.FAILED)
        assert all(w.status == WebhookStatus.FAILED for w in failed)


class TestAlertsSummary:
    def test_summary(self):
        engine = AlertsEngine()
        summary = engine.get_summary()
        assert summary["total_events"] >= 5
        assert summary["total_rules"] >= 6
        assert "events_by_type" in summary
        assert summary["webhook_deliveries"] >= 3


# ── API Endpoint Tests ─────────────────────────────────────────────

class TestAlertsAPI:
    def test_list_rules(self):
        response = client.get("/v1/billing/alerts/rules")
        assert response.status_code == 200
        assert response.json()["total"] >= 6

    def test_create_rule(self):
        response = client.post("/v1/billing/alerts/rules", json={
            "name": "API Test Rule", "alert_type": "credit_low",
            "severity": "warning", "channels": ["email"],
        })
        assert response.status_code == 200

    def test_toggle_rule(self):
        response = client.post("/v1/billing/alerts/rules/rule_pay_fail/toggle")
        assert response.status_code == 200

    def test_list_events(self):
        response = client.get("/v1/billing/alerts/events")
        assert response.status_code == 200
        assert response.json()["total"] >= 5

    def test_acknowledge(self):
        response = client.post("/v1/billing/alerts/events/evt_usage_acme/acknowledge")
        assert response.status_code == 200

    def test_fire_alert(self):
        # Ensure payment_failed rule is enabled (may have been toggled by earlier test)
        from alerts_engine import alerts_engine
        rule = alerts_engine._rules.get("rule_pay_fail")
        if rule and not rule.enabled:
            rule.enabled = True
        response = client.post("/v1/billing/alerts/fire", json={
            "alert_type": "payment_failed", "title": "API Fire Test",
            "message": "Fired from API test", "severity": "critical",
        })
        assert response.status_code == 200
        assert len(response.json()["channels"]) > 0

    def test_webhooks(self):
        response = client.get("/v1/billing/alerts/webhooks")
        assert response.status_code == 200
        assert response.json()["total"] >= 3

    def test_summary(self):
        response = client.get("/v1/billing/alerts/summary")
        assert response.status_code == 200
        assert response.json()["total_rules"] >= 6
