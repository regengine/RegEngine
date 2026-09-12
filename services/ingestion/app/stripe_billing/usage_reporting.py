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

    - A session-scoped Postgres advisory lock (``pg_advisory_lock``, keyed
      on the tenant) is held for the entire call, released only in a
      ``finally``. This is what actually provides the concurrency
      guarantee: the per-period commits below end the transaction after
      each period, releasing that period's row-level ``FOR UPDATE`` lock
      as soon as it succeeds -- row locking alone cannot block a second
      call from grabbing an unlocked *later* period once the first has
      committed. The advisory lock has no such gap: a concurrent call
      blocks at its own ``pg_advisory_lock`` until this one fully
      finishes (success, no-op, or exception).
    - Only the ``(unit_count - last_reported_count)`` delta is ever sent,
      per period.
    - Each Stripe call carries an ``identifier`` derived from that period's
      counter's cumulative value at read time
      (``{tenant_id}:{billing_period_start}:{unit_count}``). That value is
      NOT stable across separate invocations: new events keep incrementing
      ``unit_count`` for a period between calls to this function, so a
      later call reporting the same period computes a different
      ``identifier`` and Stripe will not dedupe it against an earlier one.
    - Because of that, ``last_reported_count`` is advanced and committed
      immediately after each period's Stripe call succeeds — not batched
      to one commit at the end. A ``stripe.error.StripeError`` on period N
      only fails to advance period N; every period before it in this call
      that already succeeded is durably committed and will not be
      re-reported (and thus not double-billed) on the next run, however
      much ``unit_count`` has grown for it by then. Only the failed
      period's (and any not-yet-attempted period's) outstanding delta is
      resent.
    """
    mapping = _state_mod._get_subscription_mapping(tenant_id)
    if mapping.get("metered_billing_enabled") != "true":
        return None

    customer_id = mapping.get("customer_id")
    if not customer_id:
        return None

    # Serialize reporting runs for this tenant with a SESSION-scoped
    # advisory lock (pg_advisory_lock, not pg_advisory_xact_lock): the
    # per-period commits below each end the current transaction, which
    # releases the FOR UPDATE row lock taken below as soon as the first
    # period succeeds -- row locking alone can no longer block a second,
    # concurrent call to this function from grabbing an unlocked LATER
    # period and double-reporting it. The advisory lock spans every
    # commit in this call and is released only in the `finally` below,
    # so a concurrent call blocks until this one fully finishes.
    lock_key = text("SELECT pg_advisory_lock(hashtextextended('billing.usage_report:' || :tenant_id, 0))")
    unlock_key = text("SELECT pg_advisory_unlock(hashtextextended('billing.usage_report:' || :tenant_id, 0))")
    session.execute(lock_key, {"tenant_id": tenant_id})
    try:
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
                # Defensive floor against a corrected/negative count; the
                # WHERE clause above should already exclude these.
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
            # Commit this period's advance now, before attempting the next
            # period. A failure on a later period must not roll this back —
            # see the docstring's identifier-instability note. Safe against
            # a concurrent call because the advisory lock above is held
            # across every commit in this function, independent of
            # per-period transaction boundaries.
            session.commit()

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

        return {
            "tenant_id": tenant_id,
            "periods_reported": len(reported_periods),
            "total_reported_delta": sum(p["reported_delta"] for p in reported_periods),
            "reported_periods": reported_periods,
        }
    finally:
        session.execute(unlock_key, {"tenant_id": tenant_id})
