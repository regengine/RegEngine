"""Integration test for /v1/account/erasure (RE-SEC-001).

Locks in the contract that ``request_erasure`` reads identity from
``current_user`` as a SQLAlchemy ``UserModel`` instance (attribute
access), not a dict, and reads ``tenant_id`` from
``TenantContext.get_tenant_context(db)`` rather than from the user
object or request body.

Pre-fix the handler did ``current_user.get("user_id")`` on a UserModel,
which raised AttributeError. The broad ``except Exception`` swallowed
it and returned a misleading 500 ("logged and processed manually").
Every GDPR Article 17 erasure silently failed.
"""

from __future__ import annotations

import inspect
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Make services/admin importable
_REPO_ADMIN = Path(__file__).resolve().parents[1]
if str(_REPO_ADMIN) not in sys.path:
    sys.path.insert(0, str(_REPO_ADMIN))


_USER_ID = uuid.uuid4()
_TENANT_ID = uuid.uuid4()


def _make_user_model(**overrides):
    """A UserModel-shaped mock. The handler must use attribute access."""
    u = MagicMock()
    u.id = _USER_ID
    u.email = "user@example.com"
    # Explicitly raise on dict-style access so any regression to
    # ``.get("user_id")`` re-introduces the bug loudly instead of
    # silently swallowing.
    u.get.side_effect = AttributeError("UserModel has no .get(); use attribute access")
    for k, v in overrides.items():
        setattr(u, k, v)
    return u


@pytest.mark.asyncio
async def test_erasure_reads_id_email_via_attribute_not_dict():
    """Regression: handler uses ``current_user.id`` / ``.email``, not
    ``current_user.get(...)``. If a future PR re-introduces dict access,
    the .get side_effect will raise and bubble out of the (now
    narrowed) except clause as a real test failure rather than a
    swallowed 500.
    """
    from services.admin.app import erasure_routes as m

    body = m.ErasureRequest(confirm=True, reason="testing")
    user = _make_user_model()

    db = MagicMock()
    db.commit = MagicMock()
    fake_store = MagicMock()

    with (
        patch.object(m.TenantContext, "get_tenant_context", return_value=_TENANT_ID),
        patch.object(m, "_apply_account_erasure", return_value=3) as erase_mock,
        patch.object(m, "arm_global_admin_context"),
        patch.object(m, "_revoke_erased_user_runtime_sessions", new_callable=AsyncMock) as revoke_mock,
        patch.object(m, "_delete_neo4j_user_graph_data", new_callable=AsyncMock),
    ):
        resp = await m.request_erasure(body=body, current_user=user, session_store=fake_store, db=db)

    assert resp.status == "accepted"
    assert resp.soft_deleted is True
    assert resp.audit_logs_anonymized is True
    assert resp.hard_delete_scheduled is False
    erase_mock.assert_called_once_with(db, user_id=_USER_ID, tenant_id=_TENANT_ID)
    revoke_mock.assert_awaited_once_with(fake_store, _USER_ID)
    db.commit.assert_called_once()
    # Confirm the user.get() escape hatch was never invoked — i.e. the
    # handler used attribute access throughout.
    assert user.get.call_count == 0


@pytest.mark.asyncio
async def test_erasure_starts_runtime_cleanup_immediately_after_commit_without_disarm():
    """A durable commit must flow directly to cache/elevation cleanup.

    ``SET LOCAL`` is cleared by PostgreSQL at commit. A post-commit disarm
    starts a new transaction and can fail after the erasure is durable but
    before runtime credentials are revoked.
    """
    from services.admin.app import erasure_routes as m

    events: list[str] = []
    db = MagicMock()
    db.commit.side_effect = lambda: events.append("commit")

    async def _record_cleanup(_store, _user_id):
        events.append("runtime-cleanup")

    async def _record_graph_cleanup(_tenant_id, _user_id):
        events.append("graph-cleanup")

    with (
        patch.object(m.TenantContext, "get_tenant_context", return_value=_TENANT_ID),
        patch.object(m, "_apply_account_erasure", return_value=0),
        patch.object(m, "arm_global_admin_context"),
        patch.object(m, "_revoke_erased_user_runtime_sessions", side_effect=_record_cleanup),
        patch.object(m, "_delete_neo4j_user_graph_data", side_effect=_record_graph_cleanup),
    ):
        response = await m.request_erasure(
            body=m.ErasureRequest(confirm=True),
            current_user=_make_user_model(),
            session_store=MagicMock(),
            db=db,
        )

    assert response.status == "accepted"
    assert events == ["commit", "runtime-cleanup", "graph-cleanup"]
    assert "disarm_global_admin_context" not in inspect.getsource(m.request_erasure)
    db.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_erasure_rolls_back_armed_transaction_before_mapping_db_failure():
    """A failure before durable commit must clear transaction-local authority."""
    from services.admin.app import erasure_routes as m
    from fastapi import HTTPException
    from sqlalchemy.exc import SQLAlchemyError

    db = MagicMock()

    with (
        patch.object(m.TenantContext, "get_tenant_context", return_value=_TENANT_ID),
        patch.object(m, "arm_global_admin_context"),
        patch.object(
            m,
            "_apply_account_erasure",
            side_effect=SQLAlchemyError("write failed"),
        ),
        patch.object(m, "_revoke_erased_user_runtime_sessions", new_callable=AsyncMock) as revoke_mock,
        patch.object(m, "_delete_neo4j_user_graph_data", new_callable=AsyncMock) as graph_mock,
    ):
        with pytest.raises(HTTPException) as exc:
            await m.request_erasure(
                body=m.ErasureRequest(confirm=True),
                current_user=_make_user_model(),
                session_store=MagicMock(),
                db=db,
            )

    assert exc.value.status_code == 500
    db.commit.assert_not_called()
    db.rollback.assert_called_once_with()
    revoke_mock.assert_not_awaited()
    graph_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_erasure_requires_confirm_true():
    """``confirm=false`` returns 400 before any DB / tenant access."""
    from services.admin.app import erasure_routes as m
    from fastapi import HTTPException

    body = m.ErasureRequest(confirm=False)
    user = _make_user_model()

    with pytest.raises(HTTPException) as exc:
        await m.request_erasure(body=body, current_user=user)
    assert exc.value.status_code == 400
