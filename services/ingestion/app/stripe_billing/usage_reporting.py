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

Security-review fix (per-label-metered-billing branch): this function used
to look only at the *current* UTC-calendar-month counter row. But
``increment_usage_for_event`` buckets an accepted event by its own
``event_timestamp`` — a value carried in from untrusted/customer-controlled
inbound data (EPCIS ``eventTime``, webhook/API ``event_timestamp``/
``timestamp`` fields; see ``services/shared/canonical_event.py``'s
``parse_timestamp``, which places no lower bound on how far in the past a
timestamp may be). A routine backfill (or a tenant deliberately submitting
stale timestamps to under-report usage) durably accepts events into a past
billing period's counter row, and that row was never read here — the usage
was silently and permanently excluded from Stripe billing. This function
now reports *every* period with outstanding (``unit_count >
last_reported_count``) usage for the tenant, not just the current one.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import stripe
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import state as _state_mod
from .plans import METERED_ADDONS

logger = structlog.get_logger("stripe-billing.usage")

# Must match the Meter configured in the Stripe Dashboard for this event
# name. Kept in sync with ``METERED_ADDONS["label_events"]["meter_event_name"]``.
METER_EVENT_NAME = METERED_ADDONS["label_events"]["meter_event_name"]


def report_tenant_usage_to_stripe(session: Session, tenant_id: str) -> Optional[Dict[str, Any]]:
    """Report this tenant's un-reported usage, across ALL billing periods, to Stripe.

    No-ops (returns ``None``) if the tenant is not opted into metered
    billing, has no linked Stripe customer, or has no period (current or
    past) with new usage to report.

    Safe to call repeatedly / on a schedule:

    - Only the ``(unit_count - last_reported_count)`` delta is ever sent,
      per period.
    - Every counter row with outstanding usage is read with ``FOR UPDATE``
      in one query, so two concurrent reporting runs for the same tenant
      cannot both read the same pre-report ``unit_count`` and
      double-report the delta.
    - Each Stripe call carries a stable ``identifier`` derived from that
      period's counter's new cumulative value
      (``{tenant_id}:{billing_period_start}:{unit_count}``), so a retried
      call after a successful-but-unacknowledged Stripe response is
      deduplicated Stripe-side too (Stripe enforces uniqueness of
      ``identifier`` within a rolling ~24h window).
    - ``last_reported_count`` only advances after Stripe confirms success
      for that period; all updates commit together at the end. A
      ``stripe.error.StripeError`` on any period is logged and re-raised,
      rolling back the whole batch (no partial updates), so the next run
      naturally re-sends the same (Stripe-deduplicated) identifiers for
      every outstanding period, including ones that already succeeded in
      the failed run.
    """
    mapping = _state_mod._get_subscription_mapping(tenant_id)
    if mapping.get("metered_billing_enabled") != "true":
        return None

    customer_id = mapping.get("customer_id")
    if not customer_id:
        return None

    rows = session.execute(
        text("""
            SELECT billing_period_start, unit_count, last_reported_count
            FROM billing.tenant_usage_counters
            WHERE tenant_id = :tenant_id AND unit_count > last_reported_count
            ORDER BY billing_period_start
            FOR UPDATE
        """),
        {"tenant_id": tenant_id},
    ).fetchall()

    if not rows:
        # No period (current or past) has outstanding usage to report.
        return None

    reported_periods: List[Dict[str, Any]] = []

    for period_start, unit_count, last_reported_count in rows:
        delta = unit_count - last_reported_count
        if delta <= 0:
            # Defensive floor against a corrected/negative count; the WHERE
            # clause above should already exclude these.
            continue

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

        logger.info(
            "stripe_usage_reported",
            tenant_id=tenant_id,
            billing_period_start=period_start.isoformat(),
            delta=delta,
            unit_count=unit_count,
            identifier=identifier,
        )

        reported_periods.append(
            {
                "billing_period_start": period_start.isoformat(),
                "reported_delta": delta,
                "unit_count": unit_count,
                "identifier": identifier,
                "meter_event_id": getattr(meter_event, "identifier", identifier),
            }
        )

    if not reported_periods:
        return None

    session.commit()

    return {
        "tenant_id": tenant_id,
        "periods_reported": len(reported_periods),
        "total_reported_delta": sum(p["reported_delta"] for p in reported_periods),
        "reported_periods": reported_periods,
    }
