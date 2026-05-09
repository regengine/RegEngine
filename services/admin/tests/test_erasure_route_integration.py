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

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
    u.get.side_effect = AttributeError(
        "UserModel has no .get(); use attribute access"
    )
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
    from app import erasure_routes as m

    body = m.ErasureRequest(confirm=True, reason="testing")
    user = _make_user_model()

    db = MagicMock()
    db.commit = MagicMock()
    db.__enter__ = MagicMock(return_value=db)
    db.__exit__ = MagicMock(return_value=False)

    fake_get_db = MagicMock()
    fake_get_db.return_value.__enter__ = MagicMock(return_value=db)
    fake_get_db.return_value.__exit__ = MagicMock(return_value=False)

    fake_manager = MagicMock()

    async def _proc_del(**_kwargs):
        return {
            "soft_deleted": True,
            "hard_delete_scheduled": True,
            "hard_delete_date": "2027-05-09",
        }

    async def _anon(**_kwargs):
        return (3, [])

    fake_manager.process_deletion_request = _proc_del
    fake_manager.anonymize_audit_logs_for_user = _anon

    with patch.object(m, "get_db", fake_get_db), \
         patch.object(m.TenantContext, "get_tenant_context",
                      return_value=_TENANT_ID), \
         patch("shared.data_retention.DataRetentionManager",
               return_value=fake_manager), \
         patch.object(m, "enqueue_graph_write") as enqueue_mock, \
         patch.object(m, "_delete_neo4j_user_graph_data") as neo4j_mock:
        # _delete_neo4j_user_graph_data is async — patch with AsyncMock-ish
        async def _async_noop(*a, **k):
            return None
        neo4j_mock.side_effect = _async_noop

        resp = await m.request_erasure(body=body, current_user=user)

    assert resp.status == "accepted"
    assert resp.soft_deleted is True
    assert resp.audit_logs_anonymized is True
    enqueue_mock.assert_called_once()
    # Confirm the user.get() escape hatch was never invoked — i.e. the
    # handler used attribute access throughout.
    assert user.get.call_count == 0


@pytest.mark.asyncio
async def test_erasure_requires_confirm_true():
    """``confirm=false`` returns 400 before any DB / tenant access."""
    from app import erasure_routes as m
    from fastapi import HTTPException

    body = m.ErasureRequest(confirm=False)
    user = _make_user_model()

    with pytest.raises(HTTPException) as exc:
        await m.request_erasure(body=body, current_user=user)
    assert exc.value.status_code == 400
