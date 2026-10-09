"""Regression tests for the low-severity audit finding covering three files.

1. ``app/data_export_routes.py``: the GDPR export spanned every tenant the
   user belongs to yet rendered each row's raw ``tenant_id``, leaking other
   tenants' ids through the requesting tenant's context.
2. ``app/user_routes.py``: ``GET /admin/users`` returned every listed user's
   ``is_sysadmin`` flag to any caller with ``users.read``, disclosing which
   users hold cross-tenant platform access.
3. ``app/invite_routes.py``: ``POST /admin/invites`` compared emails with
   case-sensitive ``==``, so inviting a case variant of an existing member
   or pending invite created a duplicate.

Each test fails against the pre-fix code and passes with the fix.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))
sys.path.insert(0, str(service_dir.parent))

TENANT_ID = UUID("00000000-0000-0000-0000-0000000000b1")
OTHER_TENANT_ID = UUID("00000000-0000-0000-0000-0000000000b2")
ADMIN_ID = UUID("00000000-0000-0000-0000-0000000000b3")
ROLE_ID = UUID("00000000-0000-0000-0000-0000000000b4")
USER_ID = uuid.uuid4()

NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 1. Export must not contain any tenant id
# ---------------------------------------------------------------------------


def _make_export_db():
    """Mock session whose rows all carry tenant ids, like production data."""
    from app.sqlalchemy_models import (
        AuditLogModel,
        MembershipModel,
        MFARecoveryCodeModel,
        RoleModel,
        SessionModel,
        SupplierCTEEventModel,
        SupplierFacilityModel,
        SupplierFunnelEventModel,
        SupplierTraceabilityLotModel,
        UserModel,
    )

    user = MagicMock()
    user.id = USER_ID
    user.email = "user@example.com"
    user.status = "active"
    user.is_sysadmin = False
    user.mfa_secret = None
    user.mfa_secret_ciphertext = None
    user.created_at = NOW
    user.updated_at = NOW
    user.last_login_at = NOW

    role = MagicMock()
    role.id = uuid.uuid4()
    role.name = "member"

    membership = MagicMock()
    membership.tenant_id = OTHER_TENANT_ID
    membership.role_id = role.id
    membership.is_active = True
    membership.created_at = NOW

    facility = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=OTHER_TENANT_ID,
        name="Facility",
        street="1 Main St",
        city="Springfield",
        state="IL",
        postal_code="62701",
        fda_registration_number="123",
        roles=["shipper"],
        created_at=NOW,
        updated_at=NOW,
    )
    lot = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=OTHER_TENANT_ID,
        facility_id=uuid.uuid4(),
        tlc_code="LOT-1",
        product_description="peanuts",
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )
    funnel_event = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=OTHER_TENANT_ID,
        event_name="onboarded",
        step="done",
        status="ok",
        created_at=NOW,
    )
    audit_row = SimpleNamespace(
        id=1,
        tenant_id=OTHER_TENANT_ID,
        timestamp=NOW,
        event_type="user.login",
        action="login",
        event_category="auth",
        severity="info",
        resource_type="session",
        resource_id="r1",
        endpoint="/login",
    )

    def _get_side_effect(model, pk):
        if model is UserModel:
            return user
        if model is RoleModel:
            return role
        return None

    def _query_side_effect(model):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.count.return_value = 0
        if model is MembershipModel:
            q.all.return_value = [membership]
        elif model is SupplierFacilityModel:
            q.all.return_value = [facility]
        elif model is SupplierTraceabilityLotModel:
            q.all.return_value = [lot]
        elif model is SupplierFunnelEventModel:
            q.all.return_value = [funnel_event]
        elif model is AuditLogModel:
            q.all.return_value = [audit_row]
        else:
            q.all.return_value = []
        return q

    db = MagicMock()
    db.get.side_effect = _get_side_effect
    db.query.side_effect = _query_side_effect
    exec_result = MagicMock()
    exec_result.mappings.return_value.all.return_value = []
    db.execute.return_value = exec_result
    return db


class TestExportWithholdsTenantIds:
    def test_no_tenant_id_anywhere_in_export(self):
        """Membership, supplier and audit sections must not render tenant ids.

        The mock rows above all belong to OTHER_TENANT_ID; the old code
        serialized each row's tenant_id verbatim.
        """
        from app.data_export_routes import _build_user_export

        data = _build_user_export(_make_export_db(), str(USER_ID))
        serialized = json.dumps(data)

        assert "tenant_id" not in serialized
        assert str(OTHER_TENANT_ID) not in serialized

    def test_export_still_contains_personal_data(self):
        """Withholding ids must not drop the personal data itself."""
        from app.data_export_routes import _build_user_export

        data = _build_user_export(_make_export_db(), str(USER_ID))

        assert data["account"]["email"] == "user@example.com"
        assert data["memberships"][0]["role"] == "member"
        assert len(data["supplier_data"]["facilities"]) == 1
        assert len(data["audit_log"]["data"]) == 1


# ---------------------------------------------------------------------------
# 2. User list masks the sysadmin flag for non-sysadmin callers
# ---------------------------------------------------------------------------


def _make_list_users_db():
    listed_id = uuid.uuid4()
    role_id = uuid.uuid4()
    user = SimpleNamespace(
        id=listed_id,
        email="listed@example.com",
        status="active",
        is_sysadmin=True,
        created_at=NOW,
    )
    membership = SimpleNamespace(is_active=True)
    role = SimpleNamespace(id=role_id, name="Owner")

    result = MagicMock()
    result.scalar.return_value = 1
    result.all.return_value = [(user, membership, role)]
    db = MagicMock()
    db.execute.return_value = result
    return db


def _call_list_users(monkeypatch, caller_is_sysadmin):
    import app.user_routes as user_routes_mod
    from shared.pagination import PaginationParams

    monkeypatch.setattr(
        user_routes_mod.TenantContext,
        "get_tenant_context",
        staticmethod(lambda _db: TENANT_ID),
    )
    caller = SimpleNamespace(id=uuid.uuid4(), is_sysadmin=caller_is_sysadmin)
    return asyncio.run(
        user_routes_mod.list_users(
            pagination=PaginationParams(skip=0, limit=10),
            current_user=caller,
            db=_make_list_users_db(),
        )
    )


class TestListUsersMasksSysadminFlag:
    def test_non_sysadmin_caller_sees_false(self, monkeypatch):
        """A tenant admin must not learn who holds platform access."""
        response = _call_list_users(monkeypatch, caller_is_sysadmin=False)

        assert response.total == 1
        assert response.items[0].email == "listed@example.com"
        assert response.items[0].is_sysadmin is False

    def test_sysadmin_caller_still_sees_true(self, monkeypatch):
        """Masking must not blind platform operators."""
        response = _call_list_users(monkeypatch, caller_is_sysadmin=True)

        assert response.items[0].is_sysadmin is True


# ---------------------------------------------------------------------------
# 3. Invite duplicate checks are case-insensitive (live SQLite harness,
#    mirroring test_invite_audit_chain_guard_2857.py)
# ---------------------------------------------------------------------------


def _make_session():
    from app.sqlalchemy_models import (
        AuditLogModel,
        InviteModel,
        MembershipModel,
        RoleModel,
        TenantModel,
        UserModel,
    )
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

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
        InviteModel.__table__,
        AuditLogModel.__table__,
    ):
        table.create(bind=engine)

    maker = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
    session = maker()
    session.add(TenantModel(id=TENANT_ID, name="T", slug="t", status="active", settings={}))
    session.add(UserModel(id=ADMIN_ID, email="admin@example.com", status="active", is_sysadmin=True))
    session.add(RoleModel(id=ROLE_ID, tenant_id=TENANT_ID, name="member", permissions=[]))
    session.commit()
    return session


@pytest.fixture
def client(monkeypatch):
    session = _make_session()
    import app.invite_routes as invite_routes
    from app.database import get_session
    from app.dependencies import PermissionChecker, get_current_user
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setattr(invite_routes.TenantContext, "get_tenant_context", staticmethod(lambda db: TENANT_ID))
    monkeypatch.setattr(invite_routes, "can_invite_role", lambda *a, **k: True)
    monkeypatch.setattr(invite_routes, "_send_invite_email", lambda *a, **k: None)
    monkeypatch.setattr(invite_routes.AuditLogger, "log_event", staticmethod(lambda *a, **k: 1))
    monkeypatch.setattr(invite_routes.supplier_graph_sync, "record_invite_created", lambda *a, **k: None)
    monkeypatch.setattr(invite_routes.supplier_graph_sync, "record_invite_accepted", lambda *a, **k: None)

    app = FastAPI()
    app.include_router(invite_routes.router)
    from app.sqlalchemy_models import UserModel

    admin = session.get(UserModel, ADMIN_ID)
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_session] = lambda: session

    def _permit(self, user=Depends(get_current_user), db=Depends(get_session)):
        return True

    monkeypatch.setattr(PermissionChecker, "__call__", _permit)

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client, session


class TestInviteEmailCaseInsensitive:
    def test_member_case_variant_rejected(self, client):
        """Inviting MEMBER@... when Member@... is already in the tenant is a 409."""
        from app.sqlalchemy_models import MembershipModel, UserModel

        test_client, session = client
        member_id = uuid4()
        session.add(UserModel(id=member_id, email="Member@Example.com", status="active", is_sysadmin=False))
        session.add(
            MembershipModel(
                user_id=member_id,
                tenant_id=TENANT_ID,
                role_id=ROLE_ID,
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

        resp = test_client.post(
            "/admin/invites",
            json={"email": "member@example.com", "role_id": str(ROLE_ID)},
        )

        assert resp.status_code == 409, resp.text
        assert "already a member" in resp.json()["detail"].lower()

    def test_pending_invite_case_variant_rejected(self, client):
        """A pending invite for Invitee@... blocks invitee@... with a 409."""
        from app.sqlalchemy_models import InviteModel

        test_client, session = client
        session.add(
            InviteModel(
                id=uuid4(),
                tenant_id=TENANT_ID,
                email="Invitee@Example.com",
                role_id=ROLE_ID,
                token_hash="1" * 64,
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                created_by=ADMIN_ID,
            )
        )
        session.commit()

        resp = test_client.post(
            "/admin/invites",
            json={"email": "invitee@example.com", "role_id": str(ROLE_ID)},
        )

        assert resp.status_code == 409, resp.text
        assert "already exists" in resp.json()["detail"].lower()

    def test_stored_email_is_normalized(self, client):
        """The stored invite email is lowercased so lookups stay consistent."""
        from app.sqlalchemy_models import InviteModel
        from sqlalchemy import select

        test_client, session = client
        resp = test_client.post(
            "/admin/invites",
            json={"email": "NewPerson@Example.com", "role_id": str(ROLE_ID)},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["email"] == "newperson@example.com"
        session.expire_all()
        row = session.execute(
            select(InviteModel).where(InviteModel.email == "newperson@example.com")
        ).scalar_one_or_none()
        assert row is not None
