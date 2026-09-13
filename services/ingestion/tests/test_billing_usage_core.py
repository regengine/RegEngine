"""Unit tests for ``app.stripe_billing.usage`` (DESIGN_metering-billing.md
§4): the per-label metered usage counting primitive.

Monkeypatch-based, no live DB — matches the style of
``test_stripe_plans_1342.py`` / ``test_billing_usage_routes.py``: a fake
SQLAlchemy ``Session`` records every ``execute()`` call and returns queued
results, so the idempotency / upsert logic is exercised without Postgres.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.stripe_billing.usage import (  # noqa: E402
    _current_billing_period,
    increment_usage_for_event,
)

TENANT_ID = "tenant-usage-core-1"


class _Result:
    def __init__(self, row: Any = None) -> None:
        self._row = row

    def fetchone(self) -> Any:
        return self._row


class _FakeSession:
    """Programmable fake session: queued ``execute()`` results, every call
    recorded (SQL text + params) for assertions — mirrors the
    ``_FakeSession`` pattern in ``test_billing_usage_routes.py``.
    """

    def __init__(self, results: Optional[List[_Result]] = None) -> None:
        self._results = list(results or [])
        self._call_index = 0
        self.calls: List[tuple] = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        if self._call_index < len(self._results):
            result = self._results[self._call_index]
            self._call_index += 1
            return result
        return _Result()


# ---------------------------------------------------------------------------
# _current_billing_period
# ---------------------------------------------------------------------------


class TestCurrentBillingPeriod:
    def test_mid_month_buckets_to_first_of_month(self):
        start, end = _current_billing_period(date(2026, 9, 15))
        assert start == date(2026, 9, 1)
        assert end == date(2026, 10, 1)

    def test_first_of_month_is_its_own_bucket_start(self):
        start, end = _current_billing_period(date(2026, 9, 1))
        assert start == date(2026, 9, 1)
        assert end == date(2026, 10, 1)

    def test_december_rolls_over_to_next_january(self):
        # Year-boundary edge case: month+1 must not become month 13.
        start, end = _current_billing_period(date(2026, 12, 25))
        assert start == date(2026, 12, 1)
        assert end == date(2027, 1, 1)

    def test_defaults_to_today_utc_when_as_of_omitted(self, monkeypatch):
        fixed_now = datetime(2026, 6, 10, 23, 59, tzinfo=timezone.utc)

        class _FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now

        monkeypatch.setattr("app.stripe_billing.usage.datetime", _FixedDatetime)
        start, end = _current_billing_period()
        assert start == date(2026, 6, 1)
        assert end == date(2026, 7, 1)


# ---------------------------------------------------------------------------
# increment_usage_for_event
# ---------------------------------------------------------------------------


class TestIncrementUsageForEvent:
    def test_new_event_claims_ledger_and_upserts_counter(self):
        session = _FakeSession(results=[_Result(row=("evt-1",))])

        claimed = increment_usage_for_event(
            session,
            tenant_id=TENANT_ID,
            event_id="evt-1",
            event_timestamp=date(2026, 9, 15),
        )

        assert claimed is True
        assert len(session.calls) == 2

        ledger_sql, ledger_params = session.calls[0]
        assert "tenant_usage_event_ledger" in ledger_sql
        assert "ON CONFLICT" in ledger_sql.upper()
        assert "DO NOTHING" in ledger_sql.upper()
        assert ledger_params == {
            "tenant_id": TENANT_ID,
            "event_id": "evt-1",
            "period_start": date(2026, 9, 1),
        }

        counter_sql, counter_params = session.calls[1]
        assert "tenant_usage_counters" in counter_sql
        assert "unit_count = billing.tenant_usage_counters.unit_count + 1" in counter_sql
        assert counter_params == {
            "tenant_id": TENANT_ID,
            "period_start": date(2026, 9, 1),
            "period_end": date(2026, 10, 1),
        }

    def test_duplicate_event_is_idempotent_noop(self):
        # ON CONFLICT DO NOTHING RETURNING yields zero rows for a replay.
        session = _FakeSession(results=[_Result(row=None)])

        claimed = increment_usage_for_event(
            session,
            tenant_id=TENANT_ID,
            event_id="evt-already-counted",
            event_timestamp=date(2026, 9, 15),
        )

        assert claimed is False
        # Only the ledger INSERT ran — the counter upsert must be skipped
        # for an already-counted event, or usage would double-count.
        assert len(session.calls) == 1
        assert "tenant_usage_event_ledger" in session.calls[0][0]

    def test_accepts_datetime_event_timestamp(self):
        session = _FakeSession(results=[_Result(row=("evt-2",))])

        increment_usage_for_event(
            session,
            tenant_id=TENANT_ID,
            event_id="evt-2",
            event_timestamp=datetime(2026, 9, 30, 23, 0, tzinfo=timezone.utc),
        )

        _ledger_sql, ledger_params = session.calls[0]
        assert ledger_params["period_start"] == date(2026, 9, 1)

    def test_event_near_month_boundary_buckets_by_its_own_date(self):
        # An event timestamped on the last day of the month must land in
        # that month's bucket, not "today"'s.
        session = _FakeSession(results=[_Result(row=("evt-3",))])

        increment_usage_for_event(
            session,
            tenant_id=TENANT_ID,
            event_id="evt-3",
            event_timestamp=date(2026, 1, 31),
        )

        _ledger_sql, ledger_params = session.calls[0]
        counter_sql, counter_params = session.calls[1]
        assert ledger_params["period_start"] == date(2026, 1, 1)
        assert counter_params["period_end"] == date(2026, 2, 1)

    def test_non_utc_offset_is_converted_to_utc_before_bucketing(self):
        # 11:30pm US/Pacific (UTC-08:00) on Jan 31 is already Feb 1 in UTC.
        # Bucketing must use the UTC calendar day, per
        # DESIGN_metering-billing.md §3.3 ("UTC calendar-month buckets") —
        # not the source's own local calendar day.
        from datetime import timedelta, timezone as dt_timezone

        pacific = dt_timezone(timedelta(hours=-8))
        session = _FakeSession(results=[_Result(row=("evt-tz",))])

        increment_usage_for_event(
            session,
            tenant_id=TENANT_ID,
            event_id="evt-tz",
            event_timestamp=datetime(2026, 1, 31, 23, 30, tzinfo=pacific),
        )

        _ledger_sql, ledger_params = session.calls[0]
        counter_sql, counter_params = session.calls[1]
        assert ledger_params["period_start"] == date(2026, 2, 1)
        assert counter_params["period_end"] == date(2026, 3, 1)

    def test_naive_datetime_is_treated_as_already_utc(self):
        # Mirrors canonical_event.py's own parse_timestamp validator: a
        # naive datetime is assumed UTC, never shifted by the local clock.
        session = _FakeSession(results=[_Result(row=("evt-naive",))])

        increment_usage_for_event(
            session,
            tenant_id=TENANT_ID,
            event_id="evt-naive",
            event_timestamp=datetime(2026, 9, 15, 12, 0),
        )

        _ledger_sql, ledger_params = session.calls[0]
        assert ledger_params["period_start"] == date(2026, 9, 1)
