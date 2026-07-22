"""Unit tests for the #2461 RLS context propagation mechanism.

Covers the pure-contextvar surface (tenant_scope / system_scope /
set_rls_tenant_id), the Engine-class-level "begin" hook
(_apply_rls_gucs_on_begin / install_rls_guc_hook), the TaskWorker
dispatch seeding, and the boot-time check_rls_posture probe.

No database required: postgres behavior is exercised with fake
connections; the sqlite no-op path uses a real in-memory engine.

IMPORTANT: everything here imports via the ``shared.`` alias — the
canonical runtime alias production code uses — so the tests observe the
SAME module instance (and ContextVar pair) as the code under test.
"""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("REGENGINE_ENV", "test")

import pytest
import shared.tenant_context as tc
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

_T_A = "11111111-1111-1111-1111-111111111111"
_T_B = "22222222-2222-2222-2222-222222222222"


# ---------------------------------------------------------------------------
# (a) + (b) contextvar semantics
# ---------------------------------------------------------------------------


class TestContextvarSemantics:
    def test_default_is_none(self):
        assert tc.get_rls_tenant_id() is None

    def test_set_str_coerces_uuid_instances(self):
        token = tc.set_rls_tenant_id(uuid.UUID(_T_A))
        try:
            assert tc.get_rls_tenant_id() == _T_A
            assert isinstance(tc.get_rls_tenant_id(), str)
        finally:
            tc.reset_rls_tenant_id(token)
        assert tc.get_rls_tenant_id() is None

    def test_set_none_clears(self):
        token_outer = tc.set_rls_tenant_id(_T_A)
        token_inner = tc.set_rls_tenant_id(None)
        assert tc.get_rls_tenant_id() is None
        tc.reset_rls_tenant_id(token_inner)
        assert tc.get_rls_tenant_id() == _T_A
        tc.reset_rls_tenant_id(token_outer)

    def test_tenant_scope_sets_and_resets(self):
        assert tc.get_rls_tenant_id() is None
        with tc.tenant_scope(_T_A):
            assert tc.get_rls_tenant_id() == _T_A
        assert tc.get_rls_tenant_id() is None

    def test_tenant_scope_nests(self):
        with tc.tenant_scope(_T_A):
            with tc.tenant_scope(_T_B):
                assert tc.get_rls_tenant_id() == _T_B
            assert tc.get_rls_tenant_id() == _T_A

    def test_tenant_scope_resets_on_exception(self):
        with pytest.raises(RuntimeError):
            with tc.tenant_scope(_T_A):
                raise RuntimeError("boom")
        assert tc.get_rls_tenant_id() is None

    def test_system_scope_sets_and_resets(self):
        assert tc._rls_system_context.get() is False
        with tc.system_scope():
            assert tc._rls_system_context.get() is True
        assert tc._rls_system_context.get() is False

    def test_system_scope_resets_on_exception(self):
        with pytest.raises(RuntimeError):
            with tc.system_scope():
                raise RuntimeError("boom")
        assert tc._rls_system_context.get() is False

    def test_scopes_are_independent(self):
        with tc.tenant_scope(_T_A), tc.system_scope():
            assert tc.get_rls_tenant_id() == _T_A
            assert tc._rls_system_context.get() is True
        assert tc.get_rls_tenant_id() is None
        assert tc._rls_system_context.get() is False


# ---------------------------------------------------------------------------
# (c) hook no-ops on non-postgresql dialects
# ---------------------------------------------------------------------------


class TestSqliteNoop:
    def test_no_set_config_emitted_on_sqlite(self):
        engine = create_engine("sqlite:///:memory:")
        statements: list[str] = []

        @event.listens_for(engine, "before_cursor_execute")
        def _spy(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        with tc.tenant_scope(_T_A), tc.system_scope():
            with engine.begin() as conn:
                conn.execute(text("SELECT 1"))

        assert statements, "expected at least the SELECT 1 to execute"
        assert not any("set_config" in s for s in statements), f"hook must no-op on sqlite; saw: {statements}"
        engine.dispose()


# ---------------------------------------------------------------------------
# (d) apply-time behavior against a fake postgres connection
# ---------------------------------------------------------------------------


def _fake_pg_conn():
    executed: list[tuple[str, dict | None]] = []

    def _execute(stmt, params=None):
        executed.append((str(stmt), params))

    conn = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"), execute=_execute)
    return conn, executed


class TestApplyOnBegin:
    def test_valid_uuid_sets_tenant_guc(self):
        conn, executed = _fake_pg_conn()
        with tc.tenant_scope(_T_A):
            tc._apply_rls_gucs_on_begin(conn)
        assert len(executed) == 1
        stmt, params = executed[0]
        assert "set_config('app.tenant_id', :tid, true)" in stmt
        assert params == {"tid": _T_A}

    def test_non_uuid_slug_is_skipped_not_raised(self):
        """Mirrors the set_tenant_guc_if_uuid slug-tolerance contract."""
        conn, executed = _fake_pg_conn()
        with tc.tenant_scope("acme-co-slug"):
            tc._apply_rls_gucs_on_begin(conn)  # must not raise
        assert executed == []

    def test_unseeded_context_is_noop(self):
        conn, executed = _fake_pg_conn()
        tc._apply_rls_gucs_on_begin(conn)
        assert executed == []

    def test_system_scope_sets_system_guc(self):
        conn, executed = _fake_pg_conn()
        with tc.system_scope():
            tc._apply_rls_gucs_on_begin(conn)
        assert len(executed) == 1
        stmt, _ = executed[0]
        assert "set_config('regengine.system_context', 'true', true)" in stmt

    def test_tenant_and_system_both_applied(self):
        conn, executed = _fake_pg_conn()
        with tc.tenant_scope(_T_A), tc.system_scope():
            tc._apply_rls_gucs_on_begin(conn)
        assert len(executed) == 2
        assert "app.tenant_id" in executed[0][0]
        assert "regengine.system_context" in executed[1][0]

    def test_apply_system_guc_helper_executes_on_session(self):
        executed = []
        session = SimpleNamespace(execute=lambda stmt, params=None: executed.append(str(stmt)))
        tc.apply_system_guc(session)
        assert len(executed) == 1
        assert "set_config('regengine.system_context', 'true', true)" in executed[0]


# ---------------------------------------------------------------------------
# (e) install idempotence + (f) class-level listener covers pre-existing engines
# ---------------------------------------------------------------------------


class TestHookInstallation:
    def test_module_import_installed_hook(self):
        assert tc._HOOK_INSTALLED is True
        assert event.contains(Engine, "begin", tc._apply_rls_gucs_on_begin)

    def test_install_is_idempotent(self, monkeypatch):
        calls: list[object] = []

        def _spy(conn):
            calls.append(conn)

        monkeypatch.setattr(tc, "_apply_rls_gucs_on_begin", _spy)
        monkeypatch.setattr(tc, "_HOOK_INSTALLED", False)
        try:
            tc.install_rls_guc_hook()
            tc.install_rls_guc_hook()  # second call must be a no-op

            engine = create_engine("sqlite:///:memory:")
            with engine.begin() as conn:
                conn.execute(text("SELECT 1"))
            engine.dispose()

            # Exactly ONE spy invocation per begin — a double registration
            # would produce two.
            assert len(calls) == 1
        finally:
            event.remove(Engine, "begin", _spy)

    def test_class_level_listener_fires_for_engine_created_before_listen(self):
        """Guards the core ordering assumption: engines constructed BEFORE
        a class-level ``event.listen(Engine, "begin", ...)`` still fire the
        listener (fsma_recall's per-call engines, the readiness throwaway,
        and lazy private engines all rely on this)."""
        engine = create_engine("sqlite:///:memory:")  # created FIRST
        calls: list[object] = []

        def _spy(conn):
            calls.append(conn)

        event.listen(Engine, "begin", _spy)  # registered SECOND
        try:
            with engine.begin() as conn:
                conn.execute(text("SELECT 1"))
            assert len(calls) == 1
        finally:
            event.remove(Engine, "begin", _spy)
            engine.dispose()


# ---------------------------------------------------------------------------
# (g) TaskWorker dispatch seeds the contextvar from the claimed row
# ---------------------------------------------------------------------------


class TestTaskWorkerDispatchSeeding:
    def _make_worker(self):
        from shared.task_queue import TaskWorker

        engine = create_engine("sqlite:///:memory:")
        worker = TaskWorker(engine)
        # Queue state transitions hit fsma.task_queue which sqlite lacks —
        # neutralize them; this test only exercises the dispatch seeding.
        worker._mark_completed = lambda *a, **k: None
        worker._mark_failed = lambda *a, **k: None
        worker._mark_dead = lambda *a, **k: None
        return worker, engine

    def test_dispatch_seeds_tenant_from_row(self):
        from shared.task_queue import TASK_HANDLERS

        worker, engine = self._make_worker()
        seen: dict[str, object] = {}

        def _handler(**kwargs):
            seen["tenant"] = tc.get_rls_tenant_id()

        TASK_HANDLERS["_guc_hook_test"] = _handler
        try:
            worker._dispatch(
                {
                    "id": 1,
                    "task_type": "_guc_hook_test",
                    "payload": {},
                    "attempts": 0,
                    "max_attempts": 3,
                    "tenant_id": _T_A,
                }
            )
        finally:
            TASK_HANDLERS.pop("_guc_hook_test", None)
            engine.dispose()

        assert seen["tenant"] == _T_A
        # Scope must not leak past the dispatch.
        assert tc.get_rls_tenant_id() is None

    def test_dispatch_without_tenant_runs_unseeded(self):
        from shared.task_queue import TASK_HANDLERS

        worker, engine = self._make_worker()
        seen: dict[str, object] = {}

        def _handler(**kwargs):
            seen["tenant"] = tc.get_rls_tenant_id()

        TASK_HANDLERS["_guc_hook_test2"] = _handler
        try:
            worker._dispatch(
                {
                    "id": 2,
                    "task_type": "_guc_hook_test2",
                    "payload": {},
                    "attempts": 0,
                    "max_attempts": 3,
                    "tenant_id": None,
                }
            )
        finally:
            TASK_HANDLERS.pop("_guc_hook_test2", None)
            engine.dispose()

        assert seen["tenant"] is None


# ---------------------------------------------------------------------------
# check_rls_posture (boot-time role probe)
# ---------------------------------------------------------------------------


def _fake_posture_engine(rolsuper: bool, rolbypassrls: bool):
    conn = mock.MagicMock()
    conn.execute.return_value.fetchone.return_value = ("somerole", rolsuper, rolbypassrls)
    cm = mock.MagicMock()
    cm.__enter__.return_value = conn
    cm.__exit__.return_value = False
    eng = mock.MagicMock()
    eng.dialect.name = "postgresql"
    eng.connect.return_value = cm
    return eng


class TestCheckRlsPosture:
    def test_sqlite_is_unknown(self):
        from shared.database import check_rls_posture

        engine = create_engine("sqlite:///:memory:")
        assert check_rls_posture(engine, label="unit-sqlite") == "unknown"
        engine.dispose()

    def test_probe_failure_is_unknown_and_does_not_raise(self):
        from shared.database import check_rls_posture

        eng = mock.MagicMock()
        eng.dialect.name = "postgresql"
        eng.connect.side_effect = ConnectionError("db down")
        assert check_rls_posture(eng, label="unit-down") == "unknown"

    def test_superuser_is_inert_and_sets_gauge(self, monkeypatch):
        from shared.database import check_rls_posture, regengine_rls_enforcement_inert

        monkeypatch.delenv("REGENGINE_REQUIRE_RLS_ENFORCEMENT", raising=False)
        assert check_rls_posture(_fake_posture_engine(True, False), label="unit-inert") == "inert"
        gauge_value = regengine_rls_enforcement_inert.labels(engine="unit-inert")._value.get()
        assert gauge_value == 1

    def test_bypassrls_is_inert(self, monkeypatch):
        from shared.database import check_rls_posture

        monkeypatch.delenv("REGENGINE_REQUIRE_RLS_ENFORCEMENT", raising=False)
        assert check_rls_posture(_fake_posture_engine(False, True), label="unit-inert2") == "inert"

    def test_require_env_raises_on_inert(self, monkeypatch):
        from shared.database import check_rls_posture

        monkeypatch.setenv("REGENGINE_REQUIRE_RLS_ENFORCEMENT", "1")
        with pytest.raises(RuntimeError, match="RLS enforcement required"):
            check_rls_posture(_fake_posture_engine(True, True), label="unit-required")

    def test_plain_role_is_enforced_and_gauge_zero(self, monkeypatch):
        from shared.database import check_rls_posture, regengine_rls_enforcement_inert

        monkeypatch.setenv("REGENGINE_REQUIRE_RLS_ENFORCEMENT", "1")
        assert check_rls_posture(_fake_posture_engine(False, False), label="unit-enforced") == "enforced"
        gauge_value = regengine_rls_enforcement_inert.labels(engine="unit-enforced")._value.get()
        assert gauge_value == 0
