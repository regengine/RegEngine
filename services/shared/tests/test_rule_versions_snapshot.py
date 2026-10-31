"""Unit tests for ``shared.rules.versions.snapshot_rule_versions`` (S7).

No live database: a fake session answers the catalog and evaluated-version
queries in order. The snapshot feeds the FDA export package and the
request-workflow package, so the contract under test is that it always
returns a serialisable dict, states what it could not read, and only
queries evaluations when told which tenant and events to look at.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from shared.rules import versions as mod


class _Result:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def mappings(self):
        return self

    def fetchall(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, *results: Any):
        self._results = list(results)
        self.calls: list[tuple[str, dict | None]] = []

    def execute(self, stmt, params=None):
        self.calls.append((str(getattr(stmt, "text", stmt)), params))
        nxt = self._results.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return _Result(nxt)


class _SavepointSession(_FakeSession):
    """Fake session with ``begin_nested``; records every savepoint enter/exit."""

    def __init__(self, *results: Any):
        super().__init__(*results)
        self.savepoints: list[str] = []

    def begin_nested(self):
        session = self

        class _Savepoint:
            def __enter__(self_inner):
                session.savepoints.append("enter")
                return self_inner

            def __exit__(self_inner, exc_type, exc, tb):
                session.savepoints.append("exit:rollback" if exc_type else "exit:commit")
                return False

        return _Savepoint()


_CATALOG_ROWS = [
    {"rule_id": "rule-a", "rule_version": 3, "title": "A", "severity": "critical", "category": "kde"},
    {"rule_id": "rule-b", "rule_version": 1, "title": "B", "severity": "warning", "category": "cte"},
]


@pytest.fixture(autouse=True)
def _enforce_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")


def test_catalog_only_when_no_events_requested() -> None:
    sess = _FakeSession(_CATALOG_ROWS)
    snap = mod.snapshot_rule_versions(sess)
    assert snap["catalog_status"] == "ok"
    assert snap["catalog"]["rule-a"] == {"version": 3, "title": "A", "severity": "critical", "category": "kde"}
    assert snap["catalog"]["rule-b"]["version"] == 1
    assert snap["evaluated"] == []
    assert snap["evaluated_status"] == "not_requested"
    assert snap["enforcement_mode"] == "off"
    assert snap["snapshot_at"].endswith("+00:00")
    assert len(sess.calls) == 1, "no evaluations query without tenant + event ids"
    json.dumps(snap)  # serialisable


def test_evaluated_versions_are_tenant_scoped_and_counted() -> None:
    sess = _FakeSession(
        _CATALOG_ROWS,
        [
            {"rule_id": "rule-a", "rule_version": 2, "evaluation_count": 5},
            {"rule_id": "rule-a", "rule_version": 3, "evaluation_count": 1},
        ],
    )
    snap = mod.snapshot_rule_versions(sess, tenant_id="tenant-1", event_ids=["e1", "e2", None, ""])
    assert snap["evaluated_status"] == "ok"
    assert snap["evaluated"] == [
        {"rule_id": "rule-a", "rule_version": 2, "evaluation_count": 5},
        {"rule_id": "rule-a", "rule_version": 3, "evaluation_count": 1},
    ]
    sql, params = sess.calls[1]
    assert "fsma.rule_evaluations" in sql
    assert "tenant_id = CAST(:tid AS uuid)" in sql
    assert params == {"tid": "tenant-1", "event_ids": ["e1", "e2"]}


def test_evaluated_skipped_without_tenant() -> None:
    sess = _FakeSession(_CATALOG_ROWS)
    snap = mod.snapshot_rule_versions(sess, tenant_id=None, event_ids=["e1"])
    assert snap["evaluated_status"] == "not_requested"
    assert len(sess.calls) == 1


def test_catalog_failure_degrades_not_raises() -> None:
    sess = _FakeSession(RuntimeError("relation does not exist"), [{"rule_id": "r", "rule_version": 1, "evaluation_count": 1}])
    snap = mod.snapshot_rule_versions(sess, tenant_id="t", event_ids=["e"])
    assert snap["catalog"] == {}
    assert snap["catalog_status"] == "unavailable"
    # The evaluated query still runs and succeeds independently.
    assert snap["evaluated_status"] == "ok"


def test_each_read_runs_in_its_own_savepoint() -> None:
    """A failed catalog read is rolled back on its own savepoint.

    On PostgreSQL a failed statement aborts the enclosing transaction, so
    without the savepoint the evaluated read (and every later query on the
    caller's session) would fail too. The evaluated read must still run,
    in a second savepoint, and succeed independently.
    """
    sess = _SavepointSession(
        RuntimeError("relation does not exist"),
        [{"rule_id": "r", "rule_version": 1, "evaluation_count": 1}],
    )
    snap = mod.snapshot_rule_versions(sess, tenant_id="t", event_ids=["e"])
    assert snap["catalog_status"] == "unavailable"
    assert snap["catalog"] == {}
    assert snap["evaluated_status"] == "ok"
    assert snap["evaluated"] == [{"rule_id": "r", "rule_version": 1, "evaluation_count": 1}]
    assert len(sess.calls) == 2
    assert sess.savepoints == ["enter", "exit:rollback", "enter", "exit:commit"]


def test_evaluated_failure_degrades_not_raises() -> None:
    sess = _FakeSession(_CATALOG_ROWS, RuntimeError("timeout"))
    snap = mod.snapshot_rule_versions(sess, tenant_id="t", event_ids=["e"])
    assert snap["catalog_status"] == "ok"
    assert snap["evaluated"] == []
    assert snap["evaluated_status"] == "unavailable"


def test_enforcement_mode_reflects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")
    snap = mod.snapshot_rule_versions(_FakeSession([]))
    assert snap["enforcement_mode"] == "cte_only"
