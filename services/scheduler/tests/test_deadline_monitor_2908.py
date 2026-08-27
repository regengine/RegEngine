"""Regression tests for #2908 — deadline monitor fan-out and alert storm.

The job fires 288 times a day inside the production API process and had
two coupled defects:

1. **Stateless alerting** (the half that bites today). An FDA request
   case that goes overdue *stays* overdue by definition, so it re-emitted
   an identical ERROR every 5 minutes forever — 288 events per case per
   day into Sentry and the log stream, burying genuinely new breaches
   under a permanent stream of repeats and making the ERROR channel
   useless for exactly the signal the job exists to raise.

2. **Query fan-out.** `SELECT id FROM public.tenants` unbounded, one
   `check_deadline_status` call per tenant, each returning every
   non-submitted case with no LIMIT, all on one session drawn from the
   pool that serves API traffic — and the job registered without
   `max_instances=1`, so a tick that overruns 5 minutes stacks.

Dedupe must never *drop* the overdue condition: the summary still counts
every overdue case on every tick, and a suppressed repeat is logged at
DEBUG plus re-notified on a cadence.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# tenant_scope / set_tenant_guc validate the tenant id as a UUID, so the
# harness has to use real ones.
TENANT_A = "11111111-1111-4111-8111-111111111111"
TENANT_B = "22222222-2222-4222-8222-222222222222"


def _tenant(i: int) -> str:
    return f"33333333-3333-4333-8333-{i:012d}"


def _build_scheduler_service_without_init():
    from services.scheduler import service as scheduler_service

    with (
        patch.object(scheduler_service, "get_kafka_producer", return_value=MagicMock()),
        patch.object(scheduler_service, "WebhookNotifier", return_value=MagicMock()),
        patch.object(scheduler_service, "DistributedContext", return_value=MagicMock()),
        patch.object(scheduler_service, "StateManager", return_value=MagicMock()),
        patch.object(scheduler_service, "FDAImportAlertsScraper", return_value=MagicMock()),
        patch.object(scheduler_service, "FDARecallsScraper", return_value=MagicMock()),
        patch.object(scheduler_service, "FDAWarningLettersScraper", return_value=MagicMock()),
        patch.object(scheduler_service, "BlockingScheduler", return_value=MagicMock()),
    ):
        return scheduler_service.SchedulerService()


def _case(case_id, urgency="overdue", hours=-3.0):
    return {
        "request_case_id": case_id,
        "package_status": "in_progress",
        "requesting_party": "FDA",
        "scope_description": "lot trace",
        "response_due_at": "2026-08-01T00:00:00+00:00",
        "hours_remaining": hours,
        "urgency": urgency,
        "gap_count": 0,
        "active_exception_count": 0,
    }


class _Harness:
    """Drives check_request_deadlines against a fake DB + workflow."""

    def __init__(self, tenants, cases_by_tenant):
        self.tenants = tenants
        self.cases_by_tenant = cases_by_tenant
        self.sql_statements = []
        self.workflow_calls = []

    def _execute(self, statement, params=None):
        self.sql_statements.append((str(statement), params))
        result = MagicMock()
        result.fetchall.return_value = [(t,) for t in self.tenants]
        return result

    def run(self, svc, ticks=1):
        from services.scheduler import service as scheduler_service

        db = MagicMock()
        db.execute.side_effect = self._execute

        workflow = MagicMock()

        def _check(tid, *args, **kwargs):
            self.workflow_calls.append(tid)
            return list(self.cases_by_tenant.get(tid, []))

        workflow.check_deadline_status.side_effect = _check

        records = []

        def _record(level):
            def _log(event, **kwargs):
                records.append((level, event, kwargs))

            return _log

        with (
            patch("shared.database.SessionLocal", return_value=db),
            patch("shared.request_workflow.RequestWorkflow", return_value=workflow),
            patch.object(scheduler_service.logger, "error", side_effect=_record("error")),
            patch.object(scheduler_service.logger, "warning", side_effect=_record("warning")),
            patch.object(scheduler_service.logger, "info", side_effect=_record("info")),
            patch.object(scheduler_service.logger, "debug", side_effect=_record("debug")),
        ):
            for _ in range(ticks):
                svc.check_request_deadlines()

        return records


def _events(records, level, name):
    return [r for r in records if r[0] == level and r[1] == name]


# ---------------------------------------------------------------------------
# Half 1 — alert state machine
# ---------------------------------------------------------------------------


class TestOverdueAlertIsDeduped:
    def test_persistently_overdue_case_errors_once_across_three_ticks(self):
        """#2908 acceptance criterion 1."""
        svc = _build_scheduler_service_without_init()
        harness = _Harness([TENANT_A], {TENANT_A: [_case("case-1")]})

        records = harness.run(svc, ticks=3)

        errors = _events(records, "error", "deadline_overdue")
        assert len(errors) == 1, (
            "a case that stays overdue must ERROR once on transition, not on "
            f"every 5-minute tick (288/day/case forever); got {len(errors)} "
            "errors across 3 ticks"
        )

    def test_repeat_ticks_still_observe_the_case(self):
        """Dedupe must not DROP the condition — only stop re-shouting it."""
        svc = _build_scheduler_service_without_init()
        harness = _Harness([TENANT_A], {TENANT_A: [_case("case-1")]})

        records = harness.run(svc, ticks=3)

        summaries = _events(records, "warning", "deadline_monitor_summary")
        assert len(summaries) == 3, "every tick must still emit the aggregate summary"
        assert all(s[2].get("total_overdue") == 1 for s in summaries), (
            "the summary must keep counting the overdue case on every tick — "
            "suppressing the repeat ERROR must not hide the breach"
        )

        suppressed = _events(records, "debug", "deadline_overdue_repeat")
        assert len(suppressed) == 2, (
            f"suppressed repeats must still be recorded at DEBUG so the detail is recoverable; got {len(suppressed)}"
        )

    def test_a_second_case_going_overdue_still_errors(self):
        """A genuinely new breach must not be buried by an existing one."""
        svc = _build_scheduler_service_without_init()
        harness = _Harness([TENANT_A], {TENANT_A: [_case("case-1")]})
        harness.run(svc, ticks=2)

        harness.cases_by_tenant[TENANT_A] = [_case("case-1"), _case("case-2")]
        records = harness.run(svc, ticks=1)

        errors = _events(records, "error", "deadline_overdue")
        assert len(errors) == 1, "the newly overdue case must raise its own ERROR"
        assert errors[0][2]["case_id"] == "case-2"

    def test_case_that_recovers_and_relapses_alerts_again(self):
        """Alert state must clear when the case stops being overdue."""
        svc = _build_scheduler_service_without_init()
        harness = _Harness([TENANT_A], {TENANT_A: [_case("case-1")]})
        harness.run(svc, ticks=2)

        harness.cases_by_tenant[TENANT_A] = [_case("case-1", urgency="normal", hours=48.0)]
        harness.run(svc, ticks=1)

        harness.cases_by_tenant[TENANT_A] = [_case("case-1")]
        records = harness.run(svc, ticks=1)

        assert len(_events(records, "error", "deadline_overdue")) == 1, (
            "a case that recovered and went overdue again is a new breach"
        )

    def test_renotify_cadence_re_raises_after_the_window(self):
        """Suppression is a cooldown, not a permanent mute."""
        svc = _build_scheduler_service_without_init()
        harness = _Harness([TENANT_A], {TENANT_A: [_case("case-1")]})
        harness.run(svc, ticks=2)

        # Age the recorded alert past the re-notify window.
        svc._deadline_alert_state[TENANT_A][("overdue", "case-1")] -= svc.DEADLINE_RENOTIFY_SECONDS + 1

        records = harness.run(svc, ticks=1)
        errors = _events(records, "error", "deadline_overdue")
        assert len(errors) == 1, "an overdue case must be re-raised on the configured cadence"
        assert errors[0][2].get("renotify") is True

    def test_alert_state_is_bounded(self):
        """The dedupe cache must not grow without limit."""
        svc = _build_scheduler_service_without_init()
        assert svc.DEADLINE_ALERT_STATE_MAX > 0
        harness = _Harness(
            [TENANT_A],
            {TENANT_A: [_case(f"case-{i}") for i in range(svc.DEADLINE_ALERT_STATE_MAX + 25)]},
        )
        harness.run(svc, ticks=1)
        total = sum(len(bucket) for bucket in svc._deadline_alert_state.values())
        assert total <= svc.DEADLINE_ALERT_STATE_MAX
        assert svc._deadline_alert_entries == total, "the entry counter must track the buckets"

    def test_alert_state_is_bucketed_per_tenant(self):
        """Pruning must cost O(this tenant's cases), not O(all state).

        A flat dict forces a full scan per tenant on every tick — 5k
        tenants x 10k entries is a quadratic blow-up introduced while
        fixing a fan-out bug.
        """
        svc = _build_scheduler_service_without_init()
        harness = _Harness(
            [TENANT_A, TENANT_B],
            {TENANT_A: [_case("case-1")], TENANT_B: [_case("case-2")]},
        )
        harness.run(svc, ticks=1)

        assert set(svc._deadline_alert_state) == {TENANT_A, TENANT_B}
        assert ("overdue", "case-1") in svc._deadline_alert_state[TENANT_A]
        assert ("overdue", "case-2") in svc._deadline_alert_state[TENANT_B]

    def test_recovered_case_releases_its_state_entry(self):
        """Pruning must decrement the bounded-cache counter, not just delete."""
        svc = _build_scheduler_service_without_init()
        harness = _Harness([TENANT_A], {TENANT_A: [_case("case-1"), _case("case-2")]})
        harness.run(svc, ticks=1)
        assert svc._deadline_alert_entries == 2

        harness.cases_by_tenant[TENANT_A] = [_case("case-1")]
        harness.run(svc, ticks=1)
        assert svc._deadline_alert_entries == 1, (
            "a leaked counter would eventually evict live alerts and re-open the alert storm through the eviction path"
        )
        assert svc._deadline_alert_state[TENANT_A] == {
            k: v for k, v in svc._deadline_alert_state[TENANT_A].items() if k[1] == "case-1"
        }


class TestCriticalAlertIsDeduped:
    def test_critical_warning_is_also_deduped(self):
        svc = _build_scheduler_service_without_init()
        harness = _Harness([TENANT_A], {TENANT_A: [_case("case-1", urgency="critical", hours=1.0)]})

        records = harness.run(svc, ticks=3)

        criticals = _events(records, "warning", "deadline_critical")
        assert len(criticals) == 1, f"deadline_critical must dedupe like deadline_overdue; got {len(criticals)}"


# ---------------------------------------------------------------------------
# Half 2 — query fan-out
# ---------------------------------------------------------------------------


class TestQueryFanOut:
    def test_tenant_discovery_scan_is_bounded(self):
        svc = _build_scheduler_service_without_init()
        harness = _Harness([_tenant(i) for i in range(50)], {})
        harness.run(svc, ticks=1)

        tenant_sql = [s for s, _ in harness.sql_statements if "public.tenants" in s]
        assert tenant_sql, "expected a tenant discovery query"
        lowered = " ".join(tenant_sql[0].lower().split())
        assert "limit" in lowered, (
            "the tenant discovery scan must be bounded — an unbounded scan "
            f"grows tick duration and memory with tenant count.\nSQL: {tenant_sql[0]}"
        )
        assert "order by" in lowered, "a bounded scan needs a deterministic order"

    def test_truncated_tenant_scan_is_reported_loudly(self):
        """Silently skipping tenants on a compliance control is worse than slow."""
        svc = _build_scheduler_service_without_init()
        svc.DEADLINE_TENANT_SCAN_LIMIT = 5
        harness = _Harness([_tenant(i) for i in range(5)], {})
        records = harness.run(svc, ticks=1)

        assert _events(records, "error", "deadline_monitor_tenant_scan_truncated"), (
            "hitting the tenant cap must raise an ERROR — unmonitored tenants "
            "are unmonitored FDA deadlines, and that must never be silent"
        )

    def test_per_tenant_case_read_is_bounded(self):
        """#2908 acceptance criterion 3 — check_deadline_status carries a LIMIT."""
        from shared.request_workflow import RequestWorkflow

        db = MagicMock()
        db.execute.return_value.mappings.return_value.fetchall.return_value = []
        RequestWorkflow(db).check_deadline_status(TENANT_A)

        sql, params = db.execute.call_args.args[0], db.execute.call_args.args[1]
        lowered = " ".join(str(sql).lower().split())
        assert "limit" in lowered, (
            "check_deadline_status returns every non-submitted case with no "
            f"LIMIT — memory grows with open-case count.\nSQL: {sql}"
        )
        assert "limit" in params, "the LIMIT must be a bound parameter, not a literal"

    def test_case_read_truncation_is_reported_loudly(self):
        from shared.request_workflow import RequestWorkflow, assembly

        db = MagicMock()
        rows = [
            {
                "request_case_id": f"c{i}",
                "package_status": "in_progress",
                "requesting_party": "FDA",
                "scope_description": "x",
                "response_due_at": None,
                "hours_remaining": -1.0,
                "is_overdue": True,
                "gap_count": 0,
                "active_exception_count": 0,
            }
            for i in range(assembly.DEADLINE_STATUS_MAX_CASES)
        ]
        db.execute.return_value.mappings.return_value.fetchall.return_value = rows

        with patch.object(assembly.logger, "error") as log_error:
            RequestWorkflow(db).check_deadline_status(TENANT_A)

        assert any(c.args and c.args[0] == "deadline_status_truncated" for c in log_error.call_args_list), (
            "hitting the case LIMIT must be reported — silently dropping open "
            "FDA request cases from a deadline check is failing open"
        )

    def test_most_urgent_cases_survive_truncation(self):
        """Ordering must guarantee overdue cases are never the ones dropped."""
        from shared.request_workflow import RequestWorkflow

        db = MagicMock()
        db.execute.return_value.mappings.return_value.fetchall.return_value = []
        RequestWorkflow(db).check_deadline_status(TENANT_A)

        lowered = " ".join(str(db.execute.call_args.args[0]).lower().split())
        order_pos = lowered.find("order by response_due_at asc")
        limit_pos = lowered.find("limit")
        assert order_pos != -1 and limit_pos != -1
        assert order_pos < limit_pos, (
            "the LIMIT must be applied after ORDER BY response_due_at ASC so "
            "truncation drops the least urgent cases, never the overdue ones"
        )

    def test_deadline_monitor_registered_with_max_instances_one(self):
        """#2908 acceptance criterion 4."""
        svc = _build_scheduler_service_without_init()
        svc.scheduler = MagicMock()
        svc.schedule_jobs()

        jobs = {c.kwargs.get("id"): c.kwargs for c in svc.scheduler.add_job.call_args_list}
        assert "deadline_monitor" in jobs
        assert jobs["deadline_monitor"].get("max_instances") == 1, (
            "without max_instances=1 a tick that overruns the 5-minute "
            "interval stacks up to 3 concurrent passes, each holding "
            "connections from the API's pool"
        )


class TestFailureHandling:
    def test_db_outage_does_not_crash_the_scheduler(self):
        svc = _build_scheduler_service_without_init()
        with patch("shared.database.SessionLocal", side_effect=ConnectionError("pg down")):
            svc.check_request_deadlines()
