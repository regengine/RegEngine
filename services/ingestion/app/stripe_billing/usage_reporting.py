"""Pushes accumulated per-tenant label usage to Stripe's Billing Meters API.

DESIGN_metering-billing.md §5. This is deliberately a plain, synchronous,
independently-callable function rather than something wired into a
request path or a scheduler here (see the design doc §5.1/§7.3 for why
scheduler wiring is left as a documented follow-up) — a caller (an admin
route, a scheduler job, a one-off script) decides when to invoke it per
tenant.

Pinned SDK: ``stripe==15.5.1`` (``requirements.lock``). The legacy
``stripe.SubscriptionItem.create_usage_record`` API does not exist in
this SDK version — the current API is the Billing Meters API:
``stripe.billing.MeterEvent.create(event_name, payload, identifier,
timestamp)``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import stripe
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import state as _state_mod
from .plans import METERED_ADDONS
from .usage import _current_billing_period

logger = structlog.get_logger("stripe-billing.usage")

# Must match the Meter configured in the Stripe Dashboard for this event
# name. Kept in sync with ``METERED_ADDONS["label_events"]["meter_event_name"]``.
METER_EVENT_NAME = METERED_ADDONS["label_events"]["meter_event_name"]


def report_tenant_usage_to_stripe(session: Session, tenant_id: str) -> Optional[Dict[str, Any]]:
    """Report this tenant's un-reported current-period usage to Stripe.

    No-ops (returns ``None``) if the tenant is not opted into metered
    billing, has no linked Stripe customer, or has no new usage to
    report this period.

    Safe to call repeatedly / on a schedule:

    - Only the ``(unit_count - last_reported_count)`` delta is ever sent.
    - The current-period counter row is read with ``FOR UPDATE`` so two
      concurrent reporting runs for the same tenant cannot both read the
      same pre-report ``unit_count`` and double-report the delta.
    - The Stripe call carries a stable ``identifier`` derived from the
      counter's new cumulative value
      (``{tenant_id}:{billing_period_start}:{unit_count}``), so a retried
      call after a successful-but-unacknowledged Stripe response is
      deduplicated Stripe-side too (Stripe enforces uniqueness of
      ``identifier`` within a rolling ~24h window).
    - ``last_reported_count`` only advances after Stripe confirms
      success, in the same transaction as the report; a
      ``stripe.error.StripeError`` is logged and re-raised, leaving
      ``last_reported_count`` untouched so the next run naturally
      retries the same delta.
    """
    mapping = _state_mod._get_subscription_mapping(tenant_id)
    if mapping.get("metered_billing_enabled") != "true":
        return None

    customer_id = mapping.get("customer_id")
    if not customer_id:
        return None

    period_start, _period_end = _current_billing_period()

    row = session.execute(
        text("""
            SELECT unit_count, last_reported_count
            FROM billing.tenant_usage_counters
            WHERE tenant_id = :tenant_id AND billing_period_start = :period_start
            FOR UPDATE
        """),
        {"tenant_id": tenant_id, "period_start": period_start},
    ).fetchone()

    if row is None:
        # No usage recorded yet for this tenant/period — nothing to report.
        return None

    unit_count, last_reported_count = row[0], row[1]
    delta = unit_count - last_reported_count
    if delta <= 0:
        # Nothing new, or a defensive floor against a corrected/negative count.
        return None

    identifier = f"{tenant_id}:{period_start.isoformat()}:{unit_count}"

    try:
        meter_event = stripe.billing.MeterEvent.create(
            event_name=METER_EVENT_NAME,
            payload={"stripe_customer_id": customer_id, "value": str(delta)},
            identifier=identifier,
        )
    except stripe.error.StripeError as exc:
        logger.error(
            "stripe_usage_report_failed",
            tenant_id=tenant_id,
            billing_period_start=period_start.isoformat(),
            delta=delta,
            error=str(exc),
        )
        raise

    session.execute(
        text("""
            UPDATE billing.tenant_usage_counters
            SET last_reported_count = :unit_count, last_reported_at = now()
            WHERE tenant_id = :tenant_id AND billing_period_start = :period_start
        """),
        {"tenant_id": tenant_id, "unit_count": unit_count, "period_start": period_start},
    )
    session.commit()

    logger.info(
        "stripe_usage_reported",
        tenant_id=tenant_id,
        billing_period_start=period_start.isoformat(),
        delta=delta,
        unit_count=unit_count,
        identifier=identifier,
    )

    return {
        "tenant_id": tenant_id,
        "billing_period_start": period_start.isoformat(),
        "reported_delta": delta,
        "unit_count": unit_count,
        "identifier": identifier,
        "meter_event_id": getattr(meter_event, "identifier", identifier),
    }
