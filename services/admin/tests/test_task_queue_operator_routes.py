"""Tests for sysadmin task queue operator endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


def _make_user(*, is_sysadmin: bool) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_sysadmin = is_sysadmin
    return user


def _build_app(user: MagicMock, db: MagicMock) -> FastAPI:
    from services.admin.app.dependencies import get_session
    from services.admin.app.privileged_auth import PrivilegedActor, require_sysadmin_high_assurance
    from services.admin.app.system_routes import router

    app = FastAPI()
    app.include_router(router, prefix="/v1")

    def _privileged_actor() -> PrivilegedActor:
        if not user.is_sysadmin:
            raise HTTPException(status_code=403, detail="Sysadmin required")
        return PrivilegedActor(
            actor_type="staff_user",
            actor_id=str(user.id),
            auth_method="webauthn",
            user=user,
        )

    app.dependency_overrides[require_sysadmin_high_assurance] = _privileged_actor
    app.dependency_overrides[get_session] = lambda: db
    return app


def test_task_queue_summary_requires_sysadmin() -> None:
    client = TestClient(
        _build_app(_make_user(is_sysadmin=False), MagicMock()),
        raise_server_exceptions=False,
    )

    resp = client.get("/v1/system/task-queue/summary")

    assert resp.status_code == 403


def test_task_queue_summary_returns_shared_summary(monkeypatch) -> None:
    db = MagicMock()
    summary = {
        "counts_by_status": {"pending": 2, "processing": 1, "dead": 1},
        "retrying_count": 1,
        "stale_processing_count": 1,
        "oldest_pending_age_seconds": 300.0,
        "oldest_dead_age_seconds": 900.0,
    }
    monkeypatch.setattr(
        "services.admin.app.system_routes.get_task_queue_summary",
        MagicMock(return_value=summary),
    )
    client = TestClient(_build_app(_make_user(is_sysadmin=True), db))

    resp = client.get("/v1/system/task-queue/summary")

    assert resp.status_code == 200
    assert resp.json() == summary


def test_task_queue_replay_by_ids_returns_shared_result(monkeypatch) -> None:
    db = MagicMock()
    replay = {
        "replayed": 1,
        "failed": 1,
        "results": [
            {"id": "123", "success": True, "error": None},
            {"id": "456", "success": False, "error": "status_is_pending_not_dead"},
        ],
    }
    helper = MagicMock(return_value=replay)
    monkeypatch.setattr("services.admin.app.system_routes.replay_dead_tasks", helper)
    client = TestClient(_build_app(_make_user(is_sysadmin=True), db))

    resp = client.post(
        "/v1/system/task-queue/replay",
        json={"ids": ["123", "456"], "limit": 10},
    )

    assert resp.status_code == 200
    assert resp.json() == replay
    helper.assert_called_once_with(db, ids=["123", "456"], limit=10)


def test_task_queue_replay_by_limit_requires_sysadmin() -> None:
    client = TestClient(
        _build_app(_make_user(is_sysadmin=False), MagicMock()),
        raise_server_exceptions=False,
    )

    resp = client.post("/v1/system/task-queue/replay", json={"ids": [], "limit": 5})

    assert resp.status_code == 403
