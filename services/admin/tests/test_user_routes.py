"""Regression tests for admin user_routes (#1341).

Before this suite, ``services/admin/app/user_routes.py`` (313 LOC, 5
endpoints) had no dedicated test file. The module guards two of the
highest-blast-radius invariants in the admin service:

1. **Last-Owner protection (#1083)**: demoting or deactivating the
   only remaining Owner of a tenant would lock every user out of
   their own account. The protection runs under a ``SELECT ... FOR
   UPDATE`` lock to defeat the concurrent-demotion race where two
   requests each see one Owner remaining.

2. **Sysadmin reactivation block (#1406)**: a tenant Owner must not
   be able to re-enable a sysadmin's dormant membership (that would
   hand a customer the ability to resurrect cross-tenant access for
   an engineer who debugged their tenant months ago).

The routes also emit tamper-evident audit entries for every state
change (role change, deactivate, reactivate, reactivate_blocked).
Without tests a future refactor could silently drop any of these
emissions and CI would stay green.

Pattern: direct async-function invocation with MagicMock sessions.
TestClient round-trips are blocked in admin by #1435 (pytest
collection stale imports) so we follow the established pattern used
in ``test_compliance_routes_idor.py`` and ``test_get_current_user_*``.
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
TARGET_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
ACTOR_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
OWNER_ROLE_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
MEMBER_ROLE_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000002")


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


def _load_routes(monkeypatch):
    """Import user_routes and patch TenantContext / AuditLogger.

    Returns a tuple of (module, audit_calls, set_tenant, clear_tenant).
    """
    from services.admin.app import user_routes as user_routes_mod
    from services.admin.app import models as models_mod
    from services.admin.app import audit as audit_mod

    # Install deterministic TenantContext stub.
    monkeypatch.setattr(
        models_mod.TenantContext,
        "get_tenant_context",
        staticmethod(lambda _db: TENANT_ID),
    )
    # Mirror the patch on the symbol user_routes imported.
    monkeypatch.setattr(
        user_routes_mod.TenantContext,
        "get_tenant_context",
        staticmethod(lambda _db: TENANT_ID),
    )

    # Capture AuditLogger.log_event invocations.
    audit_calls: list[dict] = []

    def _fake_log_event(db, **kwargs):
        audit_calls.append(dict(kwargs))
        return 1

    monkeypatch.setattr(audit_mod.AuditLogger, "log_event", _fake_log_event)
    monkeypatch.setattr(
        user_routes_mod.AuditLogger, "log_event", _fake_log_event
    )

    return user_routes_mod, audit_calls


def _fake_role(role_id: uuid.UUID, name: str, tenant_id=TENANT_ID):
    """Build a fake RoleModel with the attributes our routes read."""
    return SimpleNamespace(id=role_id, name=name, tenant_id=tenant_id)


def _fake_membership(user_id=TARGET_USER_ID, role_id=MEMBER_ROLE_ID, is_active=True):
    return SimpleNamespace(
        user_id=user_id,
        tenant_id=TENANT_ID,
        role_id=role_id,
        is_active=is_active,
    )


def _fake_user(user_id=TARGET_USER_ID, is_sysadmin=False):
    return SimpleNamespace(
        id=user_id,
        email=f"{user_id}@example.com",
        is_sysadmin=is_sysadmin,
    )


# ---------------------------------------------------------------------------
# list_users
# ---------------------------------------------------------------------------


class TestListUsers_Issue1341:
    def test_returns_400_when_no_tenant_context(self, monkeypatch) -> None:
        """Defensive: if the RLS context isn't populated (e.g. sysadmin
        hit the endpoint directly without selecting a tenant), the
        handler must 400 rather than returning a cross-tenant dump."""
        user_routes_mod, _ = _load_routes(monkeypatch)
        monkeypatch.setattr(
            user_routes_mod.TenantContext,
            "get_tenant_context",
            staticmethod(lambda _db: None),
        )

        from shared.pagination import PaginationParams

        db = MagicMock()

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                user_routes_mod.list_users(
                    pagination=PaginationParams(skip=0, limit=10),
                    db=db,
                )
            )
        assert exc.value.status_code == 400
        assert "Tenant context" in exc.value.detail


# ---------------------------------------------------------------------------
# update_user_role
# ---------------------------------------------------------------------------


class TestUpdateUserRole_Issue1341:
    def test_returns_400_when_no_tenant_context(self, monkeypatch) -> None:
        user_routes_mod, _ = _load_routes(monkeypatch)
        monkeypatch.setattr(
            user_routes_mod.TenantContext,
            "get_tenant_context",
            staticmethod(lambda _db: None),
        )
        db = MagicMock()
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                user_routes_mod.update_user_role(
                    user_id=TARGET_USER_ID,
                    update=user_routes_mod.RoleUpdate(role_id=MEMBER_ROLE_ID),
                    current_user=_fake_user(ACTOR_ID, is_sysadmin=False),
                    db=db,
                )
            )
        assert exc.value.status_code == 400

    def test_returns_404_when_user_not_in_tenant(self, monkeypatch) -> None:
        """A user who belongs to another tenant must appear as 'not
        found' in this tenant's surface. Leaking 'exists in other
        tenant' would be a tenant-probing oracle."""
        user_routes_mod, _ = _load_routes(monkeypatch)
        db = MagicMock()

        # select(MembershipModel)....scalar_one_or_none() -> None
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                user_routes_mod.update_user_role(
                    user_id=TARGET_USER_ID,
                    update=user_routes_mod.RoleUpdate(role_id=MEMBER_ROLE_ID),
                    current_user=_fake_user(ACTOR_ID, is_sysadmin=False),
                    db=db,
                )
            )
        assert exc.value.status_code == 404
        assert "not found" in exc.value.detail.lower()

    def test_returns_400_when_role_does_not_exist(self, monkeypatch) -> None:
        """Target role_id that doesn't resolve → 400 (not 500). The
        caller supplied an invalid UUID; don't crash."""
        user_routes_mod, _ = _load_routes(monkeypatch)
        db = MagicMock()

        membership = _fake_membership(role_id=MEMBER_ROLE_ID)
        result = MagicMock()
        result.scalar_one_or_none.return_value = membership
        db.execute.return_value = result
        # db.get(RoleModel, update.role_id) → None (role doesn't exist)
        db.get.return_value = None

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                user_routes_mod.update_user_role(
                    user_id=TARGET_USER_ID,
                    update=user_routes_mod.RoleUpdate(role_id=OWNER_ROLE_ID),
                    current_user=_fake_user(ACTOR_ID, is_sysadmin=False),
                    db=db,
                )
            )
        assert exc.value.status_code == 400
        assert "Role not found" in exc.value.detail

    def test_blocks_demotion_of_last_owner(self, monkeypatch) -> None:
        """#1083: the only remaining Owner must not be demotable. A
        regression here would let a tenant be left with zero Owners
        and lock every user out of the tenant settings."""
        user_routes_mod, _ = _load_routes(monkeypatch)
        db = MagicMock()

        # Membership exists, currently Owner.
        current_membership = _fake_membership(role_id=OWNER_ROLE_ID)
        owner_role = _fake_role(OWNER_ROLE_ID, "Owner")
        member_role = _fake_role(MEMBER_ROLE_ID, "Member")

        # db.get(RoleModel, target_role_id) → Member (the demotion target)
        # db.get(RoleModel, current_role_id) → Owner (the current role)
        def _get(model, ident):
            if ident == MEMBER_ROLE_ID:
                return member_role
            if ident == OWNER_ROLE_ID:
                return owner_role
            return None

        db.get.side_effect = _get

        # Two execute calls in sequence:
        # 1. membership lookup with FOR UPDATE → returns current_membership
        # 2. other-owner lookup → returns [] (no other owners)
        call_count = {"n": 0}

        def _execute(stmt):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.scalar_one_or_none.return_value = current_membership
            else:
                # "locked_owners" query returns no other owners.
                result.all.return_value = []
            return result

        db.execute.side_effect = _execute

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                user_routes_mod.update_user_role(
                    user_id=TARGET_USER_ID,
                    update=user_routes_mod.RoleUpdate(role_id=MEMBER_ROLE_ID),
                    current_user=_fake_user(ACTOR_ID, is_sysadmin=False),
                    db=db,
                )
            )
        assert exc.value.status_code == 400
        assert "last Owner" in exc.value.detail, (
            "Regression: last-Owner demotion must be rejected with a "
            "specific error — a generic 400 would hide the #1083 guard"
        )

    def test_allows_demotion_when_other_owners_exist(
        self, monkeypatch,
    ) -> None:
        """Demotion of an Owner succeeds when at least one other Owner
        remains. Audit log must capture old/new role."""
        user_routes_mod, audit_calls = _load_routes(monkeypatch)
        db = MagicMock()

        current_membership = _fake_membership(role_id=OWNER_ROLE_ID)
        owner_role = _fake_role(OWNER_ROLE_ID, "Owner")
        member_role = _fake_role(MEMBER_ROLE_ID, "Member")

        def _get(model, ident):
            if ident == MEMBER_ROLE_ID:
                return member_role
            if ident == OWNER_ROLE_ID:
                return owner_role
            return None

        db.get.side_effect = _get

        # Two execute calls: membership lookup + other-owner lookup.
        # Second call returns a non-empty list so the last-owner check
        # passes.
        other_owner = _fake_membership(
            user_id=uuid.uuid4(), role_id=OWNER_ROLE_ID,
        )
        call_count = {"n": 0}

        def _execute(stmt):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.scalar_one_or_none.return_value = current_membership
            else:
                result.all.return_value = [(other_owner,)]
            return result

        db.execute.side_effect = _execute

        response = asyncio.run(
            user_routes_mod.update_user_role(
                user_id=TARGET_USER_ID,
                update=user_routes_mod.RoleUpdate(role_id=MEMBER_ROLE_ID),
                current_user=_fake_user(ACTOR_ID, is_sysadmin=False),
                db=db,
            )
        )
        # Route returns a dict with status key.
        assert response == {"status": "updated"} or response.get("status") == "updated"
        # Role was mutated on the membership.
        assert current_membership.role_id == MEMBER_ROLE_ID
        # Audit log was emitted with the right metadata.
        assert len(audit_calls) == 1
        assert audit_calls[0]["event_type"] == "membership.role_change"
        assert audit_calls[0]["resource_id"] == str(TARGET_USER_ID)
        assert audit_calls[0]["actor_id"] == ACTOR_ID
        meta = audit_calls[0]["metadata"]
        assert meta["new_role"] == str(MEMBER_ROLE_ID)
        assert meta["old_role"] == str(OWNER_ROLE_ID)
        db.commit.assert_called_once()

    def test_non_owner_role_change_skips_last_owner_check(
        self, monkeypatch,
    ) -> None:
        """Role change from Member → Member (or Admin) does NOT trigger
        the last-owner guard. That guard runs only when demoting AWAY
        from Owner."""
        user_routes_mod, audit_calls = _load_routes(monkeypatch)
        db = MagicMock()

        current_membership = _fake_membership(role_id=MEMBER_ROLE_ID)
        member_role = _fake_role(MEMBER_ROLE_ID, "Member")
        admin_role_id = uuid.UUID("cccccccc-0000-0000-0000-000000000003")
        admin_role = _fake_role(admin_role_id, "Admin")

        def _get(model, ident):
            if ident == MEMBER_ROLE_ID:
                return member_role
            if ident == admin_role_id:
                return admin_role
            return None

        db.get.side_effect = _get

        # Only ONE execute call should be made (membership lookup) —
        # no second call for the owner lock since current role is not Owner.
        call_count = {"n": 0}

        def _execute(stmt):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.scalar_one_or_none.return_value = current_membership
            else:
                pytest.fail(
                    "Should not query locked owners when demoting a "
                    "non-Owner — that's wasted DB work and suggests the "
                    "guard fires too eagerly"
                )
            return result

        db.execute.side_effect = _execute

        response = asyncio.run(
            user_routes_mod.update_user_role(
                user_id=TARGET_USER_ID,
                update=user_routes_mod.RoleUpdate(role_id=admin_role_id),
                current_user=_fake_user(ACTOR_ID, is_sysadmin=False),
                db=db,
            )
        )
        assert response == {"status": "updated"} or response.get("status") == "updated"
        assert current_membership.role_id == admin_role_id
        assert len(audit_calls) == 1


# ---------------------------------------------------------------------------
# deactivate_user
# ---------------------------------------------------------------------------


class TestDeactivateUser_Issue1341:
    def test_returns_400_when_no_tenant_context(self, monkeypatch) -> None:
        user_routes_mod, _ = _load_routes(monkeypatch)
        monkeypatch.setattr(
            user_routes_mod.TenantContext,
            "get_tenant_context",
            staticmethod(lambda _db: None),
        )
        db = MagicMock()
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                user_routes_mod.deactivate_user(
                    user_id=TARGET_USER_ID,
                    current_user=_fake_user(ACTOR_ID, is_sysadmin=False),
                    db=db,
                )
            )
        assert exc.value.status_code == 400

    def test_returns_404_when_membership_missing(self, monkeypatch) -> None:
        user_routes_mod, _ = _load_routes(monkeypatch)
        db = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                user_routes_mod.deactivate_user(
                    user_id=TARGET_USER_ID,
                    current_user=_fake_user(ACTOR_ID, is_sysadmin=False),
                    db=db,
                )
            )
        assert exc.value.status_code == 404

    def test_blocks_deactivation_of_last_owner(self, monkeypatch) -> None:
        """Twin of the demote-last-Owner test — deactivating the only
        remaining Owner zeroes out the tenant too (#1083)."""
        user_routes_mod, _ = _load_routes(monkeypatch)
        db = MagicMock()

        current_membership = _fake_membership(role_id=OWNER_ROLE_ID)
        owner_role = _fake_role(OWNER_ROLE_ID, "Owner")

        db.get.return_value = owner_role

        call_count = {"n": 0}

        def _execute(stmt):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.scalar_one_or_none.return_value = current_membership
            else:
                # No other owners — the deactivation must be blocked.
                result.all.return_value = []
            return result

        db.execute.side_effect = _execute

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                user_routes_mod.deactivate_user(
                    user_id=TARGET_USER_ID,
                    current_user=_fake_user(ACTOR_ID, is_sysadmin=False),
                    db=db,
                )
            )
        assert exc.value.status_code == 400
        assert "last Owner" in exc.value.detail
        # is_active must NOT have been flipped.
        assert current_membership.is_active is True

    def test_happy_path_soft_deletes_and_audits(self, monkeypatch) -> None:
        user_routes_mod, audit_calls = _load_routes(monkeypatch)
        db = MagicMock()

        current_membership = _fake_membership(
            role_id=MEMBER_ROLE_ID, is_active=True,
        )
        member_role = _fake_role(MEMBER_ROLE_ID, "Member")
        db.get.return_value = member_role

        result = MagicMock()
        result.scalar_one_or_none.return_value = current_membership
        db.execute.return_value = result

        response = asyncio.run(
            user_routes_mod.deactivate_user(
                user_id=TARGET_USER_ID,
                current_user=_fake_user(ACTOR_ID, is_sysadmin=False),
                db=db,
            )
        )
        assert response == {"status": "deactivated"} or response.get("status") == "deactivated"
        assert current_membership.is_active is False, (
            "Soft-delete invariant: deactivation flips is_active, does "
            "NOT remove the row (audit trail + reactivation path)"
        )
        assert len(audit_calls) == 1
        assert audit_calls[0]["event_type"] == "membership.deactivate"
        assert audit_calls[0]["metadata"]["is_active"] is False
        db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# reactivate_user  (includes #1406 sysadmin-reactivation block)
# ---------------------------------------------------------------------------


class TestReactivateUser_Issue1341:
    def test_returns_400_when_no_tenant_context(self, monkeypatch) -> None:
        user_routes_mod, _ = _load_routes(monkeypatch)
        monkeypatch.setattr(
            user_routes_mod.TenantContext,
            "get_tenant_context",
            staticmethod(lambda _db: None),
        )
        db = MagicMock()
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                user_routes_mod.reactivate_user(
                    user_id=TARGET_USER_ID,
                    current_user=_fake_user(ACTOR_ID, is_sysadmin=False),
                    db=db,
                )
            )
        assert exc.value.status_code == 400

    def test_returns_404_when_membership_missing(self, monkeypatch) -> None:
        user_routes_mod, _ = _load_routes(monkeypatch)
        db = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                user_routes_mod.reactivate_user(
                    user_id=TARGET_USER_ID,
                    current_user=_fake_user(ACTOR_ID, is_sysadmin=False),
                    db=db,
                )
            )
        assert exc.value.status_code == 404

    def test_blocks_non_sysadmin_reactivating_sysadmin_1406(
        self, monkeypatch,
    ) -> None:
        """#1406: a regular tenant Owner must NOT be able to reactivate
        a sysadmin's dormant membership. That would let a customer
        resurrect cross-tenant access for an engineer who once
        debugged their tenant."""
        user_routes_mod, audit_calls = _load_routes(monkeypatch)
        db = MagicMock()

        dormant_membership = _fake_membership(
            user_id=TARGET_USER_ID, is_active=False,
        )
        # target user IS a sysadmin
        dormant_sysadmin = _fake_user(TARGET_USER_ID, is_sysadmin=True)
        # caller is NOT a sysadmin
        caller = _fake_user(ACTOR_ID, is_sysadmin=False)

        result = MagicMock()
        result.scalar_one_or_none.return_value = dormant_membership
        db.execute.return_value = result
        db.get.return_value = dormant_sysadmin

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                user_routes_mod.reactivate_user(
                    user_id=TARGET_USER_ID,
                    current_user=caller,
                    db=db,
                )
            )
        assert exc.value.status_code == 403
        assert "sysadmin" in exc.value.detail.lower()

        # A "blocked" audit entry must still be emitted so security can
        # see the attempted reactivation.
        blocked = [
            c for c in audit_calls
            if c["event_type"] == "membership.reactivate_blocked"
        ]
        assert len(blocked) == 1, (
            "The #1406 block must produce an audit row with event_type "
            "'membership.reactivate_blocked' — silently rejecting would "
            "hide the attempt from ops dashboards"
        )
        assert blocked[0]["metadata"]["reason"] == "target_is_sysadmin"
        # Membership must remain dormant.
        assert dormant_membership.is_active is False

    def test_allows_sysadmin_reactivating_sysadmin_target(
        self, monkeypatch,
    ) -> None:
        """The #1406 block applies specifically when the CALLER is not
        a sysadmin. Another sysadmin may reactivate a sysadmin target
        — that's normal internal team management."""
        user_routes_mod, audit_calls = _load_routes(monkeypatch)
        db = MagicMock()

        dormant = _fake_membership(user_id=TARGET_USER_ID, is_active=False)
        target_sysadmin = _fake_user(TARGET_USER_ID, is_sysadmin=True)
        caller_sysadmin = _fake_user(ACTOR_ID, is_sysadmin=True)

        result = MagicMock()
        result.scalar_one_or_none.return_value = dormant
        db.execute.return_value = result
        db.get.return_value = target_sysadmin

        response = asyncio.run(
            user_routes_mod.reactivate_user(
                user_id=TARGET_USER_ID,
                current_user=caller_sysadmin,
                db=db,
            )
        )
        assert response == {"status": "reactivated"} or response.get("status") == "reactivated"
        assert dormant.is_active is True
        # The audit log should be the reactivate event, NOT the blocked event.
        reactivates = [
            c for c in audit_calls
            if c["event_type"] == "membership.reactivate"
        ]
        assert len(reactivates) == 1

    def test_happy_path_flips_is_active_true(self, monkeypatch) -> None:
        user_routes_mod, audit_calls = _load_routes(monkeypatch)
        db = MagicMock()

        dormant = _fake_membership(user_id=TARGET_USER_ID, is_active=False)
        target = _fake_user(TARGET_USER_ID, is_sysadmin=False)

        result = MagicMock()
        result.scalar_one_or_none.return_value = dormant
        db.execute.return_value = result
        db.get.return_value = target

        response = asyncio.run(
            user_routes_mod.reactivate_user(
                user_id=TARGET_USER_ID,
                current_user=_fake_user(ACTOR_ID, is_sysadmin=False),
                db=db,
            )
        )
        assert response == {"status": "reactivated"} or response.get("status") == "reactivated"
        assert dormant.is_active is True
        assert len(audit_calls) == 1
        assert audit_calls[0]["event_type"] == "membership.reactivate"
        assert audit_calls[0]["metadata"]["is_active"] is True
        db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# list_roles
# ---------------------------------------------------------------------------


class TestListRoles_Issue1341:
    def test_returns_400_when_no_tenant_context(self, monkeypatch) -> None:
        user_routes_mod, _ = _load_routes(monkeypatch)
        monkeypatch.setattr(
            user_routes_mod.TenantContext,
            "get_tenant_context",
            staticmethod(lambda _db: None),
        )
        from shared.pagination import PaginationParams

        db = MagicMock()
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                user_routes_mod.list_roles(
                    pagination=PaginationParams(skip=0, limit=10),
                    db=db,
                )
            )
        assert exc.value.status_code == 400
