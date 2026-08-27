"""Regression tests for #2906 — the last-Owner guard must count only
Owners who can actually authenticate.

``services/admin/app/user_routes.py`` refuses to demote or deactivate a
tenant's final Owner (#1083).  Before this fix the guard counted *every*
Owner membership row, with no predicate on whether that Owner could still
log in.  Deactivation is a soft delete (``membership.is_active = False``,
``user_routes.py``), so a previously-offboarded Owner's row survives and
satisfied the very guard meant to prevent the tenant losing its last
Owner.

What "can actually authenticate" means here is fixed by the auth code,
not by guesswork:

* ``dependencies.py`` — ``get_current_user`` raises ``credentials_exception``
  (logging ``deactivated_user_access_attempt``) when
  ``not membership.is_active``, so an inactive membership confers zero
  capability on *every* authenticated admin route.
* ``auth/session_auth.py``, ``auth/webauthn_router.py``,
  ``auth/challenges_router.py`` and ``auth/email_code_router.py`` — every
  credential-establishing path additionally requires
  ``UserModel.global_status == "active"`` *and* ``UserModel.status ==
  "active"``, so a globally disabled user can never obtain a new session.
  ``services/scheduler/service.py`` flips ``users.status`` to
  ``'disabled'`` automatically after 90 days without a login (NIST
  AC-2(3)), and ``invite_routes.py`` deliberately refuses to reinstate a
  non-active user — so that state is reached by a background job and is
  not repairable from the admin surface.

Leaving a tenant with only such an Owner is a self-sealing lockout:
``reactivate_user`` is itself gated by
``PermissionChecker("users.manage_roles")``, so recovery needs direct DB
access.  The guard therefore fails closed — an Owner that cannot
authenticate does not count as the surviving Owner.

These tests drive the real routes against a real (SQLite) session so the
assertion is on emitted SQL semantics, not on mock bookkeeping.
"""

from __future__ import annotations

# Admin-test sys.path bootstrap (#1435).
import sys
from pathlib import Path as _Path

_SERVICE_DIR = _Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SERVICE_DIR.parent
for _p in (_SERVICE_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from services.admin.app.sqlalchemy_models import (
    AuditLogModel,
    MembershipModel,
    RoleModel,
    TenantModel,
    UserModel,
)

TENANT_ID = uuid.UUID("2906aaaa-0000-0000-0000-000000000001")
OWNER_ROLE_ID = uuid.UUID("2906aaaa-0000-0000-0000-0000000000a1")
MEMBER_ROLE_ID = uuid.UUID("2906aaaa-0000-0000-0000-0000000000a2")
ALICE_ID = uuid.UUID("2906aaaa-0000-0000-0000-0000000000b1")  # the healthy Owner
BOB_ID = uuid.UUID("2906aaaa-0000-0000-0000-0000000000b2")  # the stale Owner
ACTOR_ID = uuid.UUID("2906aaaa-0000-0000-0000-0000000000c1")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user_routes_mod(monkeypatch):
    """Import user_routes with TenantContext / AuditLogger stubbed out."""
    from services.admin.app import audit as audit_mod, models as models_mod, user_routes as mod

    for target in (models_mod.TenantContext, mod.TenantContext):
        monkeypatch.setattr(target, "get_tenant_context", staticmethod(lambda _db: TENANT_ID))

    def _fake_log_event(db, **kwargs):  # audit chain is covered by its own suite
        return 1

    monkeypatch.setattr(audit_mod.AuditLogger, "log_event", _fake_log_event)
    monkeypatch.setattr(mod.AuditLogger, "log_event", _fake_log_event)
    return mod


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    for table in (
        TenantModel.__table__,
        UserModel.__table__,
        RoleModel.__table__,
        MembershipModel.__table__,
        AuditLogModel.__table__,
    ):
        table.create(bind=engine)

    session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    session = session_local()
    session.add(TenantModel(id=TENANT_ID, name="Acme Foods", slug="acme-foods-2906", status="active", settings={}))
    session.add(RoleModel(id=OWNER_ROLE_ID, tenant_id=None, name="Owner", permissions=["users.manage_roles"]))
    session.add(RoleModel(id=MEMBER_ROLE_ID, tenant_id=None, name="Member", permissions=[]))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _seed_owner(
    db: Session,
    user_id: uuid.UUID,
    *,
    membership_active: bool = True,
    user_status: str = "active",
    global_status: str = "active",
    role_id: uuid.UUID = OWNER_ROLE_ID,
) -> None:
    db.add(
        UserModel(
            id=user_id,
            email=f"{user_id}@acme.test",
            status=user_status,
            global_status=global_status,
            is_sysadmin=False,
        )
    )
    db.add(
        MembershipModel(
            user_id=user_id,
            tenant_id=TENANT_ID,
            role_id=role_id,
            is_active=membership_active,
        )
    )
    db.commit()


def _actor():
    return SimpleNamespace(id=ACTOR_ID, email="actor@acme.test", is_sysadmin=False)


def _membership(db: Session, user_id: uuid.UUID) -> MembershipModel:
    return db.execute(
        select(MembershipModel).where(
            MembershipModel.user_id == user_id,
            MembershipModel.tenant_id == TENANT_ID,
        )
    ).scalar_one()


def _deactivate(mod, db, user_id):
    return asyncio.run(mod.deactivate_user(user_id=user_id, current_user=_actor(), db=db))


def _demote(mod, db, user_id):
    return asyncio.run(
        mod.update_user_role(
            user_id=user_id,
            update=mod.RoleUpdate(role_id=MEMBER_ROLE_ID),
            current_user=_actor(),
            db=db,
        )
    )


# ---------------------------------------------------------------------------
# The filed defect: a soft-deleted Owner membership must not count.
# ---------------------------------------------------------------------------


class TestInactiveMembershipDoesNotCount_Issue2906:
    def test_deactivate_last_active_owner_is_rejected(self, user_routes_mod, db) -> None:
        """Bob was offboarded (soft delete). Deactivating Alice would
        leave the tenant with zero Owners who can authenticate."""
        _seed_owner(db, ALICE_ID)
        _seed_owner(db, BOB_ID, membership_active=False)

        with pytest.raises(HTTPException) as exc:
            _deactivate(user_routes_mod, db, ALICE_ID)

        assert exc.value.status_code == 400
        assert "last Owner" in exc.value.detail
        assert _membership(db, ALICE_ID).is_active is True, "Alice's membership must survive the rejected request"

    def test_demote_last_active_owner_is_rejected(self, user_routes_mod, db) -> None:
        _seed_owner(db, ALICE_ID)
        _seed_owner(db, BOB_ID, membership_active=False)

        with pytest.raises(HTTPException) as exc:
            _demote(user_routes_mod, db, ALICE_ID)

        assert exc.value.status_code == 400
        assert "last Owner" in exc.value.detail
        assert _membership(db, ALICE_ID).role_id == OWNER_ROLE_ID, "Alice must still be an Owner"


# ---------------------------------------------------------------------------
# Same lockout, reached through the global user status the login paths
# enforce (and the scheduler's 90-day sweep sets).
# ---------------------------------------------------------------------------


class TestGloballyDisabledOwnerDoesNotCount_Issue2906:
    def test_deactivate_rejected_when_only_other_owner_is_disabled(self, user_routes_mod, db) -> None:
        _seed_owner(db, ALICE_ID)
        _seed_owner(db, BOB_ID, user_status="disabled")

        with pytest.raises(HTTPException) as exc:
            _deactivate(user_routes_mod, db, ALICE_ID)

        assert exc.value.status_code == 400
        assert "last Owner" in exc.value.detail

    def test_demote_rejected_when_only_other_owner_is_disabled(self, user_routes_mod, db) -> None:
        _seed_owner(db, ALICE_ID)
        _seed_owner(db, BOB_ID, user_status="disabled")

        with pytest.raises(HTTPException) as exc:
            _demote(user_routes_mod, db, ALICE_ID)

        assert exc.value.status_code == 400
        assert "last Owner" in exc.value.detail

    def test_deactivate_rejected_when_only_other_owner_is_globally_erased(self, user_routes_mod, db) -> None:
        _seed_owner(db, ALICE_ID)
        _seed_owner(db, BOB_ID, global_status="erased")

        with pytest.raises(HTTPException) as exc:
            _deactivate(user_routes_mod, db, ALICE_ID)

        assert exc.value.status_code == 400
        assert "last Owner" in exc.value.detail


# ---------------------------------------------------------------------------
# The opposite failure mode: the guard must NOT become so strict that a
# tenant can never clean up a stale Owner, or lose a departing one while a
# healthy Owner remains.
# ---------------------------------------------------------------------------


class TestGuardStaysPermissiveWhereItShould_Issue2906:
    def test_deactivate_allowed_when_another_authenticating_owner_exists(self, user_routes_mod, db) -> None:
        _seed_owner(db, ALICE_ID)
        _seed_owner(db, BOB_ID)

        assert _deactivate(user_routes_mod, db, ALICE_ID) == {"status": "deactivated"}
        assert _membership(db, ALICE_ID).is_active is False

    def test_demote_allowed_when_another_authenticating_owner_exists(self, user_routes_mod, db) -> None:
        _seed_owner(db, ALICE_ID)
        _seed_owner(db, BOB_ID)

        assert _demote(user_routes_mod, db, ALICE_ID) == {"status": "updated"}
        assert _membership(db, ALICE_ID).role_id == MEMBER_ROLE_ID

    def test_stale_owner_can_still_be_removed(self, user_routes_mod, db) -> None:
        """The guard must never wedge a tenant: a stale Owner (globally
        disabled, membership still active) is removable as long as one
        Owner who can authenticate remains."""
        _seed_owner(db, ALICE_ID)
        _seed_owner(db, BOB_ID, user_status="disabled")

        assert _deactivate(user_routes_mod, db, BOB_ID) == {"status": "deactivated"}
        assert _membership(db, BOB_ID).is_active is False

    def test_non_owner_deactivation_is_unaffected(self, user_routes_mod, db) -> None:
        """A Member is not subject to the Owner invariant at all."""
        _seed_owner(db, ALICE_ID)
        _seed_owner(db, BOB_ID, role_id=MEMBER_ROLE_ID)

        assert _deactivate(user_routes_mod, db, BOB_ID) == {"status": "deactivated"}


# ---------------------------------------------------------------------------
# Both routes must share one guard, and that guard's SQL must carry the
# predicate (acceptance criterion 3 of #2906).
# ---------------------------------------------------------------------------


class TestGuardIsSharedAndFilters_Issue2906:
    @staticmethod
    def _captured_owner_query_sql(mod, route) -> str:
        """Run the route against a mock session and return the compiled
        SQL of the second SELECT — the Owner-count query."""
        statements: list = []
        owner_role = SimpleNamespace(id=OWNER_ROLE_ID, name="Owner", tenant_id=None)
        member_role = SimpleNamespace(id=MEMBER_ROLE_ID, name="Member", tenant_id=None)
        membership = SimpleNamespace(user_id=ALICE_ID, tenant_id=TENANT_ID, role_id=OWNER_ROLE_ID, is_active=True)

        db = MagicMock()
        db.get.side_effect = lambda _model, ident: {
            OWNER_ROLE_ID: owner_role,
            MEMBER_ROLE_ID: member_role,
        }.get(ident)

        def _execute(stmt, *args, **kwargs):
            statements.append(stmt)
            result = MagicMock()
            result.scalar_one_or_none.return_value = membership
            result.all.return_value = [object()]  # a surviving Owner → route proceeds
            return result

        db.execute.side_effect = _execute
        route(mod, db, ALICE_ID)
        assert len(statements) >= 2, "expected the membership lookup plus the Owner-count query"
        return str(statements[1].compile(compile_kwargs={"literal_binds": False}))

    @pytest.mark.parametrize("route", [_deactivate, _demote], ids=["deactivate_user", "update_user_role"])
    def test_owner_count_query_filters_on_authenticatability(self, user_routes_mod, route) -> None:
        sql = self._captured_owner_query_sql(user_routes_mod, route).lower()
        # Assert on the WHERE clause only — every one of these columns also
        # appears in the SELECT list, so a whole-statement match would pass
        # against the unfixed query.
        where = sql.split(" \nwhere ", 1)[-1] if " \nwhere " in sql else sql.split("where ", 1)[-1]
        assert "where" in sql, "the Owner-count query must be filtered"
        assert "memberships.is_active" in where, "guard must exclude soft-deleted Owner memberships (#2906)"
        assert "users.status" in where, "guard must exclude globally disabled Owners (#2906)"
        assert "users.global_status" in where

    def test_both_routes_use_the_same_guard_helper(self, user_routes_mod) -> None:
        """One implementation, so the two copies cannot drift again."""
        import inspect

        helper = user_routes_mod._other_authenticating_owners
        for route_name in ("update_user_role", "deactivate_user"):
            source = inspect.getsource(getattr(user_routes_mod, route_name))
            assert helper.__name__ in source, f"{route_name} must delegate to the shared last-Owner guard"
