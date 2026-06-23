"""Tests for opaque-session GET /auth/me hydration."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from starlette.testclient import TestClient

from services.admin.app import auth_routes
from services.admin.app.auth import session_auth


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_routes.router)
    return app


def test_auth_me_returns_session_profile_shape():
    app = _app()
    user_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    membership_id = uuid.UUID("22222222-2222-4222-8222-222222222222")
    organization_id = uuid.UUID("33333333-3333-4333-8333-333333333333")
    user = SimpleNamespace(id=user_id, email="owner@example.com")
    session = SimpleNamespace(active_membership_id=membership_id, auth_method="webauthn")
    membership = SimpleNamespace(
        id=membership_id,
        user_id=user_id,
        organization_id=organization_id,
        role="owner",
    )
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = membership

    app.dependency_overrides[auth_routes.get_current_active_session_context] = lambda: (
        session_auth.ActiveSessionContext(user=user, session=session)
    )
    app.dependency_overrides[auth_routes.get_session] = lambda: db

    response = TestClient(app).get("/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(user_id),
        "email": "owner@example.com",
        "organization_id": str(organization_id),
        "role": "owner",
        "auth_method": "webauthn",
    }
    sql = str(db.execute.call_args.args[0])
    assert "organization_memberships.id" in sql
    assert "organization_memberships.user_id" in sql


def test_auth_me_rejects_unauthenticated_requests():
    app = _app()
    db = MagicMock()
    app.dependency_overrides[session_auth.get_session] = lambda: db

    response = TestClient(app).get("/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}
