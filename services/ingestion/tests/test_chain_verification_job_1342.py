"""Coverage for app/chain_verification_job.py — async chain verification jobs.

Locks:
- Pydantic models (VerifyAllRequest, VerificationJobResponse,
  VerificationResultResponse) — defaults and required fields
- _run_verification: happy path (valid chain), failed chain with errors,
  outer exception during DB/import → failed job entry
- _persist_verification_result: happy path, insert exception → rollback,
  rollback-itself-raising also swallowed
- _log_verification_audit: loop running → ensure_future path,
  no loop → asyncio.run path, audit exception → silent
- POST /verify-all: kicks job off, in-memory entry created (thread
  replaced with synchronous runner)
- GET /verify-all/{job_id}: 404, completed-entry surfaced

Issue: #1342
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import chain_verification_job as cvj
from app.chain_verification_job import (
    VerificationJobResponse,
    VerificationResultResponse,
    VerifyAllRequest,
    _log_verification_audit,
    _persist_verification_result,
    _run_verification,
    _verification_jobs,
    router,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_jobs():
    """Reset in-memory jobs between tests."""
    with cvj._verification_lock:
        _verification_jobs.clear()
    yield
    with cvj._verification_lock:
        _verification_jobs.clear()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    from app.webhook_compat import _verify_api_key
    bypass = lambda: None
    app.dependency_overrides[_verify_api_key] = bypass
    app.dependency_overrides[cvj._verify_api_key] = bypass
    return app


@pytest.fixture
def client():
    return TestClient(_app())


class _FakeThread:
    """Runs the target synchronously so tests don't need to wait."""
    def __init__(self, target=None, args=(), daemon=False, **_kwargs):
        self._target = target
        self._args = args
        self.daemon = daemon

    def start(self):
        if self._target is not None:
            self._target(*self._args)


class _FakeThreading:
    """Stand-in for the `threading` module used inside chain_verification_job.

    Only exposes what the module touches (Thread + Lock). Leaves the global
    `threading` module untouched so starlette's ThreadPoolExecutor still works.
    """
    Thread = _FakeThread
    Lock = threading.Lock


def _seed_job(job_id: str, tenant_id: str = "t1") -> None:
    """Seed a job record so _run_verification can update it."""
    _verification_jobs[job_id] = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "status": "running",
        "started_at": "2026-01-01T00:00:00Z",
        "completed_at": None,
        "chain_valid": None,
        "chain_length": None,
        "errors": [],
        "message": None,
    }


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TestPydanticModels:
    def test_verify_all_request(self):
        r = VerifyAllRequest(tenant_id="t1")
        assert r.tenant_id == "t1"

    def test_verification_job_response(self):
        r = VerificationJobResponse(
            job_id="j1", tenant_id="t", status="running", started_at="now",
        )
        assert r.status == "running"

    def test_verification_result_response_defaults(self):
        r = VerificationResultResponse(
            job_id="j1", tenant_id="t", status="running", started_at="now",
        )
        assert r.completed_at is None
        assert r.chain_valid is None
        assert r.errors == []
        assert r.message is None


# ---------------------------------------------------------------------------
# _persist_verification_result
# ---------------------------------------------------------------------------


class TestPersistVerificationResult:
    def test_happy_path(self):
        db = MagicMock()
        _persist_verification_result(db, "j1", "t1", True, 5, [], "2026-01-01T00:00:00Z")
        assert db.execute.called
        assert db.commit.called

    def test_exception_triggers_rollback(self):
        db = MagicMock()
        db.execute.side_effect = RuntimeError("insert failed")
        _persist_verification_result(db, "j1", "t1", True, 5, [], "2026-01-01T00:00:00Z")
        # Should silently roll back, not raise
        assert db.rollback.called

    def test_rollback_failure_swallowed(self):
        """When both insert AND rollback raise, we must not propagate."""
        db = MagicMock()
        db.execute.side_effect = RuntimeError("insert failed")
        db.rollback.side_effect = RuntimeError("rollback failed too")
        # Must not raise
        _persist_verification_result(db, "j1", "t1", True, 5, [], "2026-01-01T00:00:00Z")


# ---------------------------------------------------------------------------
# _run_verification
# ---------------------------------------------------------------------------


class TestRunVerification:
    def test_valid_chain(self, monkeypatch):
        _seed_job("j1", "t1")
        db = MagicMock()
        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: db)

        class _Persistence:
            def __init__(self, s): pass
            def verify_chain(self, tid):
                return SimpleNamespace(valid=True, chain_length=100, errors=None)

        import shared.cte_persistence as cte_pkg
        monkeypatch.setattr(cte_pkg, "CTEPersistence", _Persistence)

        # Suppress audit log side effects
        monkeypatch.setattr(cvj, "_log_verification_audit", lambda *a, **k: None)

        _run_verification("j1", "t1")
        entry = _verification_jobs["j1"]
        assert entry["status"] == "completed"
        assert entry["chain_valid"] is True
        assert entry["chain_length"] == 100
        assert entry["errors"] == []
        assert "no tampering" in entry["message"]
        assert db.close.called

    def test_invalid_chain_surfaces_errors(self, monkeypatch):
        _seed_job("j1", "t1")
        db = MagicMock()
        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: db)

        class _Persistence:
            def __init__(self, s): pass
            def verify_chain(self, tid):
                return SimpleNamespace(
                    valid=False, chain_length=10, errors=["block 3 tampered"],
                )

        import shared.cte_persistence as cte_pkg
        monkeypatch.setattr(cte_pkg, "CTEPersistence", _Persistence)
        monkeypatch.setattr(cvj, "_log_verification_audit", lambda *a, **k: None)

        _run_verification("j1", "t1")
        entry = _verification_jobs["j1"]
        assert entry["status"] == "completed"
        assert entry["chain_valid"] is False
        assert entry["errors"] == ["block 3 tampered"]
        assert "FAILED" in entry["message"]
        assert "1 error" in entry["message"]

    def test_outer_exception_sets_failed_state(self, monkeypatch):
        _seed_job("j1", "t1")

        def _boom():
            raise RuntimeError("DB gone")

        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", _boom)

        _run_verification("j1", "t1")
        entry = _verification_jobs["j1"]
        assert entry["status"] == "failed"
        assert entry["chain_valid"] is None
        assert entry["chain_length"] == 0
        assert "DB gone" in entry["errors"][0]
        assert "Verification failed" in entry["message"]


# ---------------------------------------------------------------------------
# _log_verification_audit
# ---------------------------------------------------------------------------


class TestLogVerificationAudit:
    def test_no_loop_runs_via_asyncio_run(self, monkeypatch):
        """When no loop is running, we should call asyncio.run()."""
        called = {"run": False}

        async def _coro():
            called["coro_awaited"] = True

        class _FakeAudit:
            @classmethod
            def get_instance(cls):
                return cls()
            def log(self, **kwargs):
                return _coro()

        # Patch the shared.audit_logging import target
        import shared.audit_logging as al
        monkeypatch.setattr(al, "AuditLogger", _FakeAudit)

        def _fake_run(c):
            called["run"] = True
            c.close()  # Prevent "coroutine never awaited" warning
            return None

        monkeypatch.setattr(asyncio, "run", _fake_run)

        _log_verification_audit("t1", "j1", True, 10, [])
        assert called["run"] is True

    def test_loop_running_uses_ensure_future(self, monkeypatch):
        """When inside an event loop, we should call asyncio.ensure_future()."""
        called = {"ensure_future": False}

        async def _coro():
            pass

        class _FakeAudit:
            @classmethod
            def get_instance(cls):
                return cls()
            def log(self, **kwargs):
                return _coro()

        import shared.audit_logging as al
        monkeypatch.setattr(al, "AuditLogger", _FakeAudit)

        class _FakeLoop:
            def is_running(self):
                return True

        monkeypatch.setattr(asyncio, "get_running_loop", lambda: _FakeLoop())

        def _fake_ensure_future(coro):
            called["ensure_future"] = True
            coro.close()

        monkeypatch.setattr(asyncio, "ensure_future", _fake_ensure_future)

        _log_verification_audit("t1", "j1", False, 5, ["err"])
        assert called["ensure_future"] is True

    def test_exception_silently_swallowed(self, monkeypatch):
        """An exception anywhere in the audit path must not propagate."""
        import shared.audit_logging as al

        class _BadAudit:
            @classmethod
            def get_instance(cls):
                raise RuntimeError("audit unavailable")

        monkeypatch.setattr(al, "AuditLogger", _BadAudit)

        # Must not raise
        _log_verification_audit("t1", "j1", True, 10, [])


# ---------------------------------------------------------------------------
# POST /verify-all
# ---------------------------------------------------------------------------


class TestStartChainVerification:
    def test_kicks_off_job(self, client, monkeypatch):
        # Swap the module-local `threading` reference only (leave global alone
        # so starlette's ThreadPoolExecutor still has a real Thread).
        monkeypatch.setattr(cvj, "threading", _FakeThreading)

        # Make verification itself a no-op so we don't touch DB
        monkeypatch.setattr(cvj, "_run_verification", lambda jid, tid: None)

        r = client.post("/api/v1/chain/verify-all", json={"tenant_id": "t1"})
        assert r.status_code == 202
        body = r.json()
        assert body["tenant_id"] == "t1"
        assert body["status"] == "running"
        assert body["job_id"]
        # Entry persisted in-memory
        assert body["job_id"] in _verification_jobs

    def test_background_thread_synchronously_runs(self, client, monkeypatch):
        """Make the thread run _run_verification synchronously and assert
        the job entry progresses from running → completed."""
        monkeypatch.setattr(cvj, "threading", _FakeThreading)

        db = MagicMock()
        import shared.database as db_mod
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: db)

        class _Persistence:
            def __init__(self, s): pass
            def verify_chain(self, tid):
                return SimpleNamespace(valid=True, chain_length=7, errors=[])

        import shared.cte_persistence as cte_pkg
        monkeypatch.setattr(cte_pkg, "CTEPersistence", _Persistence)
        monkeypatch.setattr(cvj, "_log_verification_audit", lambda *a, **k: None)

        r = client.post("/api/v1/chain/verify-all", json={"tenant_id": "t1"})
        assert r.status_code == 202
        job_id = r.json()["job_id"]

        # After the thread runs synchronously, job should be completed
        entry = _verification_jobs[job_id]
        assert entry["status"] == "completed"
        assert entry["chain_valid"] is True
        assert entry["chain_length"] == 7


# ---------------------------------------------------------------------------
# GET /verify-all/{job_id}
# ---------------------------------------------------------------------------


class TestGetVerificationResult:
    def test_404_when_job_missing(self, client):
        r = client.get("/api/v1/chain/verify-all/nonexistent-job")
        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()

    def test_running_job(self, client):
        _seed_job("j1", "t1")
        r = client.get("/api/v1/chain/verify-all/j1")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "running"
        assert body["chain_valid"] is None

    def test_completed_job_surfaces_fields(self, client):
        _seed_job("j1", "t1")
        _verification_jobs["j1"].update({
            "status": "completed",
            "completed_at": "2026-01-01T01:00:00Z",
            "chain_valid": True,
            "chain_length": 50,
            "errors": [],
            "message": "ok",
        })

        r = client.get("/api/v1/chain/verify-all/j1")
        body = r.json()
        assert body["status"] == "completed"
        assert body["chain_valid"] is True
        assert body["chain_length"] == 50
        assert body["message"] == "ok"


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_routes_registered(self):
        paths = {r.path for r in router.routes}
        assert "/api/v1/chain/verify-all" in paths
        assert "/api/v1/chain/verify-all/{job_id}" in paths
