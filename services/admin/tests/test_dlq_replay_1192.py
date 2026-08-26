"""
Tests for POST /v1/system/dlq/replay -- #1192.

Verifies:
- Sysadmin-only gate (403 for non-sysadmin)
- 3 seeded 'dead' DLQ rows are all flipped to 'pending'
- replayed_at is stamped, replay_attempts incremented
- Non-existent IDs and non-dead statuses produce per-record errors
- Limit-based bulk replay works when no IDs are given
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


def _make_user(is_sysadmin: bool = False) -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.is_sysadmin = is_sysadmin
    return u


def _make_db_session():
    """Return a mock SQLAlchemy Session."""
    return MagicMock()


def _configure_admin_execute(db: MagicMock, *route_results: MagicMock) -> None:
    """Account for the route's transaction-local global-admin GUC arm."""
    db.execute.side_effect = [MagicMock(), *route_results]


def _assert_admin_context_armed(db: MagicMock) -> None:
    first_sql = str(db.execute.call_args_list[0].args[0])
    assert "set_config('regengine.is_sysadmin', 'true', true)" in first_sql


def _build_app(user: MagicMock, db: MagicMock) -> FastAPI:
    """Mount system_routes on a minimal FastAPI app with stubbed dependencies."""
    from services.admin.app.dependencies import get_session
    from services.admin.app.privileged_auth import PrivilegedActor, require_sysadmin_high_assurance
    from services.admin.app.system_routes import router

    app = FastAPI()
    app.include_router(router, prefix="/v1")

    app.dependency_overrides[require_sysadmin_high_assurance] = lambda: PrivilegedActor(
        actor_type="staff_user",
        actor_id=str(user.id),
        auth_method="webauthn",
        user=user,
    )
    app.dependency_overrides[get_session] = lambda: db
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDLQReplayAuth:
    """RBAC gate: only sysadmins may call the endpoint."""

    def test_non_sysadmin_gets_403(self):
        user = _make_user(is_sysadmin=False)
        db = _make_db_session()
        client = TestClient(_build_app(user, db), raise_server_exceptions=False)
        resp = client.post("/v1/system/dlq/replay", json={"ids": [], "limit": 5})
        assert resp.status_code == 403
        db.execute.assert_not_called()

    def test_sysadmin_passes_auth_gate(self):
        user = _make_user(is_sysadmin=True)
        db = _make_db_session()

        # Stub DB: no rows found for auto-limit query
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        _configure_admin_execute(db, mock_result)

        client = TestClient(_build_app(user, db))
        resp = client.post("/v1/system/dlq/replay", json={"ids": [], "limit": 5})
        assert resp.status_code == 200
        _assert_admin_context_armed(db)


class TestDLQReplayWithIds:
    """Replay 3 explicit dead rows by ID."""

    def _make_dead_ids(self) -> list[str]:
        return [str(uuid.uuid4()) for _ in range(3)]

    def test_three_dead_rows_all_replayed(self):
        user = _make_user(is_sysadmin=True)
        db = _make_db_session()
        dead_ids = self._make_dead_ids()

        # First execute: SELECT to verify IDs exist and are 'dead'
        fetch_result = MagicMock()
        fetch_result.fetchall.return_value = [(id_, "dead") for id_ in dead_ids]

        # Subsequent executes: one UPDATE per record (rowcount=1 → success)
        update_result = MagicMock()
        update_result.rowcount = 1

        # execute() is called 5 times: admin arm + fetch + 3 updates.
        _configure_admin_execute(db, fetch_result, update_result, update_result, update_result)

        client = TestClient(_build_app(user, db))
        resp = client.post("/v1/system/dlq/replay", json={"ids": dead_ids})

        assert resp.status_code == 200
        data = resp.json()
        assert data["replayed"] == 3
        assert data["failed"] == 0
        assert len(data["results"]) == 3
        for r in data["results"]:
            assert r["success"] is True
            assert r["id"] in dead_ids
        _assert_admin_context_armed(db)
        assert db.commit.call_count == 3

    def test_replayed_at_update_issued(self):
        """The UPDATE statement must reference replayed_at and replay_attempts."""
        user = _make_user(is_sysadmin=True)
        db = _make_db_session()
        dead_ids = [str(uuid.uuid4())]

        fetch_result = MagicMock()
        fetch_result.fetchall.return_value = [(dead_ids[0], "dead")]

        update_result = MagicMock()
        update_result.rowcount = 1
        _configure_admin_execute(db, fetch_result, update_result)

        client = TestClient(_build_app(user, db))
        resp = client.post("/v1/system/dlq/replay", json={"ids": dead_ids})
        assert resp.status_code == 200

        # Verify the UPDATE SQL contained replay tracking columns
        _assert_admin_context_armed(db)
        update_call_args = db.execute.call_args_list[2]
        sql_text = str(update_call_args[0][0])
        assert "replayed_at" in sql_text
        assert "replay_attempts" in sql_text

    def test_not_found_id_returns_error(self):
        user = _make_user(is_sysadmin=True)
        db = _make_db_session()
        missing_id = str(uuid.uuid4())

        fetch_result = MagicMock()
        fetch_result.fetchall.return_value = []  # no rows returned
        _configure_admin_execute(db, fetch_result)

        client = TestClient(_build_app(user, db))
        resp = client.post("/v1/system/dlq/replay", json={"ids": [missing_id]})

        assert resp.status_code == 200
        data = resp.json()
        assert data["replayed"] == 0
        assert data["failed"] == 1
        assert data["results"][0]["error"] == "not_found"
        _assert_admin_context_armed(db)

    def test_non_dead_status_rejected(self):
        user = _make_user(is_sysadmin=True)
        db = _make_db_session()
        pending_id = str(uuid.uuid4())

        fetch_result = MagicMock()
        fetch_result.fetchall.return_value = [(pending_id, "pending")]
        _configure_admin_execute(db, fetch_result)

        client = TestClient(_build_app(user, db))
        resp = client.post("/v1/system/dlq/replay", json={"ids": [pending_id]})

        assert resp.status_code == 200
        data = resp.json()
        assert data["replayed"] == 0
        assert data["failed"] == 1
        assert "status_is_pending_not_dead" in data["results"][0]["error"]
        _assert_admin_context_armed(db)


class TestDLQReplayBulkLimit:
    """Auto-select oldest dead rows when no IDs given."""

    def test_limit_based_replay(self):
        user = _make_user(is_sysadmin=True)
        db = _make_db_session()
        ids = [str(uuid.uuid4()) for _ in range(3)]

        # fetch returns 3 IDs for limit query
        fetch_result = MagicMock()
        fetch_result.fetchall.return_value = [(id_,) for id_ in ids]

        update_result = MagicMock()
        update_result.rowcount = 1

        _configure_admin_execute(db, fetch_result, update_result, update_result, update_result)

        client = TestClient(_build_app(user, db))
        resp = client.post("/v1/system/dlq/replay", json={"ids": [], "limit": 10})

        assert resp.status_code == 200
        data = resp.json()
        assert data["replayed"] == 3
        assert data["failed"] == 0
        _assert_admin_context_armed(db)
        assert db.commit.call_count == 3

    def test_limit_max_1000(self):
        """limit > 1000 should fail validation."""
        user = _make_user(is_sysadmin=True)
        db = _make_db_session()
        client = TestClient(_build_app(user, db), raise_server_exceptions=False)
        resp = client.post("/v1/system/dlq/replay", json={"ids": [], "limit": 1001})
        assert resp.status_code == 422
        db.execute.assert_not_called()
