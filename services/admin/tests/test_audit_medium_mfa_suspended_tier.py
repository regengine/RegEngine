"""Regression tests for the audit-medium MFA/suspended-tenant/role-tier batch.

Four independent fail-closed gaps, one file:

1. MFA secrets stored plaintext when no encryption key is set. Production
   startup must refuse to boot without ``MFA_ENCRYPTION_KEY``, and
   ``store_mfa_secret_on_user`` must refuse plaintext enrollment in a strict
   auth runtime instead of storing the seed in the clear.
2. MFA brute-force guards skipped when no session store is wired.
   ``require_mfa`` (and the dormant counter helpers) must deny the attempt
   with a retryable 503 in a strict runtime instead of verifying unthrottled.
3. API-key logins skip the suspended-tenant check that cookie and refresh
   logins perform. ``get_current_tenant`` must deny keys bound to a
   non-active tenant.
4. Role changes lack the tier check invites have. ``update_user_role`` must
   apply ``can_invite_role`` so a low-tier holder of ``users.manage_roles``
   cannot self-promote (or promote anyone) to Owner.

Pattern: direct async-function invocation with MagicMock sessions, following
test_mfa_fail_closed_ws3.py and test_user_routes.py. Strict runtime is
simulated with REGENGINE_ENV=production (is_production reads it first, so no
cloud markers are needed).
"""

from __future__ import annotations

import asyncio
import sys
import types as _types
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "services"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Stub pyotp before importing the mfa module (mirrors test_mfa_fail_closed_ws3).
if "pyotp" not in sys.modules:

    class _FakeTOTP:
        def __init__(self, secret):
            self._secret = secret

        def verify(self, token, valid_window=1):
            return token == "999111"

        def provisioning_uri(self, name=None, issuer_name=None):
            return f"otpauth://totp/{issuer_name}:{name}?secret={self._secret}"

    _pyotp_stub = _types.ModuleType("pyotp")
    _pyotp_stub.TOTP = _FakeTOTP
    _pyotp_stub.random_base32 = lambda: "JBSWY3DPEHPK3PXP"
    sys.modules["pyotp"] = _pyotp_stub

# Pre-generated valid Fernet key (same role as _FERNET_KEY in test_mfa_1342).
_FERNET_KEY = "6UMC7WJRL-mfToH9-qLM_g0ppGz1A4FXT58AGigrDr4="

TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TARGET_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
ACTOR_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
OWNER_ROLE_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
MEMBER_ROLE_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000002")


def _set_strict(monkeypatch):
    """Simulate a strict auth runtime (production without cloud markers)."""
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("REGENGINE_AUTH_STRICT", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/regengine")
    monkeypatch.setenv("REDIS_URL", "redis://example.invalid/0")


def _set_non_strict(monkeypatch):
    from shared.env import CLOUD_ENV_VARS

    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("REGENGINE_AUTH_STRICT", raising=False)
    for name in CLOUD_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")


# ---------------------------------------------------------------------------
# 1. MFA encryption key required at startup / no plaintext in strict
# ---------------------------------------------------------------------------


class TestStrictStartupRequiresMfaKey:
    def test_production_startup_refuses_without_mfa_key(self, monkeypatch):
        from services.admin.app.auth_runtime import (
            AuthRuntimeConfigurationError,
            load_auth_runtime_config,
        )

        _set_strict(monkeypatch)
        monkeypatch.delenv("MFA_ENCRYPTION_KEY", raising=False)
        with pytest.raises(AuthRuntimeConfigurationError, match="MFA_ENCRYPTION_KEY"):
            load_auth_runtime_config()

    def test_production_startup_rejects_invalid_mfa_key(self, monkeypatch):
        from services.admin.app.auth_runtime import (
            AuthRuntimeConfigurationError,
            load_auth_runtime_config,
        )

        _set_strict(monkeypatch)
        monkeypatch.setenv("MFA_ENCRYPTION_KEY", "not-a-valid-fernet-key")
        with pytest.raises(AuthRuntimeConfigurationError, match="MFA_ENCRYPTION_KEY"):
            load_auth_runtime_config()

    def test_production_startup_accepts_valid_mfa_key(self, monkeypatch):
        from services.admin.app.auth_runtime import load_auth_runtime_config

        _set_strict(monkeypatch)
        monkeypatch.setenv("MFA_ENCRYPTION_KEY", _FERNET_KEY)
        assert load_auth_runtime_config().strict is True

    def test_store_mfa_secret_refuses_plaintext_in_strict(self, monkeypatch):
        from services.admin.app.mfa import store_mfa_secret_on_user

        _set_strict(monkeypatch)
        monkeypatch.delenv("MFA_ENCRYPTION_KEY", raising=False)
        user = SimpleNamespace(mfa_secret=None, mfa_secret_ciphertext=None)
        with pytest.raises(RuntimeError, match="MFA_ENCRYPTION_KEY"):
            store_mfa_secret_on_user(user, "STRICT_PLAINTEXT")
        assert user.mfa_secret is None

    def test_store_mfa_secret_plaintext_fallback_stays_in_dev(self, monkeypatch):
        from services.admin.app.mfa import store_mfa_secret_on_user

        _set_non_strict(monkeypatch)
        monkeypatch.delenv("MFA_ENCRYPTION_KEY", raising=False)
        user = SimpleNamespace(mfa_secret=None, mfa_secret_ciphertext="stale")
        store_mfa_secret_on_user(user, "DEV_ONLY_SECRET")
        assert user.mfa_secret == "DEV_ONLY_SECRET"
        assert user.mfa_secret_ciphertext is None


# ---------------------------------------------------------------------------
# 2. MFA brute-force guard must fail closed without a session store
# ---------------------------------------------------------------------------


def _mfa_user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="mfa-case@example.com",
        mfa_secret="TESTBASE32SECRET",  # pragma: allowlist secret
        mfa_secret_ciphertext=None,
    )


class TestMfaMissingStoreFailsClosed:
    def test_require_mfa_without_store_denied_in_strict(self, monkeypatch):
        from services.admin.app.mfa import require_mfa

        _set_strict(monkeypatch)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                require_mfa(
                    x_mfa_token="999111",
                    current_user=_mfa_user(),
                    db=MagicMock(),
                    session_store=None,
                )
            )
        assert exc.value.status_code == 503

    def test_require_mfa_without_store_still_skips_in_dev(self, monkeypatch):
        from services.admin.app.mfa import require_mfa

        _set_non_strict(monkeypatch)
        result = asyncio.run(
            require_mfa(
                x_mfa_token="999111",
                current_user=_mfa_user(),
                db=MagicMock(),
                session_store=None,
            )
        )
        assert result == "999111"

    def test_require_mfa_bad_token_still_rejected_in_dev(self, monkeypatch):
        # The dev skip only bypasses throttling, not verification: a wrong
        # token must still fail with 403 when no store is wired.
        from services.admin.app.mfa import require_mfa

        _set_non_strict(monkeypatch)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                require_mfa(
                    x_mfa_token="000000",
                    current_user=_mfa_user(),
                    db=MagicMock(),
                    session_store=None,
                )
            )
        assert exc.value.status_code == 403

    def test_dormant_counter_helpers_without_store_denied_in_strict(self, monkeypatch):
        from services.admin.app import mfa as mfa_module

        _set_strict(monkeypatch)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(mfa_module._check_mfa_counter_lockout(None, "user-1"))
        assert exc.value.status_code == 503
        with pytest.raises(HTTPException) as exc:
            asyncio.run(mfa_module._record_mfa_counter_failure(None, "user-1"))
        assert exc.value.status_code == 503
        # Reset stays best-effort: nothing to clear, never raises.
        asyncio.run(mfa_module._reset_mfa_counter_failures(None, "user-1"))


# ---------------------------------------------------------------------------
# 3. API-key logins must enforce the suspended-tenant check
# ---------------------------------------------------------------------------


class TestApiKeySuspendedTenant:
    def _load_deps(self, monkeypatch, tenant_status):
        from services.admin.app import dependencies as deps_mod

        async def _fake_get_store():
            store = MagicMock()

            async def _validate_key(_key):
                return SimpleNamespace(tenant_id=str(TENANT_ID))

            store.validate_key = _validate_key
            return store

        monkeypatch.setattr(deps_mod, "get_db_key_store", _fake_get_store)
        db = MagicMock()
        if isinstance(tenant_status, Exception):
            db.get.side_effect = tenant_status
        else:
            db.get.return_value = (
                None if tenant_status is None else SimpleNamespace(status=tenant_status)
            )
        return deps_mod, db

    def test_suspended_tenant_api_key_rejected(self, monkeypatch):
        from services.admin.app import dependencies as deps_mod  # noqa: F401

        deps_mod, db = self._load_deps(monkeypatch, "suspended")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps_mod.get_current_tenant(key="valid-key", db=db))
        assert exc.value.status_code == 403
        assert exc.value.detail == "Invalid API Key"

    def test_archived_tenant_api_key_rejected(self, monkeypatch):
        from services.admin.app import dependencies as deps_mod  # noqa: F401

        deps_mod, db = self._load_deps(monkeypatch, "archived")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps_mod.get_current_tenant(key="valid-key", db=db))
        assert exc.value.status_code == 403
        assert exc.value.detail == "Invalid API Key"

    def test_missing_tenant_row_api_key_rejected(self, monkeypatch):
        from services.admin.app import dependencies as deps_mod  # noqa: F401

        deps_mod, db = self._load_deps(monkeypatch, None)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps_mod.get_current_tenant(key="valid-key", db=db))
        assert exc.value.status_code == 403
        assert exc.value.detail == "Invalid API Key"

    def test_tenant_lookup_failure_fails_closed_503(self, monkeypatch):
        from services.admin.app import dependencies as deps_mod  # noqa: F401

        deps_mod, db = self._load_deps(monkeypatch, ConnectionError("db down"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(deps_mod.get_current_tenant(key="valid-key", db=db))
        assert exc.value.status_code == 503

    @pytest.mark.parametrize("tenant_status", ["active", "trial"])
    def test_active_tenant_api_key_allowed(self, monkeypatch, tenant_status):
        from services.admin.app import dependencies as deps_mod  # noqa: F401

        deps_mod, db = self._load_deps(monkeypatch, tenant_status)
        assert asyncio.run(deps_mod.get_current_tenant(key="valid-key", db=db)) == TENANT_ID


# ---------------------------------------------------------------------------
# 4. Role changes must enforce the invite tier check (#1387 parity)
# ---------------------------------------------------------------------------


def _load_user_routes(monkeypatch):
    from services.admin.app import audit as audit_mod, models as models_mod, user_routes as user_routes_mod

    monkeypatch.setattr(
        models_mod.TenantContext,
        "get_tenant_context",
        staticmethod(lambda _db: TENANT_ID),
    )
    monkeypatch.setattr(
        user_routes_mod.TenantContext,
        "get_tenant_context",
        staticmethod(lambda _db: TENANT_ID),
    )
    audit_calls: list[dict] = []

    def _fake_log_event(db, **kwargs):
        audit_calls.append(dict(kwargs))
        return 1

    monkeypatch.setattr(audit_mod.AuditLogger, "log_event", _fake_log_event)
    monkeypatch.setattr(user_routes_mod.AuditLogger, "log_event", _fake_log_event)
    return user_routes_mod, audit_calls


def _role(role_id, name, permissions):
    return SimpleNamespace(id=role_id, name=name, tenant_id=TENANT_ID, permissions=permissions)


class TestRoleChangeTierCheck:
    def _db_for_role_change(
        self,
        current_role_name,
        target_role,
        caller_role_name="Member",
        caller_permissions=(),
        current_role_permissions=(),
        membership_role_id=None,
    ):
        """Mock db: membership lookup, caller-role lookup, role gets."""
        membership_role_id = membership_role_id or MEMBER_ROLE_ID
        db = MagicMock()
        membership = SimpleNamespace(
            user_id=TARGET_USER_ID,
            tenant_id=TENANT_ID,
            role_id=membership_role_id,
            is_active=True,
        )
        caller_role = SimpleNamespace(
            id=uuid.uuid4(),
            name=caller_role_name,
            tenant_id=TENANT_ID,
            permissions=list(caller_permissions),
        )
        current_role = SimpleNamespace(
            id=membership_role_id,
            name=current_role_name,
            tenant_id=TENANT_ID,
            permissions=list(current_role_permissions),
        )

        def _get(model, ident):
            if ident == target_role.id:
                return target_role
            if ident == membership_role_id:
                return current_role
            return None

        db.get.side_effect = _get
        call_count = {"n": 0}

        def _execute(stmt):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.scalar_one_or_none.return_value = membership
            else:
                # Caller-role lookup for the tier check.
                result.scalar_one_or_none.return_value = caller_role
            return result

        db.execute.side_effect = _execute
        return db, membership

    def test_member_cannot_promote_to_owner(self, monkeypatch):
        user_routes_mod, audit_calls = _load_user_routes(monkeypatch)
        owner_role = _role(OWNER_ROLE_ID, "Owner", ["*"])
        db, membership = self._db_for_role_change("Member", owner_role, caller_role_name="Member")
        actor = SimpleNamespace(id=ACTOR_ID, email="actor@example.com", is_sysadmin=False)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                user_routes_mod.update_user_role(
                    user_id=TARGET_USER_ID,
                    update=user_routes_mod.RoleUpdate(role_id=OWNER_ROLE_ID),
                    current_user=actor,
                    db=db,
                )
            )
        assert exc.value.status_code == 403
        assert membership.role_id == MEMBER_ROLE_ID
        assert audit_calls == []
        db.commit.assert_not_called()

    def test_grant_owner_hatch_does_not_promote_via_role_route(self, monkeypatch):
        # users.invite.grant_owner lets a non-Owner invite a future Owner.
        # It must not let them promote a current member (self included) to
        # Owner through PATCH /admin/users/{user_id}/role.
        user_routes_mod, audit_calls = _load_user_routes(monkeypatch)
        owner_role = _role(OWNER_ROLE_ID, "Owner", ["*"])
        db, membership = self._db_for_role_change(
            "Member",
            owner_role,
            caller_role_name="Admin",
            caller_permissions=["users.manage_roles", "users.invite.grant_owner"],
        )
        actor = SimpleNamespace(id=ACTOR_ID, email="actor@example.com", is_sysadmin=False)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                user_routes_mod.update_user_role(
                    user_id=TARGET_USER_ID,
                    update=user_routes_mod.RoleUpdate(role_id=OWNER_ROLE_ID),
                    current_user=actor,
                    db=db,
                )
            )
        assert exc.value.status_code == 403
        assert membership.role_id == MEMBER_ROLE_ID
        assert audit_calls == []
        db.commit.assert_not_called()

    def test_admin_cannot_demote_other_owner(self, monkeypatch):
        # The tier check compares the caller to the destination role only.
        # An Admin must also be blocked from moving a member whose current
        # role outranks their own, even when another Owner remains.
        user_routes_mod, audit_calls = _load_user_routes(monkeypatch)
        monkeypatch.setattr(
            user_routes_mod,
            "_other_authenticating_owners",
            lambda _db, _tenant_id, _exclude: [SimpleNamespace(user_id=uuid.uuid4())],
        )
        member_role = _role(uuid.uuid4(), "Member", [])
        db, membership = self._db_for_role_change(
            "Owner",
            member_role,
            caller_role_name="Admin",
            caller_permissions=["users.manage_roles"],
            current_role_permissions=["*"],
            membership_role_id=OWNER_ROLE_ID,
        )
        actor = SimpleNamespace(id=ACTOR_ID, email="actor@example.com", is_sysadmin=False)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                user_routes_mod.update_user_role(
                    user_id=TARGET_USER_ID,
                    update=user_routes_mod.RoleUpdate(role_id=member_role.id),
                    current_user=actor,
                    db=db,
                )
            )
        assert exc.value.status_code == 403
        assert membership.role_id == OWNER_ROLE_ID
        assert audit_calls == []
        db.commit.assert_not_called()

    def test_owner_can_assign_member(self, monkeypatch):
        user_routes_mod, audit_calls = _load_user_routes(monkeypatch)
        member_role = _role(MEMBER_ROLE_ID, "Member", [])
        db, membership = self._db_for_role_change("Member", member_role, caller_role_name="Owner")
        actor = SimpleNamespace(id=ACTOR_ID, email="actor@example.com", is_sysadmin=False)
        response = asyncio.run(
            user_routes_mod.update_user_role(
                user_id=TARGET_USER_ID,
                update=user_routes_mod.RoleUpdate(role_id=MEMBER_ROLE_ID),
                current_user=actor,
                db=db,
            )
        )
        assert response == {"status": "updated"} or response.get("status") == "updated"
        assert membership.role_id == MEMBER_ROLE_ID
        assert len(audit_calls) == 1

    def test_sysadmin_bypasses_tier_check(self, monkeypatch):
        user_routes_mod, _ = _load_user_routes(monkeypatch)
        owner_role = _role(OWNER_ROLE_ID, "Owner", ["*"])
        db = MagicMock()
        membership = SimpleNamespace(
            user_id=TARGET_USER_ID,
            tenant_id=TENANT_ID,
            role_id=MEMBER_ROLE_ID,
            is_active=True,
        )
        current_role = SimpleNamespace(
            id=MEMBER_ROLE_ID, name="Member", tenant_id=TENANT_ID, permissions=[]
        )

        def _get(model, ident):
            if ident == OWNER_ROLE_ID:
                return owner_role
            if ident == MEMBER_ROLE_ID:
                return current_role
            return None

        db.get.side_effect = _get
        result = MagicMock()
        result.scalar_one_or_none.return_value = membership
        db.execute.return_value = result
        actor = SimpleNamespace(id=ACTOR_ID, email="root@example.com", is_sysadmin=True)
        response = asyncio.run(
            user_routes_mod.update_user_role(
                user_id=TARGET_USER_ID,
                update=user_routes_mod.RoleUpdate(role_id=OWNER_ROLE_ID),
                current_user=actor,
                db=db,
            )
        )
        assert response == {"status": "updated"} or response.get("status") == "updated"
        assert membership.role_id == OWNER_ROLE_ID

    def test_actor_without_tenant_role_rejected(self, monkeypatch):
        user_routes_mod, _ = _load_user_routes(monkeypatch)
        member_role = _role(MEMBER_ROLE_ID, "Member", [])
        db = MagicMock()
        membership = SimpleNamespace(
            user_id=TARGET_USER_ID,
            tenant_id=TENANT_ID,
            role_id=MEMBER_ROLE_ID,
            is_active=True,
        )
        current_role = SimpleNamespace(
            id=MEMBER_ROLE_ID, name="Member", tenant_id=TENANT_ID, permissions=[]
        )

        def _get(model, ident):
            if ident == MEMBER_ROLE_ID:
                return member_role if ident == MEMBER_ROLE_ID else current_role
            return None

        db.get.side_effect = _get
        call_count = {"n": 0}

        def _execute(stmt):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.scalar_one_or_none.return_value = membership
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute.side_effect = _execute
        actor = SimpleNamespace(id=ACTOR_ID, email="actor@example.com", is_sysadmin=False)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                user_routes_mod.update_user_role(
                    user_id=TARGET_USER_ID,
                    update=user_routes_mod.RoleUpdate(role_id=MEMBER_ROLE_ID),
                    current_user=actor,
                    db=db,
                )
            )
        assert exc.value.status_code == 403
