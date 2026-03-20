"""
Notification Preferences Router.

Manages per-tenant notification preferences — which alerts to receive,
delivery channels, quiet hours, and escalation rules.
"""

from __future__ import annotations

import logging
import json
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.webhook_compat import _verify_api_key

logger = logging.getLogger("notification-prefs")


def _get_db():
    """Get database session. Returns None if unavailable."""
    try:
        from shared.database import SessionLocal
        return SessionLocal()
    except Exception as exc:
        logger.warning("db_unavailable error=%s", str(exc))
        return None

router = APIRouter(prefix="/api/v1/notifications", tags=["Notification Preferences"])


class NotificationChannel(BaseModel):
    """A notification delivery channel."""
    channel: str  # email, slack, webhook, sms
    enabled: bool = True
    target: str = ""  # email address, webhook URL, Slack channel


class AlertPreference(BaseModel):
    """Preference for a specific alert rule."""
    rule_id: str
    rule_name: str
    enabled: bool = True
    channels: list[str] = Field(default_factory=lambda: ["email"])
    min_severity: str = "warning"  # info, warning, critical


class QuietHours(BaseModel):
    """Quiet hours configuration."""
    enabled: bool = False
    start_hour: int = 22  # 10 PM
    end_hour: int = 7     # 7 AM
    timezone: str = "America/Los_Angeles"
    override_critical: bool = True  # Critical alerts bypass quiet hours


class EscalationRule(BaseModel):
    """Escalation rule for unacknowledged alerts."""
    enabled: bool = True
    escalate_after_minutes: int = 60
    escalate_to: str = ""  # email or Slack


class NotificationPreferences(BaseModel):
    """Complete notification preferences for a tenant."""
    tenant_id: str
    channels: list[NotificationChannel]
    alert_preferences: list[AlertPreference]
    quiet_hours: QuietHours
    escalation: EscalationRule
    digest_enabled: bool = True
    digest_frequency: str = "daily"  # daily, weekly
    digest_time: str = "08:00"


# Default preferences
def _default_preferences(tenant_id: str) -> NotificationPreferences:
    return NotificationPreferences(
        tenant_id=tenant_id,
        channels=[
            NotificationChannel(channel="email", enabled=True, target="compliance@example.com"),
            NotificationChannel(channel="slack", enabled=False, target="#compliance-alerts"),
            NotificationChannel(channel="webhook", enabled=False, target=""),
            NotificationChannel(channel="sms", enabled=False, target=""),
        ],
        alert_preferences=[
            AlertPreference(rule_id="kde-missing", rule_name="Missing Key Data Elements", enabled=True, channels=["email"], min_severity="warning"),
            AlertPreference(rule_id="cte-overdue", rule_name="Overdue CTE Entry", enabled=True, channels=["email"], min_severity="warning"),
            AlertPreference(rule_id="temp-excursion", rule_name="Temperature Excursion", enabled=True, channels=["email", "slack"], min_severity="info"),
            AlertPreference(rule_id="chain-integrity", rule_name="Hash Chain Break", enabled=True, channels=["email", "slack"], min_severity="info"),
            AlertPreference(rule_id="portal-expiry", rule_name="Supplier Portal Link Expiring", enabled=True, channels=["email"], min_severity="info"),
            AlertPreference(rule_id="fda-deadline", rule_name="FDA Records Request Deadline", enabled=True, channels=["email", "slack", "sms"], min_severity="info"),
            AlertPreference(rule_id="compliance-drop", rule_name="Compliance Score Drop", enabled=True, channels=["email"], min_severity="warning"),
            AlertPreference(rule_id="event-volume-spike", rule_name="Event Volume Anomaly", enabled=False, channels=["email"], min_severity="warning"),
        ],
        quiet_hours=QuietHours(enabled=False),
        escalation=EscalationRule(enabled=True, escalate_after_minutes=60, escalate_to="manager@example.com"),
        digest_enabled=True,
        digest_frequency="daily",
        digest_time="08:00",
    )


# In-memory fallback for when DB is unavailable
_prefs_store: dict[str, NotificationPreferences] = {}


def _db_get_preferences(tenant_id: str) -> Optional[NotificationPreferences]:
    """Query notification preferences from database."""
    db = _get_db()
    if not db:
        return None
    try:
        row = db.execute(
            text("SELECT prefs_json FROM fsma.tenant_notification_prefs WHERE tenant_id = :tid"),
            {"tid": tenant_id}
        ).fetchone()
        if not row:
            return None
        prefs_data = json.loads(row[0]) if row[0] else {}
        prefs_data["tenant_id"] = tenant_id
        return NotificationPreferences(**prefs_data)
    except Exception as exc:
        logger.warning("db_read_failed error=%s", str(exc))
        return None
    finally:
        db.close()


def _db_save_preferences(tenant_id: str, prefs: NotificationPreferences) -> bool:
    """Insert or update notification preferences in database."""
    db = _get_db()
    if not db:
        return False
    try:
        prefs_json = json.dumps(prefs.model_dump(exclude={"tenant_id"}))
        db.execute(
            text("""
                INSERT INTO fsma.tenant_notification_prefs (tenant_id, prefs_json, created_at, updated_at)
                VALUES (:tid, :json, now(), now())
                ON CONFLICT (tenant_id) DO UPDATE SET prefs_json = :json, updated_at = now()
            """),
            {"tid": tenant_id, "json": prefs_json}
        )
        db.commit()
        return True
    except Exception as exc:
        logger.warning("db_write_failed error=%s", str(exc))
        if db:
            db.rollback()
        return False
    finally:
        db.close()


@router.get(
    "/{tenant_id}/preferences",
    response_model=NotificationPreferences,
    summary="Get notification preferences",
)
async def get_preferences(
    tenant_id: str,
    _: None = Depends(_verify_api_key),
) -> NotificationPreferences:
    """Get notification preferences for a tenant."""
    # Try DB first
    prefs = _db_get_preferences(tenant_id)
    if prefs:
        return prefs
    
    # Fall back to memory or return defaults
    if tenant_id not in _prefs_store:
        _prefs_store[tenant_id] = _default_preferences(tenant_id)
    return _prefs_store[tenant_id]


@router.put(
    "/{tenant_id}/preferences",
    response_model=NotificationPreferences,
    summary="Update notification preferences",
)
async def update_preferences(
    tenant_id: str,
    prefs: NotificationPreferences,
    _: None = Depends(_verify_api_key),
) -> NotificationPreferences:
    """Update notification preferences for a tenant."""
    prefs.tenant_id = tenant_id
    
    # Try DB first, fall back to memory
    db_success = _db_save_preferences(tenant_id, prefs)
    if not db_success:
        _prefs_store[tenant_id] = prefs

    logger.info("preferences_updated", extra={"tenant_id": tenant_id})

    return prefs


@router.put(
    "/{tenant_id}/preferences/channel/{channel}",
    summary="Toggle a notification channel",
)
async def toggle_channel(
    tenant_id: str,
    channel: str,
    enabled: bool = True,
    _: None = Depends(_verify_api_key),
):
    """Enable or disable a notification channel."""
    # Get current preferences
    prefs = _db_get_preferences(tenant_id)
    if prefs is None:
        if tenant_id not in _prefs_store:
            _prefs_store[tenant_id] = _default_preferences(tenant_id)
        prefs = _prefs_store[tenant_id]
    
    for ch in prefs.channels:
        if ch.channel == channel:
            ch.enabled = enabled
            
            # Try DB first, fall back to memory
            db_success = _db_save_preferences(tenant_id, prefs)
            if not db_success:
                _prefs_store[tenant_id] = prefs
            
            return {"channel": channel, "enabled": enabled}

    return {"error": f"Channel '{channel}' not found"}


@router.put(
    "/{tenant_id}/preferences/alert/{rule_id}",
    summary="Toggle an alert rule",
)
async def toggle_alert_rule(
    tenant_id: str,
    rule_id: str,
    enabled: bool = True,
    _: None = Depends(_verify_api_key),
):
    """Enable or disable an alert rule notification."""
    # Get current preferences
    prefs = _db_get_preferences(tenant_id)
    if prefs is None:
        if tenant_id not in _prefs_store:
            _prefs_store[tenant_id] = _default_preferences(tenant_id)
        prefs = _prefs_store[tenant_id]
    
    for ap in prefs.alert_preferences:
        if ap.rule_id == rule_id:
            ap.enabled = enabled
            
            # Try DB first, fall back to memory
            db_success = _db_save_preferences(tenant_id, prefs)
            if not db_success:
                _prefs_store[tenant_id] = prefs
            
            return {"rule_id": rule_id, "enabled": enabled}

    return {"error": f"Rule '{rule_id}' not found"}
