"""Coverage sweep for tenant_settings_routes.py — the 3 lines #1341 missed.

This file tops off ``services/admin/app/tenant_settings_routes.py`` from
98% to 100%. The three branches left uncovered by
``test_tenant_settings_routes.py`` all exercise the narrow but real
"orphaned row" failure modes that arise when a caller's membership /
role is present but the referenced parent row has been deleted out of
band (e.g. a Tenant soft-delete or a Role row being cleaned up while
memberships still reference it).

Why the branches matter:

- **Line 42** — ``_get_tenant_for_user`` raises 404 when a valid
  membership row exists but ``db.get(TenantModel, tenant_id)`` returns
  ``None``. In practice this happens if the tenant was hard-deleted
  while a stale membership row lingered. Without this branch, the
  route would return an unresolved ``None`` and crash downstream at
  ``tenant.settings``; more importantly, keeping it at 404 (not 500)
  prevents enumerating deleted-tenant UUIDs via error-code signal. The
  ``get_onboarding_status`` endpoint is the public entrypoint to this
  helper.
- **Line 70** — ``_get_user_role_name`` returns ``None`` when the
  membership row's ``role_id`` does not resolve to a ``RoleModel``
  row. This guards against a crashed server if roles get retired /
  renamed without a cascading cleanup of memberships. The knock-on
  effect under the role gate is that the caller is treated as "no
  role" → 403, which is the correct fail-closed posture for #1386 —
  without this branch the helper would dereference ``None.name`` and
  500 instead of denying cleanly.
- **Line 107** — ``_require_tenant_admin`` raises 404 when the caller
  holds an admin/owner role but the tenant row is gone. Same
  deleted-tenant race as line 42, but on the privileged write path
  (``update_tenant_settings``). The distinction matters because this
  helper resolves the role BEFORE loading the tenant, so we need the
  404 fallthrough to avoid a second, different crash path on the
  PATCH endpoint.

Pattern: direct async-function invocation with a ``MagicMock`` DB,
mirroring ``test_tenant_settings_routes.py`` (which set up the
fixtures we reuse below). FastAPI ``TestClient`` is overkill here
because every branch is reachable from a direct call on the async
route functions — the #1341 harness already established this is the
ingestion-style pattern admin service tests are converging on (see
#1435).

# Tracks GitHub issue #1342.
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

# sys.path bootstrap (same as other admin tests — see #1435).
_SERVICE_DIR = Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SERVICE_DIR.parent
for _p in (_SERVICE_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
OWNER_ROLE_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")


def _fake_user(user_id=USER_ID, is_sysadmin=False):
    return SimpleNamespace(id=user_id, is_sysadmin=is_sysadmin)


def _fake_membership(role_id=OWNER_ROLE_ID, is_active=True):
    return SimpleNamespace(
        user_id=USER_ID, tenant_id=TENANT_ID,
        role_id=role_id, is_active=is_active,
    )


def _install_db(tenant, membership=None, role_name=None):
    """MagicMock DB matching the route's read pattern.

    db.execute(select(Membership))...scalar_one_or_none() -> membership
    db.get(TenantModel, id)  -> tenant (or None to trigger 404)
    db.get(RoleModel, id)    -> role with .name, or None to test the
                                missing-role branch (line 70).
    """
    db = MagicMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = membership
    db.execute.return_value = execute_result

    def _get(model_cls, ident):
        name = getattr(model_cls, "__name__", str(model_cls))
        if "Tenant" in name:
            return tenant
        if "Role" in name:
            if role_name is None:
                return None
            return SimpleNamespace(id=ident, name=role_name)
        return None

    db.get.side_effect = _get
    return db


def _load_routes(monkeypatch):
    """Neutralize SQLAlchemy's flag_modified so SimpleNamespace tenants
    don't trip the ``_sa_instance_state`` check. Same shim pattern as
    the sibling #1341 suite."""
    from services.admin.app import tenant_settings_routes as mod

    monkeypatch.setattr(mod, "flag_modified", lambda *a, **kw: None)
    return mod


# ---------------------------------------------------------------------------
# Line 42: _get_tenant_for_user 404 on orphaned membership
# ---------------------------------------------------------------------------


class TestGetTenantForUser_MissingTenant_1342:
    """Line 42: membership row exists but tenant was hard-deleted.

    Reached through ``get_onboarding_status`` (the only caller of
    ``_get_tenant_for_user`` in this module). The caller sees 404
    "Tenant not found", NOT 500 from a None.settings dereference.
    """

    def test_get_onboarding_404_when_tenant_missing(self, monkeypatch) -> None:
        mod = _load_routes(monkeypatch)
        membership = _fake_membership()
        # Membership is valid but Tenant has been deleted.
        db = _install_db(tenant=None, membership=membership)

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                mod.get_onboarding_status(
                    tenant_id=TENANT_ID,
                    user=_fake_user(),
                    db=db,
                )
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "Tenant not found"


# ---------------------------------------------------------------------------
# Line 70: _get_user_role_name returns None when role row missing
# ---------------------------------------------------------------------------


class TestGetUserRoleName_MissingRole_1342:
    """Line 70: membership exists, but ``db.get(RoleModel, role_id)``
    returns None (role deleted, or FK cleanup skipped).

    The helper must return None, which the role gate then interprets as
    "no role" → 403 on the mutating endpoint. The test exercises this
    end-to-end through ``update_tenant_settings`` so we observe the
    fail-closed outcome, not just the helper's raw return value.
    """

    def test_update_settings_403_when_role_row_missing(self, monkeypatch) -> None:
        mod = _load_routes(monkeypatch)
        tenant = SimpleNamespace(id=TENANT_ID, settings={})
        membership = _fake_membership()
        # role_name=None makes the MagicMock return None for db.get(RoleModel, ...).
        db = _install_db(tenant=tenant, membership=membership, role_name=None)

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                mod.update_tenant_settings(
                    tenant_id=TENANT_ID,
                    payload=mod.SettingsUpdate(workspace_profile={"x": 1}),
                    user=_fake_user(),
                    db=db,
                )
            )
        # _get_user_role_name returns None (line 70), _require_tenant_admin
        # sees role_name is None and raises the "not a member" 403.
        assert exc.value.status_code == 403
        assert "member" in exc.value.detail.lower()

    def test_helper_returns_none_directly(self, monkeypatch) -> None:
        """Direct unit assertion on the helper's return value for line 70."""
        mod = _load_routes(monkeypatch)
        tenant = SimpleNamespace(id=TENANT_ID, settings={})
        membership = _fake_membership()
        db = _install_db(tenant=tenant, membership=membership, role_name=None)

        assert mod._get_user_role_name(TENANT_ID, _fake_user(), db) is None


# ---------------------------------------------------------------------------
# Line 107: _require_tenant_admin 404 when role checks pass but tenant gone
# ---------------------------------------------------------------------------


class TestRequireTenantAdmin_MissingTenant_1342:
    """Line 107: user is a valid Owner, but the tenant row was deleted
    between the role lookup and the tenant fetch (or was deleted while
    the membership row lingered).

    ``_require_tenant_admin`` resolves the role first (via
    ``_get_user_role_name``) then loads the tenant. If the tenant is
    gone at step 2, the helper must still 404 cleanly rather than
    returning a partially-populated object. ``update_tenant_settings``
    is the privileged entrypoint.
    """

    def test_update_settings_404_when_tenant_missing_but_role_ok(
        self, monkeypatch,
    ) -> None:
        mod = _load_routes(monkeypatch)
        membership = _fake_membership(role_id=OWNER_ROLE_ID)
        # Role resolves fine (role_name="Owner") but tenant=None.
        db = _install_db(tenant=None, membership=membership, role_name="Owner")

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                mod.update_tenant_settings(
                    tenant_id=TENANT_ID,
                    payload=mod.SettingsUpdate(workspace_profile={"x": 1}),
                    user=_fake_user(),
                    db=db,
                )
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "Tenant not found"

    def test_sysadmin_also_404s_when_tenant_missing(self, monkeypatch) -> None:
        """Sysadmin bypasses the role check but still hits the tenant
        load; the 404 on line 107 must fire for them too, not just for
        tenant-scoped admins."""
        mod = _load_routes(monkeypatch)
        # No membership needed — sysadmin branch returns "Sysadmin".
        db = _install_db(tenant=None, membership=None)

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                mod.update_tenant_settings(
                    tenant_id=TENANT_ID,
                    payload=mod.SettingsUpdate(workspace_profile={"x": 1}),
                    user=_fake_user(is_sysadmin=True),
                    db=db,
                )
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "Tenant not found"
