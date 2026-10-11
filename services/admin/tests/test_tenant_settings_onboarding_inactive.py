"""Regression tests: onboarding read must honor membership status.

``GET /tenants/{tenant_id}/onboarding`` used ``_get_tenant_for_user``,
which verified only that a membership row exists, ignoring
``is_active``. A user whose membership was deactivated (offboarded)
could still read the tenant's workspace profile, onboarding state and
partner tier. The settings-write path (``_require_tenant_admin``)
already enforces ``is_active``; reads must match.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

_SERVICE_DIR = Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SERVICE_DIR.parent
for _p in (_SERVICE_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _db_with_membership(*, is_active: bool) -> MagicMock:
    db = MagicMock()
    membership = SimpleNamespace(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        role_id=uuid.uuid4(),
        is_active=is_active,
    )
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = membership
    db.execute.return_value = execute_result
    tenant = SimpleNamespace(id=TENANT_ID, settings={"onboarding": {}, "workspace_profile": {}})
    db.get.return_value = tenant
    return db


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_onboarding_read_rejects_deactivated_membership():
    from services.admin.app import tenant_settings_routes as mod

    user = SimpleNamespace(id=USER_ID, is_sysadmin=False)
    db = _db_with_membership(is_active=False)

    with pytest.raises(HTTPException) as exc_info:
        _run(mod.get_onboarding_status(TENANT_ID, user, db))

    assert exc_info.value.status_code == 403


def test_onboarding_read_allows_active_membership():
    from services.admin.app import tenant_settings_routes as mod

    user = SimpleNamespace(id=USER_ID, is_sysadmin=False)
    db = _db_with_membership(is_active=True)

    response = _run(mod.get_onboarding_status(TENANT_ID, user, db))

    assert response.is_complete is False
