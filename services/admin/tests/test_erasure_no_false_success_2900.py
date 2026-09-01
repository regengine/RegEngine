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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

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
    return MagicMock()


def _fake_session_store():
    store = MagicMock()
    store.revoke_all_user_sessions = AsyncMock(return_value=None)
    return store


async def _invoke(module, *, apply_erasure, db):
    """Drive ``request_erasure`` directly, bypassing FastAPI's DI.

    ``request_erasure`` no longer calls ``DataRetentionManager`` — it calls a
    local ``_apply_account_erasure(db, ...)`` that runs real SQLAlchemy
    queries. Mocking it wholesale (rather than trying to satisfy those
    queries with a bare ``MagicMock`` session) keeps these tests focused on
    the route's success/failure contract. ``apply_erasure`` stands in for
    ``_apply_account_erasure``: it must raise to simulate a failed erasure,
    or return an int (historical audit row count) — and itself call
    ``module.enqueue_graph_write`` to simulate that real function's
    observable side effect on success, since we no longer execute it.

    ``db``/``session_store`` are passed as explicit keyword arguments
    instead of relying on FastAPI to resolve their ``Depends(...)``
    defaults, since that resolution never happens when the coroutine is
    invoked directly instead of through a real request.
    """

    async def _async_noop(*_a, **_k):
        return None

    session_store = _fake_session_store()

    body = module.ErasureRequest(confirm=True, reason="testing")
    with (
        patch.object(module, "_apply_account_erasure", side_effect=apply_erasure),
        patch.object(module.TenantContext, "get_tenant_context", return_value=_TENANT_ID),
        patch.object(module, "enqueue_graph_write") as enqueue_mock,
        patch.object(module, "_delete_neo4j_user_graph_data") as neo4j_mock,
        patch(
            "app.auth.elevation_helpers._revoke_all_elevation_tokens_for_user",
            new=AsyncMock(return_value=0),
        ),
    ):
        neo4j_mock.side_effect = _async_noop
        try:
            response = await module.request_erasure(
                body=body,
                current_user=_user_model(),
                session_store=session_store,
                db=db,
            )
        except Exception as exc:  # noqa: BLE001 — the caller asserts on it
            return None, exc, enqueue_mock, neo4j_mock
        return response, None, enqueue_mock, neo4j_mock


@pytest.mark.asyncio
async def test_erasure_fails_closed_when_nothing_was_soft_deleted():
    """The #2900 regression: 200 + "has been marked for deletion" for a
    deletion that never happened.

    ``_apply_account_erasure`` now either fully applies the erasure or
    raises — there is no more silent partial-failure dict to simulate.
    Raising ``SQLAlchemyError`` reproduces the original bug report's
    "relation does not exist" failure mode.
    """
    from app import erasure_routes as m
    from fastapi import HTTPException

    def _apply_erasure(_db, **_kwargs):
        raise SQLAlchemyError('relation "user_account" does not exist')

    db = _fake_db()
    response, exc, _enqueue, _neo4j = await _invoke(m, apply_erasure=_apply_erasure, db=db)

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
    from app import erasure_routes as m

    def _apply_erasure(_db, **_kwargs):
        raise SQLAlchemyError("boom")

    db = _fake_db()
    _response, _exc, enqueue_mock, neo4j_mock = await _invoke(m, apply_erasure=_apply_erasure, db=db)

    enqueue_mock.assert_not_called()
    neo4j_mock.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_successful_erasure_still_returns_the_accepted_response():
    """Guard against over-correction: the happy path is unchanged.

    Current ``ErasureResponse`` never schedules a hard delete
    (``hard_delete_scheduled`` is always ``False`` — there is no durable
    hard-delete queue in the current schema), unlike the pre-#2900 mocked
    contract this test previously asserted.
    """
    from app import erasure_routes as m

    def _apply_erasure(db, *, user_id, tenant_id):
        m.enqueue_graph_write(
            db,
            tenant_id=str(tenant_id),
            operation="user_erasure",
            cypher=m._CYPHER_DELETE_USER_GRAPH_DATA,
            params={"user_id": str(user_id)},
            dedupe_key=f"user_erasure:{tenant_id}:{user_id}",
        )
        return 1

    db = _fake_db()
    response, exc, enqueue_mock, _neo4j = await _invoke(m, apply_erasure=_apply_erasure, db=db)

    assert exc is None, f"the happy path must not raise, got {exc!r}"
    assert response.status == "accepted"
    assert response.soft_deleted is True
    assert response.hard_delete_scheduled is False
    enqueue_mock.assert_called_once()
