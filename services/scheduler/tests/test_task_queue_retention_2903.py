"""Regression tests for #2903 — the retention purge must not destroy FSMA evidence.

`services/graph/app/fsma_recall/persistence.py` parks recall-drill history
rows in ``fsma.task_queue`` at ``status='completed'`` (the #1199 sentinel
that hides them from the worker).  ``SchedulerService.purge_old_tasks``
read the same column as "this row is garbage" and deleted anything
terminal older than 30 days with **no ``task_type`` predicate**.

`fsma.task_queue` is the *only* persistent store for recall drills, and
the DELETE is a hard delete with no archive table and no audit trigger,
so the loss is silent and unrecoverable.

The fix is a positive allowlist, shared by the producer-side worker and
the purge, so a *future* evidence-bearing task type is retained by
default rather than by remembering to add it to a denylist.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

TERMINAL_STATUSES = ("completed", "dead")


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


def _run_purge_and_capture():
    """Run purge_old_tasks against a mock session; return (sql, params)."""
    svc = _build_scheduler_service_without_init()
    with patch("services.admin.app.database.SessionLocal") as session_factory:
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        session_factory.return_value = db
        svc.purge_old_tasks()

    calls = [c for c in db.execute.call_args_list if c.args and "delete" in str(c.args[0]).lower()]
    assert calls, "purge_old_tasks issued no DELETE"
    call = calls[0]
    sql = str(call.args[0])
    params = call.args[1] if len(call.args) > 1 else (call.kwargs.get("parameters") or {})
    return sql, params


# ---------------------------------------------------------------------------
# The SQL itself must be task-type scoped
# ---------------------------------------------------------------------------


class TestPurgeIsTaskTypeScoped:
    def test_purge_sql_constrains_task_type(self):
        """#2903 acceptance: the emitted DELETE must constrain task_type."""
        sql, _ = _run_purge_and_capture()
        assert "task_type" in sql.lower(), (
            "purge_old_tasks must constrain task_type — without a predicate it "
            "deletes recall_drill evidence rows that share fsma.task_queue.\n"
            f"SQL was:\n{sql}"
        )

    def test_purge_binds_an_explicit_allowlist_parameter(self):
        """The scope must be a bound allowlist, not an inline literal.

        A bound parameter is what lets the worker and the purge share one
        definition; an inline literal is exactly the drift that caused
        this bug.
        """
        _, params = _run_purge_and_capture()
        allowlist = params.get("purgeable_task_types")
        assert allowlist is not None, (
            f"purge_old_tasks must bind a 'purgeable_task_types' array parameter — bound params were {sorted(params)}"
        )
        assert isinstance(allowlist, (list, tuple)) and allowlist, "allowlist must be a non-empty sequence"

    def test_recall_evidence_types_are_never_in_the_purge_scope(self):
        """A recall_drill / recall row must be out of scope at any age."""
        _, params = _run_purge_and_capture()
        allowlist = set(params.get("purgeable_task_types") or [])
        protected = set(params.get("protected_task_types") or [])

        for evidence_type in ("recall_drill", "recall"):
            assert evidence_type not in allowlist, (
                f"{evidence_type!r} must never appear in the purge allowlist — "
                "it is FSMA 204 mock-recall evidence with no other store"
            )
            assert evidence_type in protected, (
                f"{evidence_type!r} must be named in the bound denylist so the "
                "exclusion survives an accidental allowlist edit"
            )

    def test_purge_sql_also_carries_a_belt_and_braces_denylist(self):
        """Allowlist AND denylist: two independent reasons evidence survives."""
        sql, params = _run_purge_and_capture()
        lowered = " ".join(sql.lower().split())
        assert "purgeable_task_types" in lowered, sql
        assert "protected_task_types" in lowered, (
            "the DELETE must additionally exclude the protected types explicitly, "
            f"so a bad allowlist edit cannot silently re-expose them.\nSQL was:\n{sql}"
        )

    def test_purge_still_only_targets_terminal_statuses(self):
        """The #1382 guarantee must survive the #2903 fix."""
        sql, _ = _run_purge_and_capture()
        lowered = sql.lower()
        assert "'completed'" in lowered and "'dead'" in lowered
        assert "'pending'" not in lowered
        assert "'processing'" not in lowered


# ---------------------------------------------------------------------------
# One shared definition, imported by both modules
# ---------------------------------------------------------------------------


class TestSingleSourceOfTruth:
    def test_shared_module_defines_the_classification(self):
        from shared import task_types

        assert "recall_drill" in task_types.NON_WORKER_TASK_TYPES
        assert "recall" in task_types.NON_WORKER_TASK_TYPES
        assert task_types.PURGEABLE_TASK_TYPES
        assert not (task_types.PURGEABLE_TASK_TYPES & task_types.NON_WORKER_TASK_TYPES), (
            "a task type may not be both purgeable and protected"
        )

    def test_task_processor_reuses_the_shared_denylist(self):
        """#2903 acceptance: defined in exactly one module, imported by both."""
        from shared import task_types

        from server.workers import task_processor

        assert task_processor.NON_WORKER_TASK_TYPES is task_types.NON_WORKER_TASK_TYPES, (
            "server/workers/task_processor.py must import NON_WORKER_TASK_TYPES from "
            "shared.task_types rather than redefining it — the duplicate definition "
            "is what let the purge and the worker drift apart"
        )

    def test_scheduler_service_reuses_the_shared_allowlist(self):
        from shared import task_types

        _, params = _run_purge_and_capture()
        assert set(params["purgeable_task_types"]) == set(task_types.PURGEABLE_TASK_TYPES)
        assert set(params["protected_task_types"]) == set(task_types.NON_WORKER_TASK_TYPES)


# ---------------------------------------------------------------------------
# Fail-closed: unknown/future task types are retained, not deleted
# ---------------------------------------------------------------------------


class TestFailsClosedForFutureTaskTypes:
    def test_unknown_task_type_is_not_purgeable(self):
        """A task type nobody classified must be RETAINED, never deleted.

        This is the property that makes the fix durable: the next module
        that parks evidence in fsma.task_queue is safe on day one without
        its author knowing this purge exists.
        """
        from shared import task_types

        assert not task_types.is_purgeable("fsma_recall_evidence_2027")
        assert not task_types.is_purgeable("")

    def test_known_worker_types_remain_purgeable(self):
        """Fail-closed must not mean 'purge nothing' — #1382 still has to work."""
        from shared import task_types

        assert task_types.is_purgeable("nlp_extraction")
        assert task_types.is_purgeable("review_item")

    def test_every_worker_handler_type_is_classified(self):
        """Registering a handler without classifying its type must fail loudly."""
        from shared import task_types

        from server.workers import task_processor

        for task_type in task_processor.TASK_HANDLERS:
            assert task_type in task_types.PURGEABLE_TASK_TYPES, (
                f"{task_type!r} has a worker handler but is not classified in "
                "shared.task_types.PURGEABLE_TASK_TYPES — its rows would "
                "accumulate forever (#1382 regression)"
            )


# ---------------------------------------------------------------------------
# Policy applied to seeded rows (the acceptance-criteria scenario)
# ---------------------------------------------------------------------------


def _purge_predicate(row, allowlist, protected, now):
    """Python mirror of the DELETE predicate, for policy-level assertions."""
    age_anchor = row.get("completed_at") or row["created_at"]
    return (
        row["status"] in TERMINAL_STATUSES
        and row["task_type"] in allowlist
        and row["task_type"] not in protected
        and age_anchor < now - timedelta(days=30)
    )


class TestSeededRowsSurvive:
    @pytest.fixture
    def scope(self):
        _, params = _run_purge_and_capture()
        return set(params["purgeable_task_types"]), set(params["protected_task_types"])

    def test_400_day_old_completed_recall_drill_survives(self, scope):
        """#2903 acceptance criterion 1."""
        allowlist, protected = scope
        now = datetime.now(timezone.utc)
        drill = {
            "task_type": "recall_drill",
            "status": "completed",  # the #1199 sentinel, not a real completion
            "created_at": now - timedelta(days=400),
            "completed_at": now - timedelta(days=400),
        }
        assert not _purge_predicate(drill, allowlist, protected, now), (
            "a 400-day-old recall drill is FSMA 204 mock-recall evidence and must survive the retention purge"
        )

    def test_in_progress_drill_with_null_completed_at_survives(self, scope):
        """COALESCE falls back to created_at — the worst case in the issue."""
        allowlist, protected = scope
        now = datetime.now(timezone.utc)
        drill = {
            "task_type": "recall_drill",
            "status": "completed",
            "created_at": now - timedelta(days=31),
            "completed_at": None,  # drill still in_progress in the payload
        }
        assert not _purge_predicate(drill, allowlist, protected, now)

    def test_recall_state_machine_rows_survive(self, scope):
        allowlist, protected = scope
        now = datetime.now(timezone.utc)
        row = {
            "task_type": "recall",
            "status": "completed",
            "created_at": now - timedelta(days=400),
            "completed_at": now - timedelta(days=400),
        }
        assert not _purge_predicate(row, allowlist, protected, now)

    def test_ordinary_stale_worker_rows_are_still_purged(self, scope):
        """The #1382 purge must keep doing its job."""
        allowlist, protected = scope
        now = datetime.now(timezone.utc)
        row = {
            "task_type": "nlp_extraction",
            "status": "completed",
            "created_at": now - timedelta(days=90),
            "completed_at": now - timedelta(days=90),
        }
        assert _purge_predicate(row, allowlist, protected, now)

    def test_recent_worker_rows_are_retained(self, scope):
        allowlist, protected = scope
        now = datetime.now(timezone.utc)
        row = {
            "task_type": "nlp_extraction",
            "status": "completed",
            "created_at": now - timedelta(days=2),
            "completed_at": now - timedelta(days=2),
        }
        assert not _purge_predicate(row, allowlist, protected, now)


# ---------------------------------------------------------------------------
# Telemetry: a future mis-scoped purge must be visible
# ---------------------------------------------------------------------------


class TestPurgeTelemetry:
    def test_purge_logs_per_task_type_breakdown(self):
        svc = _build_scheduler_service_without_init()
        from services.scheduler import service as scheduler_service

        with (
            patch("services.admin.app.database.SessionLocal") as session_factory,
            patch.object(scheduler_service.logger, "info") as log_info,
        ):
            db = MagicMock()
            db.execute.return_value.fetchall.return_value = [
                (1, "nlp_extraction"),
                (2, "nlp_extraction"),
                (3, "review_item"),
            ]
            session_factory.return_value = db
            svc.purge_old_tasks()

        purged = [c for c in log_info.call_args_list if c.args and c.args[0] == "task_queue_purged"]
        assert purged, "purge must log task_queue_purged"
        by_type = purged[0].kwargs.get("by_task_type")
        assert by_type == {"nlp_extraction": 2, "review_item": 1}, (
            "the purge must log a per-task_type breakdown so a future "
            f"mis-scoped purge is visible in telemetry; got {by_type!r}"
        )
