"""
Notification Preferences Router.

Manages per-tenant notification preferences — which alerts to receive,
delivery channels, quiet hours, and escalation rules.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .webhook_compat import require_tenant_context
from shared.tenant_context import TenantContext
from shared.tenant_settings import get_jsonb, set_jsonb

logger = logging.getLogger("notification-prefs")


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
    """Query notification preferences from database via shared helper.

    The stored JSONB blob never persists tenant_id (excluded by
    ``_db_save_preferences``); attach the authoritative tenant_id from
    the function argument when constructing the response model.
    """
    stored = get_jsonb(tenant_id, "tenant_notification_prefs", "prefs")
    if stored:
        return NotificationPreferences(**{**stored, "tenant_id": tenant_id})
    return None


def _db_save_preferences(tenant_id: str, prefs: NotificationPreferences) -> bool:
    """Insert or update notification preferences in database via shared helper."""
    return set_jsonb(tenant_id, "tenant_notification_prefs", "prefs", prefs.model_dump(exclude={"tenant_id"}))


@router.get(
    "/{tenant_id}/preferences",
    response_model=NotificationPreferences,
    summary="Get notification preferences",
)
async def get_preferences(
    tenant_id: str,
    ctx: TenantContext = Depends(require_tenant_context),
) -> NotificationPreferences:
    """Get notification preferences for a tenant."""
    tenant_id = ctx.tenant_id
    # Try DB first
    prefs = _db_get_preferences(tenant_id)
    if prefs:
        _prefs_store[tenant_id] = prefs  # cache for fallback
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
    ctx: TenantContext = Depends(require_tenant_context),
) -> NotificationPreferences:
    """Update notification preferences for a tenant."""
    tenant_id = ctx.tenant_id
    prefs.tenant_id = tenant_id

    # Try DB first, fall back to memory
    db_success = _db_save_preferences(tenant_id, prefs)
    if db_success:
        _prefs_store[tenant_id] = prefs  # keep cache in sync
    else:
        logger.error("db_write_failed_fallback_to_memory tenant_id=%s endpoint=update_preferences", tenant_id)
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
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Enable or disable a notification channel."""
    tenant_id = ctx.tenant_id
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
            if db_success:
                _prefs_store[tenant_id] = prefs  # keep cache in sync
            else:
                logger.error("db_write_failed_fallback_to_memory tenant_id=%s endpoint=toggle_channel", tenant_id)
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
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Enable or disable an alert rule notification."""
    tenant_id = ctx.tenant_id
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
            if db_success:
                _prefs_store[tenant_id] = prefs  # keep cache in sync
            else:
                logger.error("db_write_failed_fallback_to_memory tenant_id=%s endpoint=toggle_alert_rule", tenant_id)
                _prefs_store[tenant_id] = prefs

            return {"rule_id": rule_id, "enabled": enabled}

    return {"error": f"Rule '{rule_id}' not found"}
