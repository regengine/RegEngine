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

    Safe to call repeatedly / on a schedule, and safe against a second,
    concurrent call for the same tenant:

    - A single transaction spans the whole call (no commit until the very
      end, or immediately before re-raising a ``StripeError`` -- see
      below). A previous version of this function committed after each
      period to guard against exactly the failure-rollback problem
      described next, using a session-scoped ``pg_advisory_lock`` to
      still serialize concurrent calls across those commits. That was
      itself broken: ``pg_advisory_lock`` is tied to the specific
      physical Postgres backend connection that acquired it, and a
      pooled SQLAlchemy engine does not guarantee a session keeps the
      same physical connection across multiple commits -- the lock could
      end up stranded on a connection this function no longer holds,
      while a concurrent call proceeds as if unlocked. A transaction-
      scoped ``pg_advisory_xact_lock``, held for one uninterrupted
      transaction on one connection, has no such gap: Postgres releases
      it automatically at COMMIT or ROLLBACK, whichever this function
      does, on the same connection that acquired it.
    - Only the ``(unit_count - last_reported_count)`` delta is ever sent,
      per period.
    - Each Stripe call carries an ``identifier`` derived from that period's
      counter's cumulative value at read time
      (``{tenant_id}:{billing_period_start}:{unit_count}``). That value is
      NOT stable across separate invocations: new events keep incrementing
      ``unit_count`` for a period between calls to this function, so a
      later call reporting the same period computes a different
      ``identifier`` and Stripe will not dedupe it against an earlier one.
      That means a period already reported successfully must never be
      discarded by a ROLLBACK, or a later retry would re-report it under a
      new identifier and double-bill it. So a ``stripe.error.StripeError``
      on period N does not roll back the transaction: everything written
      so far (periods before N, all in this same still-open transaction)
      is committed before the error is re-raised, and only period N's
      (and any not-yet-attempted period's) delta is left outstanding for
      the next call.
    """
    mapping = _state_mod._get_subscription_mapping(tenant_id)
    if mapping.get("metered_billing_enabled") != "true":
        return None

    customer_id = mapping.get("customer_id")
    if not customer_id:
        return None

    # Transaction-scoped advisory lock: serializes concurrent calls for
    # this tenant without any separate unlock call or cross-connection
    # risk (see docstring). Held for the rest of this transaction.
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended('billing.usage_report:' || :tenant_id, 0))"),
        {"tenant_id": tenant_id},
    )

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
        # Nothing was written; commit just to release the xact lock.
        session.commit()
        return None

    reported_periods: List[Dict[str, Any]] = []

    try:
        for period_start, unit_count, last_reported_count in rows:
            delta = unit_count - last_reported_count
            if delta <= 0:
                # Defensive floor against a corrected/negative count; the
                # WHERE clause above should already exclude these.
                continue

            identifier = f"{tenant_id}:{period_start.isoformat()}:{unit_count}"

            meter_event = stripe.billing.MeterEvent.create(
                event_name=METER_EVENT_NAME,
                payload={"stripe_customer_id": customer_id, "value": str(delta)},
                identifier=identifier,
            )

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
    except stripe.error.StripeError as exc:
        logger.error(
            "stripe_usage_report_failed",
            tenant_id=tenant_id,
            billing_period_start=period_start.isoformat(),
            delta=delta,
            error=str(exc),
        )
        # Commit (not rollback): every period already written above must
        # survive -- see the docstring's identifier-instability note.
        session.commit()
        raise

    if not reported_periods:
        session.commit()
        return None

    session.commit()

    return {
        "tenant_id": tenant_id,
        "periods_reported": len(reported_periods),
        "total_reported_delta": sum(p["reported_delta"] for p in reported_periods),
        "reported_periods": reported_periods,
    }
