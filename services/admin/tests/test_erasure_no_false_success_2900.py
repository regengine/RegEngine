"""#2900 — /v1/account/erasure must never report success for an erasure it
did not perform.

The retention layer wrote to relations that do not exist in the migrated
schema. ``soft_delete_record`` swallowed the resulting ``UndefinedTable`` and
returned ``False``; ``process_deletion_request`` turned that into
``{"soft_deleted": False}``; and the route returned **HTTP 200
``status="accepted"``** with the message *"Your account data has been marked
for deletion."*

Telling a data subject their Article 17 request was honoured when no row was
touched is a regulatory misstatement, not a cosmetic bug. These tests lock in
that the endpoint fails closed instead.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO_ADMIN = Path(__file__).resolve().parents[1]
if str(_REPO_ADMIN) not in sys.path:
    sys.path.insert(0, str(_REPO_ADMIN))

_USER_ID = uuid.uuid4()
_TENANT_ID = uuid.uuid4()


def _user_model():
    u = MagicMock()
    u.id = _USER_ID
    u.email = "user@example.com"
    return u


def _fake_db():
    db = MagicMock()
    db.__enter__ = MagicMock(return_value=db)
    db.__exit__ = MagicMock(return_value=False)
    return db


async def _invoke(module, *, process_result, db):
    async def _async_noop(*_a, **_k):
        return None

    def _apply(*_a, **_k):
        if not process_result.get("soft_deleted"):
            from sqlalchemy.exc import SQLAlchemyError

            raise SQLAlchemyError("identity mutation did not complete")
        return 0

    body = module.ErasureRequest(confirm=True, reason="testing")
    with (
        patch.object(module, "_apply_account_erasure", side_effect=_apply),
        patch.object(module, "_revoke_erased_user_runtime_sessions", side_effect=_async_noop),
        patch.object(module.TenantContext, "get_tenant_context", return_value=_TENANT_ID),
        patch.object(module, "enqueue_graph_write") as enqueue_mock,
        patch.object(module, "_delete_neo4j_user_graph_data") as neo4j_mock,
    ):
        neo4j_mock.side_effect = _async_noop
        try:
            response = await module.request_erasure(
                body=body, current_user=_user_model(), db=db, session_store=MagicMock()
            )
        except Exception as exc:  # noqa: BLE001 — the caller asserts on it
            return None, exc, enqueue_mock, neo4j_mock
        return response, None, enqueue_mock, neo4j_mock


@pytest.mark.asyncio
async def test_erasure_fails_closed_when_nothing_was_soft_deleted():
    """The #2900 regression: 200 + "has been marked for deletion" for a
    deletion that never happened."""
    from services.admin.app import erasure_routes as m
    from fastapi import HTTPException

    db = _fake_db()
    response, exc, _enqueue, _neo4j = await _invoke(
        m,
        process_result={
            "resource_type": "user_account",
            "record_id": str(_USER_ID),
            "soft_deleted": False,
            "hard_delete_scheduled": False,
            "error": 'relation "user_account" does not exist',
        },
        db=db,
    )

    assert response is None, (
        "the endpoint returned a success body for an erasure that deleted nothing: "
        f"{getattr(response, 'message', response)!r}"
    )
    assert isinstance(exc, HTTPException)
    assert exc.status_code >= 500, f"a failed erasure must not be a 2xx or a client error, got {exc.status_code}"
    assert "marked for deletion" not in str(exc.detail).lower()


@pytest.mark.asyncio
async def test_failed_erasure_does_not_enqueue_a_graph_deletion():
    """Deleting the Neo4j half while Postgres keeps the user would leave the
    two stores permanently inconsistent — with no record that it happened."""
    from services.admin.app import erasure_routes as m

    db = _fake_db()
    _response, _exc, enqueue_mock, neo4j_mock = await _invoke(
        m,
        process_result={"soft_deleted": False, "hard_delete_scheduled": False, "error": "boom"},
        db=db,
    )

    enqueue_mock.assert_not_called()
    neo4j_mock.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_successful_erasure_still_returns_the_accepted_response():
    """Guard against over-correction: the happy path is unchanged."""
    from services.admin.app import erasure_routes as m

    db = _fake_db()
    response, exc, enqueue_mock, _neo4j = await _invoke(
        m,
        process_result={
            "soft_deleted": True,
            "hard_delete_scheduled": True,
            "hard_delete_date": "2027-05-09",
        },
        db=db,
    )

    assert exc is None, f"the happy path must not raise, got {exc!r}"
    assert response.status == "accepted"
    assert response.soft_deleted is True
    assert response.hard_delete_scheduled is False
    db.commit.assert_called_once()
