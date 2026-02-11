"""
Billing Service — Alerts & Notifications Engine

Configurable billing alerts, webhook event log, and notification
rules for payment failures, usage thresholds, and contract events.
In-memory store for sandbox mode.
"""

from __future__ import annotations

import structlog
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4
from enum import Enum
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# ── Enums ──────────────────────────────────────────────────────────

class AlertType(str, Enum):
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_SUCCEEDED = "payment_succeeded"
    USAGE_THRESHOLD = "usage_threshold"
    INVOICE_OVERDUE = "invoice_overdue"
    TRIAL_EXPIRING = "trial_expiring"
    CONTRACT_EXPIRING = "contract_expiring"
    PLAN_CHANGED = "plan_changed"
    CREDIT_LOW = "credit_low"
    DUNNING_ESCALATED = "dunning_escalated"
    TAX_EXEMPTION_EXPIRING = "tax_exemption_expiring"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertChannel(str, Enum):
    EMAIL = "email"
    WEBHOOK = "webhook"
    SLACK = "slack"
    IN_APP = "in_app"


class WebhookStatus(str, Enum):
    DELIVERED = "delivered"
    FAILED = "failed"
    PENDING = "pending"
    RETRYING = "retrying"


# ── Models ─────────────────────────────────────────────────────────

class AlertRule(BaseModel):
    id: str = Field(default_factory=lambda: f"rule_{uuid4().hex[:8]}")
    name: str
    alert_type: AlertType
    severity: AlertSeverity
    channels: list[AlertChannel]
    enabled: bool = True
    threshold: Optional[float] = None  # for usage/credit rules
    recipient_emails: list[str] = []
    webhook_url: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AlertEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:12]}")
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    tenant_id: str = ""
    tenant_name: str = ""
    channels_notified: list[AlertChannel] = []
    acknowledged: bool = False
    metadata: dict = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WebhookEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"whk_{uuid4().hex[:12]}")
    event_type: str
    status: WebhookStatus
    url: str
    payload_summary: str = ""
    response_code: int = 0
    attempts: int = 1
    next_retry_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Alerts Engine ──────────────────────────────────────────────────

class AlertsEngine:
    """Billing alerts, notifications, and webhook management."""

    def __init__(self):
        self._rules: dict[str, AlertRule] = {}
        self._events: dict[str, AlertEvent] = {}
        self._webhooks: dict[str, WebhookEvent] = {}
        self._seed_demo_data()

    def _seed_demo_data(self):
        now = datetime.utcnow()

        # Default alert rules
        rules = [
            AlertRule(id="rule_pay_fail", name="Payment Failed", alert_type=AlertType.PAYMENT_FAILED,
                      severity=AlertSeverity.CRITICAL, channels=[AlertChannel.EMAIL, AlertChannel.SLACK, AlertChannel.IN_APP],
                      recipient_emails=["billing@regengine.co"]),
            AlertRule(id="rule_usage_80", name="Usage at 80%", alert_type=AlertType.USAGE_THRESHOLD,
                      severity=AlertSeverity.WARNING, channels=[AlertChannel.EMAIL, AlertChannel.IN_APP],
                      threshold=80.0, recipient_emails=["ops@regengine.co"]),
            AlertRule(id="rule_trial_exp", name="Trial Expiring (3 days)", alert_type=AlertType.TRIAL_EXPIRING,
                      severity=AlertSeverity.INFO, channels=[AlertChannel.EMAIL],
                      threshold=3.0, recipient_emails=["sales@regengine.co"]),
            AlertRule(id="rule_contract_exp", name="Contract Renewal Due", alert_type=AlertType.CONTRACT_EXPIRING,
                      severity=AlertSeverity.WARNING, channels=[AlertChannel.EMAIL, AlertChannel.SLACK],
                      threshold=30.0, recipient_emails=["deals@regengine.co"]),
            AlertRule(id="rule_credit_low", name="Credits Below $100", alert_type=AlertType.CREDIT_LOW,
                      severity=AlertSeverity.WARNING, channels=[AlertChannel.IN_APP],
                      threshold=10_000),
            AlertRule(id="rule_dunning_esc", name="Dunning Escalated", alert_type=AlertType.DUNNING_ESCALATED,
                      severity=AlertSeverity.CRITICAL, channels=[AlertChannel.EMAIL, AlertChannel.SLACK],
                      recipient_emails=["collections@regengine.co"]),
        ]
        for r in rules:
            self._rules[r.id] = r

        # Recent alert events
        events = [
            AlertEvent(id="evt_pay_medsecure", alert_type=AlertType.PAYMENT_FAILED,
                       severity=AlertSeverity.CRITICAL, title="Payment Failed — MedSecure",
                       message="Retry #2 declined for INV-2026-1009 ($12,049.55). Card ending 8888.",
                       tenant_id="medsecure", tenant_name="MedSecure Health",
                       channels_notified=[AlertChannel.EMAIL, AlertChannel.SLACK],
                       created_at=now - timedelta(hours=6)),
            AlertEvent(id="evt_usage_acme", alert_type=AlertType.USAGE_THRESHOLD,
                       severity=AlertSeverity.WARNING, title="API Usage at 85% — Acme Foods",
                       message="Acme Foods has used 42,500 of 50,000 API calls this month.",
                       tenant_id="acme_foods", tenant_name="Acme Foods Inc.",
                       channels_notified=[AlertChannel.IN_APP],
                       created_at=now - timedelta(hours=18)),
            AlertEvent(id="evt_trial_beta", alert_type=AlertType.TRIAL_EXPIRING,
                       severity=AlertSeverity.INFO, title="Trial Expiring — BetaCorp Analytics",
                       message="Enterprise trial expires in 2 days. No payment method on file.",
                       tenant_id="beta_corp", tenant_name="BetaCorp Analytics",
                       channels_notified=[AlertChannel.EMAIL],
                       created_at=now - timedelta(hours=24)),
            AlertEvent(id="evt_contract_fresh", alert_type=AlertType.CONTRACT_EXPIRING,
                       severity=AlertSeverity.WARNING, title="Contract Renewal — FreshLeaf",
                       message="Annual contract RE-2026-002 expires in 28 days. Renewal discussion needed.",
                       tenant_id="freshleaf", tenant_name="FreshLeaf Produce",
                       channels_notified=[AlertChannel.EMAIL, AlertChannel.SLACK],
                       created_at=now - timedelta(days=2)),
            AlertEvent(id="evt_plan_acme", alert_type=AlertType.PLAN_CHANGED,
                       severity=AlertSeverity.INFO, title="Upgrade — Acme Foods",
                       message="Acme Foods upgraded from Professional to Enterprise. Proration: $2,100.00",
                       tenant_id="acme_foods", tenant_name="Acme Foods Inc.",
                       channels_notified=[AlertChannel.IN_APP], acknowledged=True,
                       created_at=now - timedelta(days=12)),
        ]
        for e in events:
            self._events[e.id] = e

        # Webhook delivery log
        webhooks = [
            WebhookEvent(id="whk_pay_fail_01", event_type="payment.failed", status=WebhookStatus.DELIVERED,
                         url="https://hooks.slack.com/billing", payload_summary='{"tenant":"medsecure","amount":1204955}',
                         response_code=200, created_at=now - timedelta(hours=6)),
            WebhookEvent(id="whk_plan_chg_01", event_type="subscription.changed", status=WebhookStatus.DELIVERED,
                         url="https://hooks.slack.com/billing", payload_summary='{"tenant":"acme","from":"pro","to":"enterprise"}',
                         response_code=200, created_at=now - timedelta(days=12)),
            WebhookEvent(id="whk_fail_01", event_type="invoice.overdue", status=WebhookStatus.FAILED,
                         url="https://api.partner.com/hooks/billing", payload_summary='{"invoice":"INV-2026-1009"}',
                         response_code=500, attempts=3, created_at=now - timedelta(days=1)),
        ]
        for w in webhooks:
            self._webhooks[w.id] = w

    # ── Alert Rules ────────────────────────────────────────────

    def create_rule(self, name: str, alert_type: AlertType, severity: AlertSeverity,
                    channels: list[AlertChannel], threshold: float | None = None,
                    recipient_emails: list[str] | None = None,
                    webhook_url: str = "") -> AlertRule:
        rule = AlertRule(
            name=name, alert_type=alert_type, severity=severity,
            channels=channels, threshold=threshold,
            recipient_emails=recipient_emails or [],
            webhook_url=webhook_url,
        )
        self._rules[rule.id] = rule
        logger.info("alert_rule_created", name=name, type=alert_type.value)
        return rule

    def list_rules(self) -> list[AlertRule]:
        return list(self._rules.values())

    def toggle_rule(self, rule_id: str) -> AlertRule:
        rule = self._rules.get(rule_id)
        if not rule:
            raise ValueError(f"Rule {rule_id} not found")
        rule.enabled = not rule.enabled
        return rule

    # ── Alert Events ───────────────────────────────────────────

    def fire_alert(self, alert_type: AlertType, title: str, message: str,
                   tenant_id: str = "", tenant_name: str = "",
                   severity: AlertSeverity = AlertSeverity.INFO,
                   metadata: dict | None = None) -> AlertEvent:
        # Find matching rules
        matched_channels: list[AlertChannel] = []
        for rule in self._rules.values():
            if rule.alert_type == alert_type and rule.enabled:
                matched_channels.extend(rule.channels)
        matched_channels = list(set(matched_channels))

        event = AlertEvent(
            alert_type=alert_type, severity=severity,
            title=title, message=message,
            tenant_id=tenant_id, tenant_name=tenant_name,
            channels_notified=matched_channels,
            metadata=metadata or {},
        )
        self._events[event.id] = event
        logger.info("alert_fired", type=alert_type.value, title=title)
        return event

    def list_events(self, alert_type: AlertType | None = None,
                    severity: AlertSeverity | None = None,
                    unacknowledged_only: bool = False) -> list[AlertEvent]:
        events = list(self._events.values())
        if alert_type:
            events = [e for e in events if e.alert_type == alert_type]
        if severity:
            events = [e for e in events if e.severity == severity]
        if unacknowledged_only:
            events = [e for e in events if not e.acknowledged]
        return sorted(events, key=lambda e: e.created_at, reverse=True)

    def acknowledge_event(self, event_id: str) -> AlertEvent:
        event = self._events.get(event_id)
        if not event:
            raise ValueError(f"Event {event_id} not found")
        event.acknowledged = True
        return event

    # ── Webhooks ───────────────────────────────────────────────

    def list_webhooks(self, status: WebhookStatus | None = None) -> list[WebhookEvent]:
        webhooks = list(self._webhooks.values())
        if status:
            webhooks = [w for w in webhooks if w.status == status]
        return sorted(webhooks, key=lambda w: w.created_at, reverse=True)

    # ── Summary ────────────────────────────────────────────────

    def get_summary(self) -> dict:
        events = list(self._events.values())
        unack = [e for e in events if not e.acknowledged]
        critical = [e for e in unack if e.severity == AlertSeverity.CRITICAL]
        webhooks = list(self._webhooks.values())
        failed_hooks = [w for w in webhooks if w.status == WebhookStatus.FAILED]

        by_type: dict[str, int] = {}
        for e in events:
            by_type[e.alert_type.value] = by_type.get(e.alert_type.value, 0) + 1

        return {
            "total_events": len(events),
            "unacknowledged": len(unack),
            "critical_unacked": len(critical),
            "total_rules": len(self._rules),
            "enabled_rules": sum(1 for r in self._rules.values() if r.enabled),
            "events_by_type": by_type,
            "webhook_deliveries": len(webhooks),
            "webhook_failures": len(failed_hooks),
            "webhook_success_rate": round(
                (len(webhooks) - len(failed_hooks)) / max(len(webhooks), 1) * 100, 1
            ),
        }


# Singleton
alerts_engine = AlertsEngine()
