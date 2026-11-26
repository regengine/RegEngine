"""Regression tests for #2918 — per-task-type visibility timeouts must be persisted.

`locked_until` is the column that governs steal-back: a worker that is
SIGKILLed mid-task leaves the row unclaimable until that instant passes.
The #1210 per-task-type map promised 30s/120s/300s recovery windows, but
`_claim_task` computed `locked_until` from the 15-minute global constant
*before the task type was known*, so every task got 15 minutes.

The feature was dead in a second place too: the `RETURNING` clause
COALESCEd `visibility_timeout_seconds` to `DEFAULT_TIMEOUT_SECONDS`, so
`row[5]` was never NULL and `row[5] or TASK_TIMEOUTS_SECONDS.get(...)`
always short-circuited — making `TASK_TIMEOUTS_SECONDS` unreachable.

`services/shared/task_queue.py` already got this right
(`locked_until = NOW() + make_interval(secs => COALESCE(...))`); this
brings the monolith's worker into line.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest

from server.workers import task_processor


def _capture_claim(row=None):
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = row
    claimed = task_processor._claim_task(db)
    call = db.execute.call_args
    sql = str(call.args[0])
    params = call.args[1] if len(call.args) > 1 else (call.kwargs.get("parameters") or {})
    return claimed, sql, params


def _norm(sql):
    return " ".join(sql.lower().split())


# ---------------------------------------------------------------------------
# The persisted deadline
# ---------------------------------------------------------------------------


class TestPersistedLockedUntil:
    def test_locked_until_is_computed_in_sql_not_from_the_global_constant(self):
        """#2918 acceptance criterion 1."""
        _, sql, params = _capture_claim()
        normalized = _norm(sql)

        set_clause = normalized.split("where")[0]
        assert "locked_until" in set_clause
        assert "visibility_timeout_seconds" in set_clause, (
            "locked_until must be derived from the row's "
            "visibility_timeout_seconds inside the claim SQL — computing it "
            "in Python before the task type is known is what pinned every "
            f"task to the 15-minute global lock.\nSET clause was: {set_clause}"
        )

    def test_claim_no_longer_binds_a_precomputed_lock_until(self):
        """A precomputed 15-minute deadline must not reach the UPDATE."""
        _, _, params = _capture_claim()
        assert "lock_until" not in params, (
            "the claim still binds a Python-computed lock_until — that value "
            "is LOCK_TIMEOUT_MINUTES (15) and is independent of task type"
        )

    def test_per_task_type_map_is_bound_into_the_claim(self):
        """TASK_TIMEOUTS_SECONDS must actually reach the database."""
        _, sql, params = _capture_claim()
        types = params.get("timeout_types")
        secs = params.get("timeout_secs")
        assert types is not None and secs is not None, (
            "TASK_TIMEOUTS_SECONDS must be bound into the claim so the "
            f"persisted locked_until honours it; bound params: {sorted(params)}"
        )
        assert dict(zip(types, secs)) == dict(task_processor.TASK_TIMEOUTS_SECONDS)

    def test_coalesce_arms_are_ordered_most_specific_first(self):
        """Row override, then the per-task-type map, then the global default."""
        normalized = _norm(_capture_claim()[1])
        start = normalized.find("coalesce(")
        assert start != -1, "the effective timeout must be a COALESCE expression"
        expr = normalized[start : start + 400]

        vt = expr.find("visibility_timeout_seconds")
        tt = expr.find("unnest(")
        dt = expr.find(":default_timeout")
        assert vt != -1, "arm 1 (the producer's row-level override) is missing"
        assert tt != -1, (
            "arm 2 (the per-task-type TASK_TIMEOUTS_SECONDS map) is missing — "
            f"that is exactly what #2918 reports as dead.\nCOALESCE was: {expr}"
        )
        assert dt != -1, "arm 3 (the global default) is missing"
        assert vt < tt < dt, (
            "COALESCE arms must run most-specific first: the row's own "
            "visibility_timeout_seconds outranks the per-task-type map, which "
            f"outranks the global default.\nCOALESCE was: {expr}"
        )

    def test_default_timeout_is_the_last_resort(self):
        _, _, params = _capture_claim()
        assert params.get("default_timeout") == task_processor.DEFAULT_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# TASK_TIMEOUTS_SECONDS must be reachable, not dead code
# ---------------------------------------------------------------------------


class TestTimeoutMapIsReachable:
    def test_in_memory_timeout_falls_through_to_the_map(self):
        """`row[5] or TASK_TIMEOUTS_SECONDS[...]` must be reachable.

        The RETURNING COALESCE defaulted to 120, so row[5] was never NULL
        and the map lookup was unreachable dead code.
        """
        row = (
            7,
            "review_item",
            {"document_id": "d"},
            0,
            3,
            None,  # no row-level override — the map must supply the value
            "11111111-2222-3333-4444-555555555555",
        )
        claimed, _, _ = _capture_claim(row)
        assert claimed is not None
        assert claimed["visibility_timeout_seconds"] == task_processor.TASK_TIMEOUTS_SECONDS["review_item"], (
            "with no row-level override the per-task-type map must supply the "
            f"timeout; got {claimed['visibility_timeout_seconds']}"
        )

    def test_unmapped_task_type_falls_back_to_default(self):
        row = (8, "some_new_type", {}, 0, 3, None, None)
        claimed, _, _ = _capture_claim(row)
        assert claimed["visibility_timeout_seconds"] == task_processor.DEFAULT_TIMEOUT_SECONDS

    def test_row_override_still_honoured_in_memory(self):
        row = (9, "review_item", {}, 0, 3, 45, None)
        claimed, _, _ = _capture_claim(row)
        assert claimed["visibility_timeout_seconds"] == 45


# ---------------------------------------------------------------------------
# Heartbeat cadence must fit inside the visibility window
# ---------------------------------------------------------------------------


class TestHeartbeatCadence:
    def test_heartbeat_interval_helper_exists(self):
        assert hasattr(task_processor, "_heartbeat_interval_for"), (
            "#2918: the heartbeat cadence must be derived from the task's "
            "timeout, not hardcoded at 60s — a 30s timeout with a 60s "
            "heartbeat guarantees the lock is stolen mid-run"
        )

    @pytest.mark.parametrize("timeout", [15, 30, 45, 60, 120, 300, 900])
    def test_heartbeat_refreshes_at_least_twice_per_window(self, timeout):
        """#2918 acceptance criterion 2."""
        interval = task_processor._heartbeat_interval_for(timeout)
        assert interval > 0
        assert interval < timeout / 2, (
            f"a {timeout}s visibility window with a {interval}s heartbeat "
            "does not refresh the lock at least twice before it expires"
        )

    def test_every_configured_timeout_survives_its_heartbeat(self):
        """Every value in the #1210 map, plus the default, must be safe."""
        configured = list(task_processor.TASK_TIMEOUTS_SECONDS.values())
        configured.append(task_processor.DEFAULT_TIMEOUT_SECONDS)
        for timeout in configured:
            interval = task_processor._heartbeat_interval_for(timeout)
            assert interval < timeout / 2, (
                f"configured timeout {timeout}s is not safely above its "
                f"heartbeat interval {interval}s — the first heartbeat would "
                "shrink the lock below its own refresh cadence"
            )

    def test_misconfigured_timeout_fails_loudly(self):
        """#2918 proposed fix 3 — a bad configuration must not be silent."""
        with pytest.raises(ValueError):
            task_processor._heartbeat_interval_for(0)
        with pytest.raises(ValueError):
            task_processor._heartbeat_interval_for(-5)

    def test_handler_runner_uses_the_derived_interval(self, monkeypatch):
        """The runner must not join on the old hardcoded constant."""
        seen = {}

        real = task_processor._heartbeat_interval_for

        def _spy(timeout_seconds):
            seen["timeout"] = timeout_seconds
            return real(timeout_seconds)

        monkeypatch.setattr(task_processor, "_heartbeat_interval_for", _spy)
        task_processor._run_handler_with_heartbeat(
            db_factory=MagicMock(),
            task_id=1,
            timeout_seconds=30,
            handler=lambda payload, tenant_id: None,
            payload={},
        )
        assert seen.get("timeout") == 30, (
            "_run_handler_with_heartbeat must derive its cadence from the task's visibility timeout"
        )


# ---------------------------------------------------------------------------
# The legacy global constant
# ---------------------------------------------------------------------------


class TestLegacyGlobalConstant:
    def test_lock_timeout_minutes_no_longer_governs_claims(self):
        """#2918 acceptance criterion 4."""
        source = __import__("inspect").getsource(task_processor._claim_task)
        assert "LOCK_TIMEOUT_MINUTES" not in source, (
            "_claim_task must not compute the visibility deadline from the 15-minute global constant"
        )


# ---------------------------------------------------------------------------
# Existing claim guarantees must survive
# ---------------------------------------------------------------------------


class TestClaimInvariantsPreserved:
    def test_claim_still_filters_by_registered_handler_types(self):
        _, sql, params = _capture_claim()
        assert "handler_types" in params
        assert set(params["handler_types"]) == set(task_processor.TASK_HANDLERS.keys())
        assert "task_type = any(:handler_types)" in _norm(sql)

    def test_claim_still_honours_scheduled_at_backoff(self):
        _, sql, _ = _capture_claim()
        assert "scheduled_at <= :now" in _norm(sql), "#1241 backoff predicate must survive"

    def test_claim_still_uses_skip_locked(self):
        _, sql, _ = _capture_claim()
        assert "for update skip locked" in _norm(sql)

    def test_claim_still_reclaims_expired_processing_rows(self):
        _, sql, _ = _capture_claim()
        assert "locked_until < :now" in _norm(sql)


# ---------------------------------------------------------------------------
# The two resolutions must not drift
# ---------------------------------------------------------------------------


class TestSqlAndMemoryAgree:
    """The persisted deadline and the heartbeated one must be the same number.

    The SQL resolves the timeout to write `locked_until`; the Python
    fallback chain resolves it to drive the heartbeat. Both are fed by the
    same constants — this pins that they stay in step.
    """

    def _sql_resolution(self, params, task_type, row_value):
        mapping = dict(zip(params["timeout_types"], params["timeout_secs"]))
        if row_value is not None:
            return row_value
        return mapping.get(task_type, params["default_timeout"])

    @pytest.mark.parametrize("task_type", ["nlp_extraction", "review_item", "unmapped_type"])
    @pytest.mark.parametrize("row_value", [None, 45])
    def test_resolutions_match(self, task_type, row_value):
        row = (1, task_type, {}, 0, 3, row_value, None)
        claimed, _, params = _capture_claim(row)
        assert claimed["visibility_timeout_seconds"] == self._sql_resolution(params, task_type, row_value), (
            "the timeout persisted into locked_until and the one the heartbeat extends against must be identical"
        )

    def test_sql_compiles_against_the_postgres_dialect(self):
        """Guards the claim SQL's bind params and constructs."""
        from sqlalchemy.dialects import postgresql

        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None
        task_processor._claim_task(db)
        stmt, params = db.execute.call_args.args[0], db.execute.call_args.args[1]
        compiled = str(stmt.bindparams(**params).compile(dialect=postgresql.dialect()))
        assert "make_interval" in compiled
        assert "for update skip locked" in compiled.lower()
