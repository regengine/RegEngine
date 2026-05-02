"""Tenant-context regressions for ``shared.exception_queue``.

The exception queue is written both from API routes and webhook/rules
post-processing. Each public method must set the Postgres RLS tenant GUC
itself so callers cannot accidentally touch FORCE RLS tables without context.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from services.shared.exception_queue import ExceptionQueueService
from services.shared.rules.types import EvaluationSummary, RuleEvaluationResult


TENANT_ID = "11111111-1111-1111-1111-111111111111"


class _FakeResult:
    def __init__(self, *, row: tuple[Any, ...] | None = None, rows: list[tuple[Any, ...]] | None = None, rowcount: int = 1):
        self._row = row
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _FakeSession:
    def __init__(self, calls: list[str]):
        self.calls = calls

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.calls.append(f"execute:{sql.split()[0].upper()}")
        if "COUNT(*)" in sql:
            return _FakeResult(row=(3,))
        if "FROM fsma.exception_comments" in sql:
            return _FakeResult(rows=[])
        if "FROM fsma.exception_cases" in sql:
            return _FakeResult(row=_case_row())
        return _FakeResult()


def _case_row() -> tuple[Any, ...]:
    now = datetime.now(timezone.utc)
    return (
        "case-1",
        TENANT_ID,
        "critical",
        "open",
        ["evt-1"],
        ["eval-1"],
        None,
        now,
        "Supplier",
        "Facility",
        "kde",
        "Fix it",
        None,
        None,
        None,
        None,
        None,
        now,
        now,
        None,
    )


@pytest.fixture()
def calls(monkeypatch) -> list[str]:
    observed: list[str] = []

    def _set_tenant_guc(_session, tenant_id: str) -> None:
        observed.append(f"set:{tenant_id}")

    from services.shared import tenant_context

    monkeypatch.setattr(tenant_context, "set_tenant_guc", _set_tenant_guc)
    return observed


def test_read_methods_set_tenant_context_before_query(calls):
    svc = ExceptionQueueService(_FakeSession(calls))

    svc.get_exception(TENANT_ID, "case-1")
    svc.list_exceptions(TENANT_ID)
    svc.get_unresolved_blocking_count(TENANT_ID)
    svc.list_comments(TENANT_ID, "case-1")

    first_execute = calls.index("execute:SELECT")
    assert calls[0] == f"set:{TENANT_ID}"
    assert first_execute > 0
    assert calls.count(f"set:{TENANT_ID}") >= 4


def test_create_exception_sets_tenant_context_before_insert(calls):
    svc = ExceptionQueueService(_FakeSession(calls))

    case = svc.create_exception(
        tenant_id=TENANT_ID,
        severity="critical",
        rule_category="kde",
        linked_event_ids=["evt-1"],
        linked_rule_evaluation_ids=["eval-1"],
    )

    assert case.case_id == "case-1"
    assert calls[0] == f"set:{TENANT_ID}"
    assert calls[1] == "execute:INSERT"


def test_create_exceptions_from_evaluation_sets_context_on_persist(calls):
    svc = ExceptionQueueService(_FakeSession(calls))
    result = RuleEvaluationResult(
        evaluation_id="eval-1",
        rule_id="rule-1",
        rule_title="Missing ship date",
        category="kde",
        severity="critical",
        result="fail",
        why_failed="ship_date missing",
        remediation_suggestion="Add ship_date.",
    )
    summary = EvaluationSummary(
        event_id="evt-1",
        total_rules=1,
        failed=1,
        results=[result],
        critical_failures=[result],
    )

    created = svc.create_exceptions_from_evaluation(TENANT_ID, summary)

    assert len(created) == 1
    assert calls[0] == f"set:{TENANT_ID}"
    assert "execute:INSERT" in calls
