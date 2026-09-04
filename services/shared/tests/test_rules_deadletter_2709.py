"""WS-8 (#2709): durable dead-letter for rule-evaluation persistence.

Covers the writer (engine salvage path copies still-failing rows into
``fsma.rule_evaluation_deadletter``) and the replayer
(``deadletter_replay``: idempotent re-insert, attempt bumping, parking,
tenant iteration).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

_SHARED_DIR = Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SHARED_DIR.parent
for _p in (_SHARED_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.rules import deadletter_replay as replay_mod  # noqa: E402
from shared.rules.engine import RulesEngine  # noqa: E402
from shared.rules.types import RuleEvaluationResult  # noqa: E402


def _result(rule_id: str) -> RuleEvaluationResult:
    return RuleEvaluationResult(
        rule_id=rule_id,
        rule_version=1,
        rule_title=f"Rule {rule_id}",
        severity="warning",
        result="pass",
        evidence_fields_inspected=[{"field": rule_id}],
        confidence=0.9,
        category="kde_presence",
    )


# ---------------------------------------------------------------------------
# Writer (engine salvage path)
# ---------------------------------------------------------------------------


class TestDeadletterWriter:
    def test_batch_salvage_deadletters_poisoned_row(self) -> None:
        session = MagicMock()

        def _execute(stmt, params=None):
            sql = str(stmt)
            if "INSERT INTO fsma.rule_evaluations" in sql and "deadletter" not in sql:
                if isinstance(params, list):
                    raise RuntimeError("chunk broke")
                if params["rule_id"] == "r-poisoned":
                    raise RuntimeError("row poisoned")
            return None

        session.execute.side_effect = _execute

        engine = RulesEngine(session)
        engine._batch_persist_evaluations(
            "tenant-1",
            [("event-a", _result("r-poisoned")), ("event-b", _result("r-fine"))],
        )

        dl_calls = [c for c in session.execute.call_args_list if "rule_evaluation_deadletter" in str(c.args[0])]
        assert len(dl_calls) == 1
        params = dl_calls[0].args[1]
        assert params["event_id"] == "event-a"
        assert params["rule_id"] == "r-poisoned"
        assert params["persist_error"] == "row poisoned"
        # The verdict payload survives verbatim.
        assert params["result"] == "pass"
        assert params["rule_version"] == 1

    def test_deadletter_write_failure_is_critical_not_fatal(self, monkeypatch) -> None:
        """If even the dead-letter insert fails, we log CRITICAL and move on
        — persistence failure handling must never take down ingestion."""
        import shared.rules.engine as engine_mod

        fake_logger = MagicMock()
        monkeypatch.setattr(engine_mod, "logger", fake_logger)

        session = MagicMock()

        def _execute(stmt, params=None):
            sql = str(stmt)
            if "INSERT INTO" in sql:  # both evaluations AND deadletter fail
                raise RuntimeError("db is very down")
            return None

        session.execute.side_effect = _execute

        engine = RulesEngine(session)
        engine._persist_evaluations("tenant-1", "event-1", [_result("r1")])  # must not raise

        crit_calls = [c for c in fake_logger.critical.call_args_list if c.args and "deadletter" in c.args[0]]
        assert len(crit_calls) == 1


# ---------------------------------------------------------------------------
# Replayer
# ---------------------------------------------------------------------------


class _ScriptedResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _ReplaySession:
    """Routes the replayer's queries; scripts per-row insert outcomes."""

    def __init__(self, pending_rows, insert_fails_for=()):
        self.pending_rows = pending_rows
        self.insert_fails_for = set(insert_fails_for)
        self.calls: list[tuple[str, dict]] = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.calls.append((sql, dict(params or {})))
        if "FROM fsma.rule_evaluation_deadletter" in sql and sql.strip().startswith("SELECT"):
            return _ScriptedResult(self.pending_rows)
        if "INSERT INTO fsma.rule_evaluations" in sql:
            if params["eval_id"] in self.insert_fails_for:
                raise RuntimeError("still poisoned")
            return _ScriptedResult([])
        return _ScriptedResult([])

    def begin_nested(self):
        return MagicMock()

    def rollback(self):
        pass

    def commit(self):
        pass


def _dl_row(dl_id, eval_id, attempts=0):
    return (dl_id, eval_id, "event-1", "r1", 1, "pass", None, {"k": "v"}, 0.9, attempts)


class TestReplayForTenant:
    def test_successful_replay_marks_replayed(self) -> None:
        session = _ReplaySession([_dl_row("dl-1", "eval-1")])
        counters = replay_mod.replay_deadletter_for_tenant(session, "tenant-1")

        assert counters == {"attempted": 1, "replayed": 1, "failed": 0, "parked": 0}
        marks = [c for c in session.calls if "SET replayed_at = now()" in c[0]]
        assert len(marks) == 1 and marks[0][1]["id"] == "dl-1"
        # Idempotent insert form.
        inserts = [c for c in session.calls if "INSERT INTO fsma.rule_evaluations" in c[0]]
        assert "ON CONFLICT (evaluation_id, tenant_id) DO NOTHING" in inserts[0][0]

    def test_failed_replay_bumps_attempts(self) -> None:
        session = _ReplaySession([_dl_row("dl-1", "eval-1", attempts=2)], insert_fails_for={"eval-1"})
        counters = replay_mod.replay_deadletter_for_tenant(session, "tenant-1")

        assert counters["failed"] == 1
        assert counters["parked"] == 0
        bumps = [c for c in session.calls if "SET replay_attempts" in c[0]]
        assert len(bumps) == 1 and bumps[0][1]["attempts"] == 3

    def test_final_failure_parks_row(self, monkeypatch) -> None:
        fake_logger = MagicMock()
        monkeypatch.setattr(replay_mod, "logger", fake_logger)
        last = replay_mod._MAX_REPLAY_ATTEMPTS - 1
        session = _ReplaySession([_dl_row("dl-1", "eval-1", attempts=last)], insert_fails_for={"eval-1"})
        counters = replay_mod.replay_deadletter_for_tenant(session, "tenant-1")

        assert counters["parked"] == 1
        park_logs = [c for c in fake_logger.error.call_args_list if c.args and c.args[0] == "deadletter_row_parked"]
        assert len(park_logs) == 1

    def test_pending_query_excludes_exhausted_rows(self) -> None:
        session = _ReplaySession([])
        replay_mod.replay_deadletter_for_tenant(session, "tenant-1")
        select_sql, select_params = next(c for c in session.calls if c[0].strip().startswith("SELECT"))
        assert "replay_attempts < :max_attempts" in select_sql
        assert "replayed_at IS NULL" in select_sql
        assert select_params["max_attempts"] == replay_mod._MAX_REPLAY_ATTEMPTS


class TestReplayAllTenants:
    def test_iterates_tenants_with_guc(self, monkeypatch) -> None:
        import shared.maintenance_tenants as maintenance_mod
        import shared.tenant_context as tc_mod

        monkeypatch.setattr(maintenance_mod, "list_maintenance_tenant_ids", lambda: ["t-1", "t-2"])
        guc_calls = []
        monkeypatch.setattr(tc_mod, "set_tenant_guc", lambda s, t: guc_calls.append(t))

        per_tenant_calls = []
        monkeypatch.setattr(
            replay_mod,
            "replay_deadletter_for_tenant",
            lambda s, t, batch_size=200: (
                per_tenant_calls.append(t) or {"attempted": 1, "replayed": 1, "failed": 0, "parked": 0}
            ),
        )

        session = MagicMock()

        totals = replay_mod.replay_all_tenants(session)

        assert per_tenant_calls == ["t-1", "t-2"]
        assert guc_calls == ["t-1", "t-2"]
        assert totals["replayed"] == 2

    def test_one_tenant_failure_does_not_poison_tick(self, monkeypatch) -> None:
        import shared.maintenance_tenants as maintenance_mod
        import shared.tenant_context as tc_mod

        monkeypatch.setattr(maintenance_mod, "list_maintenance_tenant_ids", lambda: ["t-1", "t-2"])
        monkeypatch.setattr(tc_mod, "set_tenant_guc", lambda s, t: None)

        def _per_tenant(session, tid, batch_size=200):
            if tid == "t-1":
                raise RuntimeError("tenant broke")
            return {"attempted": 1, "replayed": 1, "failed": 0, "parked": 0}

        monkeypatch.setattr(replay_mod, "replay_deadletter_for_tenant", _per_tenant)

        session = MagicMock()

        totals = replay_mod.replay_all_tenants(session)
        assert totals["replayed"] == 1
        session.rollback.assert_called()
