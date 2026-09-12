"""Per-label metered usage tracking (DESIGN_metering-billing.md §4).

Billable unit ("a label"): one ``TraceabilityEvent`` durably accepted into
``fsma.traceability_events`` — i.e. one genuinely NEW row inserted by
``CanonicalEventStore.persist_event`` / ``persist_events_batch``
(``services/shared/canonical_persistence/writer.py``), not a replay that
resolves to ``idempotent=True``. That is the single choke point every
production caller of the canonical writer already passes through, so the
counting hook lives there — this module only provides the (idempotent)
increment primitive it calls.

Usage is tracked for every tenant unconditionally (cheap: two indexed
upserts in the caller's existing transaction) regardless of whether the
tenant has opted into metered billing. Whether accumulated usage is ever
*reported* to Stripe is a separate, later concern gated by the tenant's
opt-in flag — see ``usage_reporting.report_tenant_usage_to_stripe``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional, Tuple, Union

from sqlalchemy import text
from sqlalchemy.orm import Session


def _current_billing_period(as_of: Optional[date] = None) -> Tuple[date, date]:
    """Return the UTC calendar-month bucket ``(period_start, period_end)``
    containing ``as_of`` (default: today, UTC).

    ``period_end`` is the first day of the *next* month (an exclusive
    upper bound) — matches the ``billing.tenant_usage_counters`` schema's
    ``billing_period_end`` column.

    Deliberately NOT the tenant's real Stripe subscription anchor day —
    see DESIGN_metering-billing.md §3.3/§7.2 for why: the Redis
    subscription mapping doesn't reliably carry a local
    ``current_period_start``, and the Meter Events pushed to Stripe carry
    no period metadata of our own — Stripe's own meter aggregates them
    into the customer's real invoice period regardless of how we bucket
    locally. This bucket is for local display / idempotency-window
    purposes only.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc).date()

    period_start = as_of.replace(day=1)
    if period_start.month == 12:
        period_end = period_start.replace(year=period_start.year + 1, month=1)
    else:
        period_end = period_start.replace(month=period_start.month + 1)
    return period_start, period_end


def increment_usage_for_event(
    session: Session,
    *,
    tenant_id: str,
    event_id: str,
    event_timestamp: Union[datetime, date],
) -> bool:
    """Idempotently count one accepted label event toward the tenant's
    current-period usage.

    Must be called with the tenant's RLS GUC already set on ``session`` —
    the caller (``CanonicalEventStore.persist_event`` /
    ``persist_events_batch``) already does this before it calls here, and
    both statements below run inside that same caller-owned transaction.

    Two statements:

      1. ``INSERT INTO billing.tenant_usage_event_ledger ...
         ON CONFLICT (tenant_id, event_id) DO NOTHING RETURNING event_id``
         — the idempotency guard. A retried call for the same
         ``event_id`` (e.g. a retried webhook after the DB commit but
         before the HTTP response reached the caller) returns zero rows
         here and stops.
      2. Only if (1) claimed a new row: upsert
         ``billing.tenant_usage_counters.unit_count += 1`` for the
         event's billing period.

    Returns ``True`` if this call incremented the counter, ``False`` if
    the event was already counted (idempotent no-op). Never raises for a
    duplicate; only propagates genuine DB errors, so a failure here rolls
    back the caller's whole ``persist_event`` transaction — the label
    count and the persisted event stay atomically in sync, never drifting
    apart.
    """
    as_of = event_timestamp.date() if isinstance(event_timestamp, datetime) else event_timestamp
    period_start, period_end = _current_billing_period(as_of)

    claimed = session.execute(
        text("""
            INSERT INTO billing.tenant_usage_event_ledger (
                tenant_id, event_id, billing_period_start
            ) VALUES (:tenant_id, :event_id, :period_start)
            ON CONFLICT (tenant_id, event_id) DO NOTHING
            RETURNING event_id
        """),
        {
            "tenant_id": tenant_id,
            "event_id": event_id,
            "period_start": period_start,
        },
    ).fetchone()

    if claimed is None:
        # Already counted for this tenant+event — idempotent no-op.
        return False

    session.execute(
        text("""
            INSERT INTO billing.tenant_usage_counters (
                tenant_id, billing_period_start, billing_period_end, unit_count
            ) VALUES (:tenant_id, :period_start, :period_end, 1)
            ON CONFLICT (tenant_id, billing_period_start)
            DO UPDATE SET
                unit_count = billing.tenant_usage_counters.unit_count + 1,
                updated_at = now()
        """),
        {
            "tenant_id": tenant_id,
            "period_start": period_start,
            "period_end": period_end,
        },
    )
    return True
