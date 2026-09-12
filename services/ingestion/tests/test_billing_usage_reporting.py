"""Unit tests for ``app.stripe_billing.usage_reporting`` (DESIGN_metering-
billing.md §5): pushing accumulated per-tenant label usage to Stripe's
Billing Meters API.

Monkeypatch-based, no live DB/Stripe network calls — ``stripe.billing.
MeterEvent.create`` and the Redis-backed subscription mapping lookup are
both replaced with fakes, matching the style of ``test_stripe_plans_1342.py``
/ ``test_billing_usage_routes.py``.
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
TODAY = date(2026, 9, 15)
PERIOD_START = date(2026, 9, 1)


class _Result:
    def __init__(self, row: Any = None) -> None:
        self._row = row

    def fetchone(self) -> Any:
        return self._row


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


@pytest.fixture(autouse=True)
def _fixed_period(monkeypatch):
    # Pin "today" so every test bucket lands in the same UTC calendar month
    # regardless of when the suite actually runs.
    monkeypatch.setattr(mod, "_current_billing_period", lambda: (PERIOD_START, date(2026, 10, 1)))


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

    def test_returns_none_when_no_counter_row_for_period(self, monkeypatch):
        monkeypatch.setattr(mod._state_mod, "_get_subscription_mapping", lambda tid: _mapping())
        session = _FakeSession(results=[_Result(row=None)])

        result = mod.report_tenant_usage_to_stripe(session, TENANT_ID)

        assert result is None
        assert not session.committed

    def test_returns_none_when_nothing_new_since_last_report(self, monkeypatch):
        monkeypatch.setattr(mod._state_mod, "_get_subscription_mapping", lambda tid: _mapping())
        # unit_count == last_reported_count => delta 0.
        session = _FakeSession(results=[_Result(row=(42, 42))])

        result = mod.report_tenant_usage_to_stripe(session, TENANT_ID)

        assert result is None
        assert not session.committed

    def test_returns_none_when_delta_is_negative(self, monkeypatch):
        # Defensive floor: a corrected/negative delta must not be reported.
        monkeypatch.setattr(mod._state_mod, "_get_subscription_mapping", lambda tid: _mapping())
        session = _FakeSession(results=[_Result(row=(10, 42))])

        result = mod.report_tenant_usage_to_stripe(session, TENANT_ID)

        assert result is None
        assert not session.committed


# ---------------------------------------------------------------------------
# Successful report
# ---------------------------------------------------------------------------


class TestReportTenantUsageSuccess:
    def test_reports_only_the_delta_and_advances_high_water_mark(self, monkeypatch):
        monkeypatch.setattr(mod._state_mod, "_get_subscription_mapping", lambda tid: _mapping())
        session = _FakeSession(results=[_Result(row=(42, 30))])

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
            "billing_period_start": "2026-09-01",
            "reported_delta": 12,
            "unit_count": 42,
            "identifier": f"{TENANT_ID}:2026-09-01:42",
            "meter_event_id": "mtr_evt_1",
        }
        assert session.committed is True

        # The counter row is read FOR UPDATE (concurrency guard) ...
        select_sql, select_params = session.calls[0]
        assert "FOR UPDATE" in select_sql.upper()
        assert select_params == {"tenant_id": TENANT_ID, "period_start": PERIOD_START}
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
            session = _FakeSession(results=[_Result(row=(42, 30))])
            mod.report_tenant_usage_to_stripe(session, TENANT_ID)

        assert identifiers[0] == identifiers[1]


# ---------------------------------------------------------------------------
# Stripe error handling
# ---------------------------------------------------------------------------


class TestReportTenantUsageStripeError:
    def test_stripe_error_is_reraised_and_high_water_mark_not_advanced(self, monkeypatch):
        monkeypatch.setattr(mod._state_mod, "_get_subscription_mapping", lambda tid: _mapping())
        session = _FakeSession(results=[_Result(row=(42, 30))])

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
