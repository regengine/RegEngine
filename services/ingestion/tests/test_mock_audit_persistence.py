"""Mock-audit drill persistence — fsma.mock_audit_drills storage layer.

Locks:
- _persist_drill: insert params, commit, close, 503 on failure
- _load_drill: row -> in-memory-shaped dict, None on no-row / DB failure
- _mark_drill_completed: update params, 503 on failure
- POST /drill/start persists the drill row
- GET /drill/{id} and POST /drill/{id}/submit fall back to the DB row when
  the in-process cache is empty (restart survival), including the
  cross-tenant 404 on submit

Companion to test_mock_audit_1342.py, which locks the API behavior against
the in-process cache. Migration: v101 (1b10a708e36a).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from app import mock_audit as ma
from app.mock_audit import (
    FDA_SCENARIOS,
    _active_drills,
    _load_drill,
    _mark_drill_completed,
    _persist_drill,
    router,
)
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_drills():
    """Reset the in-memory drill cache between tests."""
    _active_drills.clear()
    yield
    _active_drills.clear()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    from app.webhook_compat import _verify_api_key

    from services.ingestion.tests.tenant_context_overrides import install_tenant_context_override

    app.dependency_overrides[_verify_api_key] = lambda: None
    install_tenant_context_override(app, default_tenant="t1")
    return app


@pytest.fixture
def client():
    return TestClient(_app())


def _fake_session(monkeypatch) -> MagicMock:
    session = MagicMock()
    import shared.database as db_mod

    monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)
    return session


def _drill_dict(tenant_id: str = "t1", *, status: str = "active", hours_ago: float = 1.0) -> dict:
    now = datetime.now(timezone.utc)
    started = now - timedelta(hours=hours_ago)
    return {
        "tenant_id": tenant_id,
        "scenario": FDA_SCENARIOS[0].copy(),
        "started_at": started.isoformat(),
        "deadline": (started + timedelta(hours=24)).isoformat(),
        "status": status,
        "grade": None,
    }


def _all_true_payload(drill_id: str) -> dict:
    return {
        "drill_id": drill_id,
        "has_lot_genealogy": True,
        "has_electronic_records": True,
        "has_all_ctes": True,
        "has_all_kdes": True,
        "has_chain_verification": True,
        "has_epcis_export": True,
    }


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


class TestPersistDrill:
    def test_inserts_row_with_drill_fields(self, monkeypatch):
        session = _fake_session(monkeypatch)
        drill = _drill_dict()

        _persist_drill("drill-123", drill)

        assert session.execute.called
        sql = str(session.execute.call_args[0][0])
        assert "INSERT INTO fsma.mock_audit_drills" in sql
        params = session.execute.call_args[0][1]
        assert params["drill_id"] == "drill-123"
        assert params["tid"] == "t1"
        assert params["target_tlc"] == FDA_SCENARIOS[0]["target_tlc"]
        assert params["status"] == "active"
        assert session.commit.called
        assert session.close.called

    def test_surfaces_db_failure(self, monkeypatch):
        session = _fake_session(monkeypatch)
        session.execute.side_effect = RuntimeError("DB gone")

        with pytest.raises(HTTPException) as exc:
            _persist_drill("drill-123", _drill_dict())
        assert exc.value.status_code == 503

        assert session.close.called


class TestLoadDrill:
    def test_returns_in_memory_shaped_dict(self, monkeypatch):
        session = _fake_session(monkeypatch)
        started = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)
        deadline = started + timedelta(hours=24)
        session.execute.return_value.fetchone.return_value = (
            "11111111-1111-1111-1111-111111111111",
            FDA_SCENARIOS[0].copy(),
            "active",
            None,
            None,
            started,
            deadline,
        )

        drill = _load_drill("drill-123")

        assert drill == {
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "scenario": FDA_SCENARIOS[0],
            "started_at": started.isoformat(),
            "deadline": deadline.isoformat(),
            "status": "active",
            "grade": None,
            "score": None,
        }
        assert session.close.called

    def test_returns_none_when_no_row(self, monkeypatch):
        session = _fake_session(monkeypatch)
        session.execute.return_value.fetchone.return_value = None

        assert _load_drill("drill-123") is None

    def test_returns_none_on_db_failure(self, monkeypatch):
        session = _fake_session(monkeypatch)
        session.execute.side_effect = RuntimeError("DB gone")

        assert _load_drill("drill-123") is None
        assert session.close.called


class TestMarkDrillCompleted:
    def test_updates_grade_and_score(self, monkeypatch):
        session = _fake_session(monkeypatch)

        session.execute.return_value.rowcount = 1
        _mark_drill_completed("drill-123", "t1", "A", 100)

        sql = str(session.execute.call_args[0][0])
        assert "UPDATE fsma.mock_audit_drills" in sql
        params = session.execute.call_args[0][1]
        assert params == {"drill_id": "drill-123", "tid": "t1", "grade": "A", "score": 100}
        assert session.commit.called
        assert session.close.called

    def test_surfaces_db_failure(self, monkeypatch):
        session = _fake_session(monkeypatch)
        session.execute.side_effect = RuntimeError("DB gone")

        with pytest.raises(HTTPException) as exc:
            _mark_drill_completed("drill-123", "t1", "A", 100)
        assert exc.value.status_code == 503


# ---------------------------------------------------------------------------
# Route wiring
# ---------------------------------------------------------------------------


class TestStartDrillPersists:
    def test_start_drill_writes_row(self, client, monkeypatch):
        monkeypatch.setattr(ma, "_get_real_tlc", lambda tid: None)
        persisted: dict = {}
        monkeypatch.setattr(ma, "_persist_drill", lambda drill_id, drill: persisted.update({drill_id: drill}))

        r = client.post("/api/v1/audit/drill/start", json={"tenant_id": "t1"})

        assert r.status_code == 200
        drill_id = r.json()["drill_id"]
        assert persisted[drill_id]["tenant_id"] == "t1"
        assert persisted[drill_id]["status"] == "active"
        # In-memory cache and persisted row are the same record
        assert persisted[drill_id] is _active_drills[drill_id]


class TestGetDrillDbFallback:
    def test_falls_back_to_db_when_not_in_memory(self, client, monkeypatch):
        monkeypatch.setattr(ma, "_load_drill", lambda drill_id: _drill_dict(hours_ago=1.0))

        r = client.get("/api/v1/audit/drill/drill-db-1")

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "active"
        assert body["time_remaining_seconds"] > 0

    def test_404_when_neither_memory_nor_db(self, client, monkeypatch):
        monkeypatch.setattr(ma, "_load_drill", lambda drill_id: None)

        r = client.get("/api/v1/audit/drill/drill-db-1")

        assert r.status_code == 404

    def test_memory_hit_skips_db(self, client, monkeypatch):
        _active_drills["drill-mem-1"] = _drill_dict()

        def _boom(drill_id):
            raise AssertionError("DB should not be queried on a memory hit")

        monkeypatch.setattr(ma, "_load_drill", _boom)

        r = client.get("/api/v1/audit/drill/drill-mem-1")

        assert r.status_code == 200


class TestSubmitDbFallback:
    def test_grades_db_loaded_drill(self, client, monkeypatch):
        monkeypatch.setattr(ma, "_load_drill", lambda drill_id: _drill_dict(hours_ago=1.0))
        completions: list = []
        monkeypatch.setattr(
            ma,
            "_mark_drill_completed",
            lambda drill_id, tenant_id, grade, score: completions.append((drill_id, tenant_id, grade, score)),
        )

        r = client.post(
            "/api/v1/audit/drill/drill-db-2/submit",
            json=_all_true_payload("drill-db-2"),
        )

        assert r.status_code == 200
        body = r.json()
        assert body["grade"] == "A"
        assert body["score"] == 100
        assert completions == [("drill-db-2", "t1", "A", 100)]
        # DB-loaded drill lands back in the in-process cache as completed
        assert _active_drills["drill-db-2"]["status"] == "completed"

    def test_404_when_db_drill_belongs_to_other_tenant(self, client, monkeypatch):
        monkeypatch.setattr(ma, "_load_drill", lambda drill_id: _drill_dict(tenant_id="other-tenant"))
        monkeypatch.setattr(
            ma,
            "_mark_drill_completed",
            lambda *a: pytest.fail("must not persist a cross-tenant submission"),
        )

        r = client.post(
            "/api/v1/audit/drill/drill-db-3/submit",
            json=_all_true_payload("drill-db-3"),
        )

        assert r.status_code == 404

    def test_memory_submit_persists_completion(self, client, monkeypatch):
        drill = _drill_dict(hours_ago=1.0)
        _active_drills["drill-mem-2"] = drill
        completions: list = []
        monkeypatch.setattr(
            ma,
            "_mark_drill_completed",
            lambda drill_id, tenant_id, grade, score: completions.append((drill_id, tenant_id, grade, score)),
        )

        r = client.post(
            "/api/v1/audit/drill/drill-mem-2/submit",
            json=_all_true_payload("drill-mem-2"),
        )

        assert r.status_code == 200
        assert completions == [("drill-mem-2", "t1", "A", 100)]
        assert _active_drills["drill-mem-2"]["status"] == "completed"
