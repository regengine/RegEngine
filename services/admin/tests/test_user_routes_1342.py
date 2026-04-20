"""
Regression coverage for ``services/admin/app/user_routes.py`` — closes the 86% gap.

Missing branches:
* Lines 56-88  — list_users happy path (query + row assembly)
* Lines 299-313 — list_roles happy path (query + row assembly)

Both functions' no-tenant 400 guards are already covered by existing
``TestListUsers_Issue1341`` and ``TestListRoles_Issue1341``. This file
adds the happy-path DB-read-and-assemble branches.

Uses the same direct coroutine-invocation pattern as the existing test.

Tracks GitHub issue #1342.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Ensure the repo root is on sys.path so `from services.admin.app import ...` resolves.
repo_root = Path(__file__).resolve().parents[4]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
ACTOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
ROLE_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")


def _load_routes(monkeypatch):
    """Load user_routes and patch TenantContext to return TENANT_ID."""
    from services.admin.app import user_routes as ur
    monkeypatch.setattr(
        ur.TenantContext, "get_tenant_context",
        staticmethod(lambda _db: TENANT_ID),
    )
    return ur


def _fake_user(**kwargs):
    """Construct a minimal UserModel-like SimpleNamespace."""
    from datetime import datetime, timezone
    defaults = dict(
        id=ACTOR_ID, email="actor@example.com", status="active",
        is_sysadmin=False, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _fake_membership(**kwargs):
    defaults = dict(
        user_id=ACTOR_ID, tenant_id=TENANT_ID,
        role_id=ROLE_ID, is_active=True,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _fake_role(**kwargs):
    defaults = dict(id=ROLE_ID, name="Member", tenant_id=TENANT_ID)
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# list_users — lines 56-88
# ---------------------------------------------------------------------------


class TestListUsersHappyPath:

    def test_returns_user_list_with_active_status(self, monkeypatch):
        """Lines 56-88: list_users with one active user → PaginatedResponse
        with correct UserResponse.status='active'."""
        ur = _load_routes(monkeypatch)
        from shared.pagination import PaginationParams

        user = _fake_user()
        membership = _fake_membership(is_active=True)
        role = _fake_role()

        # Mock db: first .scalar() returns total=1, second .all() returns one row
        db = MagicMock()
        call_count = [0]

        def _execute_side_effect(stmt):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # Count query
                result.scalar.return_value = 1
            else:
                # Rows query
                result.all.return_value = [(user, membership, role)]
            return result

        db.execute.side_effect = _execute_side_effect

        result = asyncio.run(
            ur.list_users(
                pagination=PaginationParams(skip=0, limit=10),
                db=db,
            )
        )

        assert result.total == 1
        assert len(result.items) == 1
        assert result.items[0].email == "actor@example.com"
        assert result.items[0].status == "active"
        assert result.items[0].role_name == "Member"

    def test_inactive_membership_yields_inactive_status(self, monkeypatch):
        """Lines 80-81: membership.is_active=False → status='inactive'."""
        ur = _load_routes(monkeypatch)
        from shared.pagination import PaginationParams

        user = _fake_user(status="active")
        membership = _fake_membership(is_active=False)
        role = _fake_role()

        db = MagicMock()
        call_count = [0]

        def _execute_side_effect(stmt):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar.return_value = 1
            else:
                result.all.return_value = [(user, membership, role)]
            return result

        db.execute.side_effect = _execute_side_effect

        result = asyncio.run(
            ur.list_users(
                pagination=PaginationParams(skip=0, limit=10),
                db=db,
            )
        )

        assert result.items[0].status == "inactive"

    def test_empty_result_returns_zero_total(self, monkeypatch):
        """Lines 56-88: no users in tenant → empty list, total=0."""
        ur = _load_routes(monkeypatch)
        from shared.pagination import PaginationParams

        db = MagicMock()
        call_count = [0]

        def _execute_side_effect(stmt):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar.return_value = 0
            else:
                result.all.return_value = []
            return result

        db.execute.side_effect = _execute_side_effect

        result = asyncio.run(
            ur.list_users(
                pagination=PaginationParams(skip=0, limit=10),
                db=db,
            )
        )

        assert result.total == 0
        assert result.items == []


# ---------------------------------------------------------------------------
# list_roles — lines 299-313
# ---------------------------------------------------------------------------


class TestListRolesHappyPath:

    def test_returns_role_list(self, monkeypatch):
        """Lines 299-313: list_roles with one custom role → PaginatedResponse
        with RoleResponse.is_system=False for tenant-scoped role."""
        ur = _load_routes(monkeypatch)
        from shared.pagination import PaginationParams

        role = _fake_role(tenant_id=TENANT_ID)  # Custom role (not system)

        db = MagicMock()
        call_count = [0]

        def _execute_side_effect(stmt):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar.return_value = 1
            else:
                result.scalars.return_value.all.return_value = [role]
            return result

        db.execute.side_effect = _execute_side_effect

        result = asyncio.run(
            ur.list_roles(
                pagination=PaginationParams(skip=0, limit=10),
                db=db,
            )
        )

        assert result.total == 1
        assert len(result.items) == 1
        assert result.items[0].name == "Member"
        assert result.items[0].is_system is False

    def test_system_role_has_is_system_true(self, monkeypatch):
        """Line 312: role with tenant_id=None → is_system=True."""
        ur = _load_routes(monkeypatch)
        from shared.pagination import PaginationParams

        system_role = _fake_role(tenant_id=None, name="Admin")

        db = MagicMock()
        call_count = [0]

        def _execute_side_effect(stmt):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar.return_value = 1
            else:
                result.scalars.return_value.all.return_value = [system_role]
            return result

        db.execute.side_effect = _execute_side_effect

        result = asyncio.run(
            ur.list_roles(
                pagination=PaginationParams(skip=0, limit=10),
                db=db,
            )
        )

        assert result.items[0].is_system is True

    def test_empty_roles_returns_zero_total(self, monkeypatch):
        """Lines 299-313: no roles in tenant → empty list."""
        ur = _load_routes(monkeypatch)
        from shared.pagination import PaginationParams

        db = MagicMock()
        call_count = [0]

        def _execute_side_effect(stmt):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar.return_value = 0
            else:
                result.scalars.return_value.all.return_value = []
            return result

        db.execute.side_effect = _execute_side_effect

        result = asyncio.run(
            ur.list_roles(
                pagination=PaginationParams(skip=0, limit=10),
                db=db,
            )
        )

        assert result.total == 0
        assert result.items == []
