"""Unit tests for ``app.stripe_billing.usage_reporting`` (DESIGN_metering-
billing.md §5): pushing accumulated per-tenant label usage to Stripe's
Billing Meters API.

Monkeypatch-based, no live DB/Stripe network calls — ``stripe.billing.
MeterEvent.create`` and the Redis-backed subscription mapping lookup are
both replaced with fakes, matching the style of ``test_stripe_plans_1342.py``
/ ``test_billing_usage_routes.py``.

Security-review fix: ``report_tenant_usage_to_stripe`` used to look only at
the tenant's *current* UTC-calendar-month counter row, silently skipping
any past-period row with outstanding usage (e.g. from a backfilled or
deliberately backdated ``event_timestamp`` — see
``services/shared/canonical_event.py``'s ``parse_timestamp``). It now
selects every period with ``unit_count > last_reported_count`` and reports
each. These tests exercise that multi-period behavior directly.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any, List, Optional

import pytest
import stripe

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.stripe_billing import usage_reporting as mod  # noqa: E402

TENANT_ID = "tenant-reporting-1"
PERIOD_START = date(2026, 9, 1)
PAST_PERIOD_START = date(2026, 7, 1)


class _Result:
    """Fake SQLAlchemy result: supports both ``fetchall`` (the outstanding-
    periods SELECT) and ``fetchone`` (unused by the current implementation,
    kept for shape-compatibility with other fakes in this test suite)."""

    def __init__(self, rows: Optional[List[Any]] = None) -> None:
        self._rows = list(rows or [])

    def fetchall(self) -> List[Any]:
        return list(self._rows)

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, results: Optional[List[_Result]] = None) -> None:
        self._results = list(results or [])
        self._call_index = 0
        self.calls: List[tuple] = []
        self.committed = False

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        if self._call_index < len(self._results):
            result = self._results[self._call_index]
            self._call_index += 1
            return result
        return _Result()

    def commit(self) -> None:
        self.committed = True


def _mapping(**overrides):
    base = {"plan_id": "growth", "metered_billing_enabled": "true", "customer_id": "cus_123"}
    base.update(overrides)
    return base


def _select_result(*period_rows: tuple) -> _Result:
    """Build the fake result for the outstanding-periods SELECT.

    Each ``period_rows`` entry is ``(period_start, unit_count, last_reported_count)``.
    """
    return _Result(rows=list(period_rows))


# ---------------------------------------------------------------------------
# No-op branches
# ---------------------------------------------------------------------------


class TestReportTenantUsageNoOps:
    def test_returns_none_when_not_opted_into_metered_billing(self, monkeypatch):
        monkeypatch.setattr(mod._state_mod, "_get_subscription_mapping", lambda tid: _mapping(metered_billing_enabled="false"))
        session = _FakeSession()

        result = mod.report_tenant_usage_to_stripe(session, TENANT_ID)

        assert result is None
        assert session.calls == []  # never touches the DB if not opted in

    def test_returns_none_when_no_stripe_customer_linked(self, monkeypatch):
        monkeypatch.setattr(
            mod._state_mod, "_get_subscription_mapping", lambda tid: _mapping(customer_id=None)
        )
        session = _FakeSession()

        result = mod.report_tenant_usage_to_stripe(session, TENANT_ID)

        assert result is None
        assert session.calls == []

    def test_returns_none_when_no_periods_have_outstanding_usage(self, monkeypatch):
        monkeypatch.setattr(mod._state_mod, "_get_subscription_mapping", lambda tid: _mapping())
        session = _FakeSession(results=[_select_result()])

        result = mod.report_tenant_usage_to_stripe(session, TENANT_ID)

        assert result is None
        assert not session.committed


# ---------------------------------------------------------------------------
# Successful report — single (current) period, matching pre-fix behavior
# ---------------------------------------------------------------------------


class TestReportTenantUsageSuccessSinglePeriod:
    def test_reports_only_the_delta_and_advances_high_water_mark(self, monkeypatch):
        monkeypatch.setattr(mod._state_mod, "_get_subscription_mapping", lambda tid: _mapping())
        session = _FakeSession(results=[_select_result((PERIOD_START, 42, 30))])

        captured = {}

        class _MeterEvent:
            identifier = "mtr_evt_1"

        def _fake_create(*, event_name, payload, identifier):
            captured["event_name"] = event_name
            captured["payload"] = payload
            captured["identifier"] = identifier
            return _MeterEvent()

        monkeypatch.setattr(stripe.billing.MeterEvent, "create", _fake_create)

        result = mod.report_tenant_usage_to_stripe(session, TENANT_ID)

        assert captured["event_name"] == mod.METER_EVENT_NAME
        assert captured["payload"] == {"stripe_customer_id": "cus_123", "value": "12"}
        assert captured["identifier"] == f"{TENANT_ID}:2026-09-01:42"

        assert result == {
            "tenant_id": TENANT_ID,
            "periods_reported": 1,
            "total_reported_delta": 12,
            "reported_periods": [
                {
                    "billing_period_start": "2026-09-01",
                    "reported_delta": 12,
                    "unit_count": 42,
                    "identifier": f"{TENANT_ID}:2026-09-01:42",
                    "meter_event_id": "mtr_evt_1",
                }
            ],
        }
        assert session.committed is True

        # The counter rows are read FOR UPDATE (concurrency guard) ...
        select_sql, select_params = session.calls[0]
        assert "FOR UPDATE" in select_sql.upper()
        assert select_params == {"tenant_id": TENANT_ID}
        # ... and the high-water mark advances to the new cumulative count,
        # not just by the delta.
        update_sql, update_params = session.calls[1]
        assert "last_reported_count" in update_sql
        assert update_params == {
            "tenant_id": TENANT_ID,
            "unit_count": 42,
            "period_start": PERIOD_START,
        }

    def test_identifier_is_stable_for_same_cumulative_count(self, monkeypatch):
        # Same (tenant, period, unit_count) must always produce the same
        # Stripe idempotency identifier, so a retried call dedupes Stripe-side.
        monkeypatch.setattr(mod._state_mod, "_get_subscription_mapping", lambda tid: _mapping())

        identifiers = []

        def _fake_create(*, event_name, payload, identifier):
            identifiers.append(identifier)

            class _MeterEvent:
                pass

            return _MeterEvent()

        monkeypatch.setattr(stripe.billing.MeterEvent, "create", _fake_create)

        for _ in range(2):
            session = _FakeSession(results=[_select_result((PERIOD_START, 42, 30))])
            mod.report_tenant_usage_to_stripe(session, TENANT_ID)

        assert identifiers[0] == identifiers[1]


# ---------------------------------------------------------------------------
# Successful report — multiple periods (the security-review fix)
# ---------------------------------------------------------------------------


class TestReportTenantUsageSuccessMultiPeriod:
    def test_reports_a_past_period_alongside_the_current_one(self, monkeypatch):
        # A backfilled/backdated event landed in PAST_PERIOD_START's counter
        # row via increment_usage_for_event. Before the fix, only the
        # current-period row was ever read here, so this usage would be
        # permanently unbilled.
        monkeypatch.setattr(mod._state_mod, "_get_subscription_mapping", lambda tid: _mapping())
        session = _FakeSession(
            results=[
                _select_result(
                    (PAST_PERIOD_START, 5, 0),
                    (PERIOD_START, 42, 30),
                )
            ]
        )

        created = []

        def _fake_create(*, event_name, payload, identifier):
            created.append({"identifier": identifier, "payload": payload})

            class _MeterEvent:
                pass

            return _MeterEvent()

        monkeypatch.setattr(stripe.billing.MeterEvent, "create", _fake_create)

        result = mod.report_tenant_usage_to_stripe(session, TENANT_ID)

        assert len(created) == 2
        assert created[0]["identifier"] == f"{TENANT_ID}:2026-07-01:5"
        assert created[0]["payload"] == {"stripe_customer_id": "cus_123", "value": "5"}
        assert created[1]["identifier"] == f"{TENANT_ID}:2026-09-01:42"
        assert created[1]["payload"] == {"stripe_customer_id": "cus_123", "value": "12"}

        assert result["periods_reported"] == 2
        assert result["total_reported_delta"] == 17
        assert [p["billing_period_start"] for p in result["reported_periods"]] == [
            "2026-07-01",
            "2026-09-01",
        ]
        assert session.committed is True

        # One UPDATE per reported period, both after the single locking SELECT.
        update_calls = [c for c in session.calls if c[0].strip().upper().startswith("UPDATE")]
        assert len(update_calls) == 2
        assert update_calls[0][1] == {
            "tenant_id": TENANT_ID,
            "unit_count": 5,
            "period_start": PAST_PERIOD_START,
        }
        assert update_calls[1][1] == {
            "tenant_id": TENANT_ID,
            "unit_count": 42,
            "period_start": PERIOD_START,
        }


# ---------------------------------------------------------------------------
# Stripe error handling
# ---------------------------------------------------------------------------


class TestReportTenantUsageStripeError:
    def test_stripe_error_is_reraised_and_high_water_mark_not_advanced(self, monkeypatch):
        monkeypatch.setattr(mod._state_mod, "_get_subscription_mapping", lambda tid: _mapping())
        session = _FakeSession(results=[_select_result((PERIOD_START, 42, 30))])

        def _raise(**kwargs):
            raise stripe.error.StripeError("boom")

        monkeypatch.setattr(stripe.billing.MeterEvent, "create", _raise)

        with pytest.raises(stripe.error.StripeError):
            mod.report_tenant_usage_to_stripe(session, TENANT_ID)

        # Only the initial SELECT ... FOR UPDATE happened — no UPDATE to
        # last_reported_count, and no commit, so a retry resends the same
        # delta next time.
        assert len(session.calls) == 1
        assert session.committed is False

    def test_failure_on_a_later_period_does_not_roll_back_an_earlier_success(self, monkeypatch):
        # Bug (caught by review): the identifier embeds the period's
        # *current* unit_count, which keeps growing as new events land in
        # between separate invocations — it is NOT stable across a failed
        # attempt and a later retry. So if a later period's StripeError
        # rolled back an earlier period's already-succeeded update, a
        # retry after that failure would recompute a DIFFERENT identifier
        # for the earlier period (since unit_count grew) and Stripe would
        # not dedupe it, double-reporting (over-billing) that period.
        # The fix: commit each period's advance immediately after its own
        # Stripe call succeeds, so an earlier success is never undone by a
        # later failure in the same call.
        monkeypatch.setattr(mod._state_mod, "_get_subscription_mapping", lambda tid: _mapping())
        session = _FakeSession(
            results=[
                _select_result(
                    (PAST_PERIOD_START, 5, 0),
                    (PERIOD_START, 42, 30),
                )
            ]
        )

        call_count = {"n": 0}

        def _flaky_create(*, event_name, payload, identifier):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise stripe.error.StripeError("boom")

            class _MeterEvent:
                pass

            return _MeterEvent()

        monkeypatch.setattr(stripe.billing.MeterEvent, "create", _flaky_create)

        with pytest.raises(stripe.error.StripeError):
            mod.report_tenant_usage_to_stripe(session, TENANT_ID)

        # The first period's Stripe call succeeded and must be durably
        # committed even though the second period then failed.
        assert session.committed is True
        update_calls = [c for c in session.calls if "UPDATE billing.tenant_usage_counters" in c[0]]
        assert len(update_calls) == 1
        assert update_calls[0][1] == {
            "tenant_id": TENANT_ID,
            "unit_count": 5,
            "period_start": PAST_PERIOD_START,
        }
