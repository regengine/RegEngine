"""Tests for internal organization administration routes."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from starlette.testclient import TestClient

from services.admin.app.admin import organizations_router as org_router
from services.admin.app.auth.session_auth import AUTH_SESSION_COOKIE
from services.admin.app.sqlalchemy_models import OrganizationModel


def _client_with_db(db):
    app = FastAPI()
    app.include_router(org_router.router)
    app.dependency_overrides[org_router.get_session] = lambda: db
    return TestClient(app)


def _user(*, is_sysadmin: bool):
    return SimpleNamespace(
        id=uuid.UUID("33333333-3333-4333-8333-333333333333"),
        is_sysadmin=is_sysadmin,
        status="active",
        global_status="active",
    )


def _session(*, auth_method: str):
    return SimpleNamespace(
        id=uuid.UUID("44444444-4444-4444-8444-444444444444"),
        auth_method=auth_method,
    )


def test_update_organization_sso_policy_requires_session_cookie():
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    db = MagicMock()
    client = _client_with_db(db)

    response = client.put(
        f"/admin/organizations/{org_id}/sso-policy",
        json={
            "domain_name": "secure.example",
            "domain_verified": True,
            "enforced_auth_policy": "sso_only",
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}
    db.get.assert_not_called()
    db.commit.assert_not_called()


def test_update_organization_sso_policy_requires_sysadmin_session():
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    db = MagicMock()
    db.execute.return_value.one_or_none.return_value = (_user(is_sysadmin=False), _session(auth_method="webauthn"))
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")

    response = client.put(
        f"/admin/organizations/{org_id}/sso-policy",
        json={
            "domain_name": "secure.example",
            "domain_verified": True,
            "enforced_auth_policy": "sso_only",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Super admin access required."}
    db.get.assert_not_called()
    db.commit.assert_not_called()


def test_update_organization_sso_policy_rejects_email_otp_session_with_step_up_code():
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    db = MagicMock()
    db.execute.return_value.one_or_none.return_value = (_user(is_sysadmin=True), _session(auth_method="email_otp"))
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")

    response = client.put(
        f"/admin/organizations/{org_id}/sso-policy",
        json={
            "domain_name": "secure.example",
            "domain_verified": True,
            "enforced_auth_policy": "sso_only",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "requires_step_up"
    assert response.json()["detail"]["auth_method"] == "email_otp"
    db.get.assert_not_called()
    db.commit.assert_not_called()


def test_update_organization_sso_policy_allows_webauthn_session_and_updates_database():
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    organization = OrganizationModel(
        id=org_id,
        name="Enterprise Foods",
        domain_name=None,
        domain_verified=False,
        enforced_auth_policy="standard",
    )
    db = MagicMock()
    db.execute.return_value.one_or_none.return_value = (_user(is_sysadmin=True), _session(auth_method="webauthn"))
    db.get.return_value = organization
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")

    response = client.put(
        f"/admin/organizations/{org_id}/sso-policy",
        json={
            "domain_name": "  Secure.Example. ",
            "domain_verified": True,
            "enforced_auth_policy": "sso_only",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": str(org_id),
        "domain_name": "secure.example",
        "domain_verified": True,
        "enforced_auth_policy": "sso_only",
    }
    db.get.assert_called_once_with(OrganizationModel, org_id)
    assert organization.domain_name == "secure.example"
    assert organization.domain_verified is True
    assert organization.enforced_auth_policy == "sso_only"
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(organization)
