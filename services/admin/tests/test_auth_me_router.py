"""Tests for opaque-session GET /auth/me hydration."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from starlette.testclient import TestClient

from services.admin.app import auth_routes
from services.admin.app.auth import session_auth

USER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
MEMBERSHIP_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
ORG_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
TENANT_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_routes.router)
    return app


def _mock_db(*, membership, tenant_ids):
    """db.execute is called twice: org membership, then tenant memberships."""
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = membership
    tenant_result = MagicMock()
    tenant_result.scalars.return_value.all.return_value = tenant_ids
    db = MagicMock()
    db.execute.side_effect = [org_result, tenant_result]
    return db


def _wire(app, *, user, session, db):
    app.dependency_overrides[auth_routes.get_current_active_session_context] = lambda: (
        session_auth.ActiveSessionContext(user=user, session=session)
    )
    app.dependency_overrides[auth_routes.get_session] = lambda: db


def test_auth_me_returns_tenant_id_from_sole_membership():
    app = _app()
    user = SimpleNamespace(id=USER_ID, email="owner@example.com")
    session = SimpleNamespace(active_membership_id=MEMBERSHIP_ID, auth_method="webauthn")
    membership = SimpleNamespace(id=MEMBERSHIP_ID, user_id=USER_ID, organization_id=ORG_ID, role="owner")
    db = _mock_db(membership=membership, tenant_ids=[TENANT_ID])
    _wire(app, user=user, session=session, db=db)

    response = TestClient(app).get("/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(USER_ID),
        "email": "owner@example.com",
        "organization_id": str(ORG_ID),
        "tenant_id": str(TENANT_ID),
        "role": "owner",
        "auth_method": "webauthn",
    }
    # First query is still the organization-membership lookup.
    org_sql = str(db.execute.call_args_list[0].args[0])
    assert "organization_memberships.id" in org_sql
    # Second query resolves tenant from the memberships table.
    tenant_sql = str(db.execute.call_args_list[1].args[0])
    assert "memberships.tenant_id" in tenant_sql


def test_auth_me_tenant_id_null_when_membership_ambiguous():
    """Multiple active memberships => refuse to guess the acting tenant."""
    app = _app()
    user = SimpleNamespace(id=USER_ID, email="multi@example.com")
    session = SimpleNamespace(active_membership_id=MEMBERSHIP_ID, auth_method="webauthn")
    membership = SimpleNamespace(id=MEMBERSHIP_ID, user_id=USER_ID, organization_id=ORG_ID, role="owner")
    other_tenant = uuid.UUID("55555555-5555-4555-8555-555555555555")
    db = _mock_db(membership=membership, tenant_ids=[TENANT_ID, other_tenant])
    _wire(app, user=user, session=session, db=db)

    response = TestClient(app).get("/auth/me")

    assert response.status_code == 200
    assert response.json()["tenant_id"] is None


def test_auth_me_tenant_id_null_when_no_membership():
    app = _app()
    user = SimpleNamespace(id=USER_ID, email="orphan@example.com")
    session = SimpleNamespace(active_membership_id=None, auth_method="webauthn")
    db = _mock_db(membership=None, tenant_ids=[])
    _wire(app, user=user, session=session, db=db)

    response = TestClient(app).get("/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] is None
    assert body["organization_id"] is None


def test_auth_me_rejects_unauthenticated_requests():
    app = _app()
    db = MagicMock()
    app.dependency_overrides[session_auth.get_session] = lambda: db

    response = TestClient(app).get("/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}
