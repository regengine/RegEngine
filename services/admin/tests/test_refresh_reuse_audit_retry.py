"""Refresh-token-reuse audit write must retry once, then alarm.

Audit finding: audit-write failures were swallowed on the
refresh-token-reuse path (AuditLogger.log_event returns None on failure,
and refresh_router ignored that return and only logged a warning on
exceptions). These tests pin the fixed behavior: a lost reuse-audit write
is retried once, still returns 401 reuse-detected, and alarms loudly
(error log plus metric) when the retry also fails.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_repo_root = Path(__file__).resolve().parents[3]
_service_dir = Path(__file__).resolve().parents[2]
for _p in (_repo_root, _service_dir):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

os.environ.setdefault("ADMIN_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AUTH_SECRET_KEY", "refresh-reuse-audit-retry-test-secret")
os.environ.setdefault("SESSION_STORE_BACKEND", "memory")


def _request():
    return SimpleNamespace(
        headers={},
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(),
    )


def _reused_session(user_id=None):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        family_id=uuid.uuid4(),
        is_revoked=False,
        created_at=now,
        last_used_at=now,
        expires_at=now,
        token_version=0,
    )


def _store_for(session):
    store = MagicMock()
    store.claim_session_by_token = AsyncMock(return_value=None)
    store.check_token_reuse = AsyncMock(return_value=session.id)
    store.get_session = AsyncMock(return_value=session)
    store.revoke_all_for_family = AsyncMock(return_value=1)
    return store


def _db_with_tenant(tenant_id):
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = tenant_id
    return db


@pytest.mark.asyncio
async def test_reuse_audit_none_return_is_retried_and_recovers():
    from fastapi import HTTPException

    from services.admin.app.auth import refresh_router
    from services.admin.app.auth.refresh_router import RefreshRequest, refresh_session

    session = _reused_session()
    store = _store_for(session)
    db = _db_with_tenant(uuid.uuid4())

    with patch.object(refresh_router.AuditLogger, "log_event", side_effect=[None, 99]) as log_event:
        with pytest.raises(HTTPException) as exc:
            await refresh_session.__wrapped__(
                RefreshRequest(refresh_token="raw"),
                _request(),
                db=db,
                session_store=store,
            )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Refresh token reuse detected"
    assert log_event.call_count == 2
    store.revoke_all_for_family.assert_awaited_once_with(session.family_id)
    db.commit.assert_called()


@pytest.mark.asyncio
async def test_reuse_audit_repeated_failure_retries_once_then_alarms():
    from fastapi import HTTPException

    from services.admin.app.auth import refresh_router
    from services.admin.app.auth.refresh_router import RefreshRequest, refresh_session

    session = _reused_session()
    store = _store_for(session)
    db = _db_with_tenant(uuid.uuid4())

    with patch.object(refresh_router.AuditLogger, "log_event", return_value=None) as log_event:
        with patch.object(refresh_router, "_count_reuse_audit_failure") as count_failure:
            with pytest.raises(HTTPException) as exc:
                await refresh_session.__wrapped__(
                    RefreshRequest(refresh_token="raw"),
                    _request(),
                    db=db,
                    session_store=store,
                )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Refresh token reuse detected"
    # One initial attempt plus exactly one retry, then give up loudly.
    assert log_event.call_count == 2
    count_failure.assert_called_once()
    store.revoke_all_for_family.assert_awaited_once_with(session.family_id)


@pytest.mark.asyncio
async def test_reuse_audit_exception_is_retried_then_reports_failure():
    from fastapi import HTTPException

    from services.admin.app.auth import refresh_router
    from services.admin.app.auth.refresh_router import RefreshRequest, refresh_session

    session = _reused_session()
    store = _store_for(session)
    db = _db_with_tenant(uuid.uuid4())
    db.commit.side_effect = Exception("db down")

    with patch.object(refresh_router.AuditLogger, "log_event", return_value=7) as log_event:
        with patch.object(refresh_router, "_count_reuse_audit_failure") as count_failure:
            with pytest.raises(HTTPException) as exc:
                await refresh_session.__wrapped__(
                    RefreshRequest(refresh_token="raw"),
                    _request(),
                    db=db,
                    session_store=store,
                )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Refresh token reuse detected"
    assert log_event.call_count == 2
    count_failure.assert_called_once()
    store.revoke_all_for_family.assert_awaited_once_with(session.family_id)


@pytest.mark.asyncio
async def test_reuse_audit_success_writes_once_with_no_alarm():
    from fastapi import HTTPException

    from services.admin.app.auth import refresh_router
    from services.admin.app.auth.refresh_router import RefreshRequest, refresh_session

    session = _reused_session()
    store = _store_for(session)
    db = _db_with_tenant(uuid.uuid4())

    with patch.object(refresh_router.AuditLogger, "log_event", return_value=7) as log_event:
        with patch.object(refresh_router, "_count_reuse_audit_failure") as count_failure:
            with pytest.raises(HTTPException) as exc:
                await refresh_session.__wrapped__(
                    RefreshRequest(refresh_token="raw"),
                    _request(),
                    db=db,
                    session_store=store,
                )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Refresh token reuse detected"
    assert log_event.call_count == 1
    count_failure.assert_not_called()
    db.commit.assert_called_once()
