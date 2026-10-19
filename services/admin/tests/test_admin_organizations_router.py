"""Tests for internal organization administration routes."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.testclient import TestClient

from services.admin.app.admin import organizations_router as org_router
from services.admin.app.admin.organizations_router import OrganizationSsoPolicyUpdate
from services.admin.app.auth.session_auth import AUTH_SESSION_COOKIE
from services.admin.app.sqlalchemy_models import OrganizationModel, TenantModel


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


def _db_with_authenticated_session(*, user, session):
    """Model the scoped session lookup separately from its GUC statements."""
    db = MagicMock()
    auth_result = MagicMock()
    auth_result.one_or_none.return_value = (user, session)

    def _execute(statement, *_args, **_kwargs):
        if "set_config(" in str(statement):
            return MagicMock()
        return auth_result

    db.execute.side_effect = _execute
    return db


def _guc_statements(db) -> list[str]:
    return [
        str(execute_call.args[0])
        for execute_call in db.execute.call_args_list
        if "set_config(" in str(execute_call.args[0])
    ]


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
    db = _db_with_authenticated_session(
        user=_user(is_sysadmin=False),
        session=_session(auth_method="webauthn"),
    )
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
    assert response.json() == {"detail": "System administrator access required."}
    db.get.assert_not_called()
    db.commit.assert_not_called()
    gucs = _guc_statements(db)
    assert "regengine.is_sysadmin', 'true'" in gucs[0]
    assert "regengine.is_sysadmin', 'false'" in gucs[1]
    assert "regengine.user_id" in gucs[2]


def test_update_organization_sso_policy_rejects_email_otp_session_with_step_up_code():
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    db = _db_with_authenticated_session(
        user=_user(is_sysadmin=True),
        session=_session(auth_method="email_otp"),
    )
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
    gucs = _guc_statements(db)
    assert "regengine.is_sysadmin', 'true'" in gucs[0]
    assert "regengine.is_sysadmin', 'false'" in gucs[1]
    assert "regengine.user_id" in gucs[2]


def test_update_organization_sso_policy_allows_webauthn_session_and_updates_database():
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    organization = OrganizationModel(
        id=org_id,
        name="Enterprise Foods",
        domain_name=None,
        domain_verified=False,
        enforced_auth_policy="standard",
    )
    db = _db_with_authenticated_session(
        user=_user(is_sysadmin=True),
        session=_session(auth_method="webauthn"),
    )
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
    db.refresh.assert_not_called()
    gucs = _guc_statements(db)
    assert "regengine.is_sysadmin', 'true'" in gucs[0]
    assert "regengine.is_sysadmin', 'false'" in gucs[1]
    assert "regengine.user_id" in gucs[2]
    assert "regengine.is_sysadmin', 'true'" in gucs[3]


def _sysadmin_webauthn_db(organization=None):
    db = _db_with_authenticated_session(
        user=_user(is_sysadmin=True),
        session=_session(auth_method="webauthn"),
    )
    db.get.return_value = organization
    return db


def _put_sso_policy(client, org_id, payload):
    return client.put(f"/admin/organizations/{org_id}/sso-policy", json=payload)


def _organization(org_id):
    return OrganizationModel(
        id=org_id,
        name="Enterprise Foods",
        domain_name=None,
        domain_verified=False,
        enforced_auth_policy="standard",
    )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("secure.example", "secure.example"),
        ("  Secure.Example. ", "secure.example"),
        ("SUB.DOMAIN.CO.UK", "sub.domain.co.uk"),
        ("a.b", "a.b"),
        ("xn--mnchen-3ya.de", "xn--mnchen-3ya.de"),
    ],
)
def test_domain_validator_accepts_and_normalizes(raw, expected):
    payload = OrganizationSsoPolicyUpdate(
        domain_name=raw,
        domain_verified=True,
        enforced_auth_policy="sso_only",
    )
    assert payload.domain_name == expected


@pytest.mark.parametrize(
    "raw",
    [
        "notadomain",
        "user@example.com",
        "example.com:8443",
        "https://example.com",
        "exa mple.com",
        "   ",
        "-leading.com",
        "trailing-.com",
        "empty..label.com",
        ".leading-dot.com",
        ("x" * 64) + ".com",
        ("a." * 126) + "com",
    ],
)
def test_domain_validator_rejects_non_domains(raw):
    with pytest.raises(ValueError, match="bare DNS domain"):
        OrganizationSsoPolicyUpdate(
            domain_name=raw,
            domain_verified=False,
            enforced_auth_policy="standard",
        )


@pytest.mark.parametrize(
    "raw",
    ["empty..label.com", "-leading.com", ("x" * 64) + ".com"],
)
def test_route_rejects_malformed_domain_before_touching_database(raw):
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    db = _sysadmin_webauthn_db(_organization(org_id))
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")

    response = _put_sso_policy(
        client,
        org_id,
        {
            "domain_name": raw,
            "domain_verified": True,
            "enforced_auth_policy": "sso_only",
        },
    )

    assert response.status_code == 422
    db.get.assert_not_called()
    db.commit.assert_not_called()


def test_update_returns_404_for_unknown_organization():
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    db = _sysadmin_webauthn_db(None)
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")

    response = _put_sso_policy(
        client,
        org_id,
        {
            "domain_name": "secure.example",
            "domain_verified": True,
            "enforced_auth_policy": "sso_only",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Organization not found."}
    db.commit.assert_not_called()


def test_update_returns_409_when_domain_already_claimed():
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    db = _sysadmin_webauthn_db(_organization(org_id))
    db.commit.side_effect = IntegrityError(
        "UPDATE organizations SET domain_name='secure.example'",
        {},
        Exception("duplicate key value violates unique constraint"),
    )
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")

    response = _put_sso_policy(
        client,
        org_id,
        {
            "domain_name": "secure.example",
            "domain_verified": True,
            "enforced_auth_policy": "sso_only",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Organization domain is already claimed."}
    db.rollback.assert_called_once()


def test_update_returns_503_when_commit_fails():
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    db = _sysadmin_webauthn_db(_organization(org_id))
    db.commit.side_effect = OperationalError("COMMIT", {}, Exception("connection down"))
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")

    response = _put_sso_policy(
        client,
        org_id,
        {
            "domain_name": "secure.example",
            "domain_verified": True,
            "enforced_auth_policy": "sso_only",
        },
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Organization policy update temporarily unavailable."}
    db.rollback.assert_called_once()


def test_unexpected_commit_error_is_not_reported_as_temporarily_unavailable():
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    db = _sysadmin_webauthn_db(_organization(org_id))
    db.commit.side_effect = RuntimeError("boom")
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")

    with pytest.raises(RuntimeError, match="boom"):
        _put_sso_policy(
            client,
            org_id,
            {
                "domain_name": "secure.example",
                "domain_verified": True,
                "enforced_auth_policy": "sso_only",
            },
        )
    db.commit.assert_called_once()


def test_response_reflects_committed_state():
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    organization = _organization(org_id)
    db = _sysadmin_webauthn_db(organization)

    def _commit_with_database_side_effect():
        organization.domain_verified = False

    db.commit.side_effect = _commit_with_database_side_effect
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")

    response = _put_sso_policy(
        client,
        org_id,
        {
            "domain_name": "secure.example",
            "domain_verified": True,
            "enforced_auth_policy": "sso_only",
        },
    )

    assert response.status_code == 200
    assert response.json()["domain_verified"] is False
    db.commit.assert_called_once()


def test_retired_admin_key_header_rejected_despite_valid_session():
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    db = _sysadmin_webauthn_db(_organization(org_id))
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")

    response = client.put(
        f"/admin/organizations/{org_id}/sso-policy",
        json={
            "domain_name": "secure.example",
            "domain_verified": True,
            "enforced_auth_policy": "sso_only",
        },
        headers={"x-admin-key": "retired-key"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "X-Admin-Key is not an accepted authentication method."}
    db.get.assert_not_called()
    db.commit.assert_not_called()


def test_sso_only_with_unverified_domain_is_accepted():
    """Lock in the cross-module contract with challenges_router.

    Passwordless enforcement only kicks in for sso_only organizations once
    the domain is verified, so storing sso_only alongside
    domain_verified=False must succeed rather than lock the org out.
    """
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    organization = _organization(org_id)
    db = _sysadmin_webauthn_db(organization)
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")

    response = _put_sso_policy(
        client,
        org_id,
        {
            "domain_name": "secure.example",
            "domain_verified": False,
            "enforced_auth_policy": "sso_only",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": str(org_id),
        "domain_name": "secure.example",
        "domain_verified": False,
        "enforced_auth_policy": "sso_only",
    }
    db.commit.assert_called_once()


def test_successful_update_emits_succeeded_audit_event(monkeypatch):
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    db = _sysadmin_webauthn_db(_organization(org_id))
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")
    events = []
    monkeypatch.setattr(
        org_router,
        "audit_privileged_action",
        lambda request, **kwargs: events.append(kwargs),
    )

    response = _put_sso_policy(
        client,
        org_id,
        {
            "domain_name": "secure.example",
            "domain_verified": True,
            "enforced_auth_policy": "sso_only",
        },
    )

    assert response.status_code == 200
    assert [event["outcome"] for event in events] == ["attempted", "succeeded"]
    succeeded = events[-1]
    assert succeeded["action"] == "organization.sso_policy.update"
    assert succeeded["target"] == str(org_id)
    assert succeeded["actor"].actor_id == "33333333-3333-4333-8333-333333333333"
    assert "session-token" not in str(events)


def test_unknown_organization_emits_failed_audit_event(monkeypatch):
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    db = _sysadmin_webauthn_db(None)
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")
    events = []
    monkeypatch.setattr(
        org_router,
        "audit_privileged_action",
        lambda request, **kwargs: events.append(kwargs),
    )

    response = _put_sso_policy(
        client,
        org_id,
        {
            "domain_name": "secure.example",
            "domain_verified": True,
            "enforced_auth_policy": "sso_only",
        },
    )

    assert response.status_code == 404
    assert [event["outcome"] for event in events] == ["attempted", "failed"]
    assert events[-1]["reason"] == "organization_not_found"
    assert events[-1]["target"] == str(org_id)


def _patch_org(client, org_id, payload):
    return client.patch(f"/admin/organizations/{org_id}", json=payload)


def test_patch_organization_requires_session_cookie():
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    db = MagicMock()
    response = _patch_org(_client_with_db(db), org_id, {"name": "New Name"})

    assert response.status_code == 401
    db.get.assert_not_called()
    db.commit.assert_not_called()


def test_patch_organization_updates_trimmed_name():
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    organization = _organization(org_id)
    db = _sysadmin_webauthn_db(organization)
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")

    response = _patch_org(client, org_id, {"name": "  Renamed Foods  "})

    assert response.status_code == 200
    assert response.json() == {"id": str(org_id), "name": "Renamed Foods"}
    assert organization.name == "Renamed Foods"
    db.commit.assert_called_once()


@pytest.mark.parametrize("name", ["", "   ", "x" * 256])
def test_patch_organization_rejects_invalid_name(name):
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    db = _sysadmin_webauthn_db(_organization(org_id))
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")

    response = _patch_org(client, org_id, {"name": name})

    assert response.status_code == 422
    db.get.assert_not_called()
    db.commit.assert_not_called()


def test_patch_organization_returns_404_for_unknown_organization():
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    db = _sysadmin_webauthn_db(None)
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")

    response = _patch_org(client, org_id, {"name": "New Name"})

    assert response.status_code == 404
    db.commit.assert_not_called()


def test_patch_organization_returns_503_when_commit_fails():
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    db = _sysadmin_webauthn_db(_organization(org_id))
    db.commit.side_effect = OperationalError("COMMIT", {}, Exception("connection down"))
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")

    response = _patch_org(client, org_id, {"name": "New Name"})

    assert response.status_code == 503
    db.rollback.assert_called_once()


def test_patch_organization_also_renames_matching_tenant_row():
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    organization = _organization(org_id)
    tenant = TenantModel(id=org_id, name="Enterprise Foods", slug="enterprise-foods")
    db = _sysadmin_webauthn_db(organization)
    db.get.side_effect = lambda model, _id: {OrganizationModel: organization, TenantModel: tenant}[model]
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")

    response = _patch_org(client, org_id, {"name": "Renamed Foods"})

    assert response.status_code == 200
    assert organization.name == "Renamed Foods"
    assert tenant.name == "Renamed Foods"
    db.commit.assert_called_once()


def test_patch_organization_succeeds_when_no_tenant_row_shares_the_id():
    org_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    organization = _organization(org_id)
    db = _sysadmin_webauthn_db(organization)
    db.get.side_effect = lambda model, _id: organization if model is OrganizationModel else None
    client = _client_with_db(db)
    client.cookies.set(AUTH_SESSION_COOKIE, "session-token")

    response = _patch_org(client, org_id, {"name": "Renamed Foods"})

    assert response.status_code == 200
    assert organization.name == "Renamed Foods"
    db.commit.assert_called_once()
