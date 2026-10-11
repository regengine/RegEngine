"""Wave 2 QA coverage for services/admin auth, roles, invites, exports, tenant scope.

Fills unit-level gaps with fast, deterministic tests (MagicMock only, no DB,
no network, no clock dependence). Each test pins behavior the service already
relies on for tenant isolation and access control:

* ``dependencies._parse_token_version`` coercion rules
* ``dependencies._optional_bearer_token`` header parsing
* ``dependencies._enforce_session_bound_token`` accept/reject verdicts
* ``dependencies.PermissionChecker`` allow/deny verdicts with the real
  ``has_permission`` matcher (exact, wildcard, missing role, insufficient)
* ``auth_routes`` session helpers (sole vs ambiguous tenant, permission
  shaping, active-membership loading)
* ``data_export_routes._serialize`` and invalid-id handling
* ``invite_routes`` email validation, base-URL handling, E2E outbox gating

Product files intentionally untouched (tests only).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
SESSION_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _request_with_auth_header(value: bytes | None) -> Request:
    headers = [(b"authorization", value)] if value is not None else []
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
        }
    )


# ---------------------------------------------------------------------------
# _parse_token_version
# ---------------------------------------------------------------------------


class TestParseTokenVersion:
    def test_none_returns_none(self):
        from services.admin.app.dependencies import _parse_token_version

        assert _parse_token_version(None) is None

    def test_booleans_return_none(self):
        from services.admin.app.dependencies import _parse_token_version

        assert _parse_token_version(True) is None
        assert _parse_token_version(False) is None

    def test_int_passes_through(self):
        from services.admin.app.dependencies import _parse_token_version

        assert _parse_token_version(3) == 3
        assert _parse_token_version(0) == 0

    def test_numeric_string_is_coerced(self):
        from services.admin.app.dependencies import _parse_token_version

        assert _parse_token_version("7") == 7

    def test_blank_and_garbage_strings_return_none(self):
        from services.admin.app.dependencies import _parse_token_version

        assert _parse_token_version("") is None
        assert _parse_token_version("   ") is None
        assert _parse_token_version("v3") is None
        assert _parse_token_version("3.5") is None

    def test_other_types_return_none(self):
        from services.admin.app.dependencies import _parse_token_version

        assert _parse_token_version(3.0) is None
        assert _parse_token_version(["3"]) is None


# ---------------------------------------------------------------------------
# _optional_bearer_token
# ---------------------------------------------------------------------------


class TestOptionalBearerToken:
    def test_missing_header_returns_none(self):
        from services.admin.app.dependencies import _optional_bearer_token

        assert _optional_bearer_token(_request_with_auth_header(None)) is None

    def test_non_bearer_scheme_returns_none(self):
        from services.admin.app.dependencies import _optional_bearer_token

        assert _optional_bearer_token(_request_with_auth_header(b"Basic dXNlcjpwYXNz")) is None

    def test_bearer_scheme_is_case_insensitive(self):
        from services.admin.app.dependencies import _optional_bearer_token

        assert _optional_bearer_token(_request_with_auth_header(b"bearer abc123")) == "abc123"

    def test_bearer_with_empty_token_returns_none(self):
        from services.admin.app.dependencies import _optional_bearer_token

        assert _optional_bearer_token(_request_with_auth_header(b"Bearer ")) is None


# ---------------------------------------------------------------------------
# _enforce_session_bound_token
# ---------------------------------------------------------------------------


def _make_session_data(**overrides):
    from services.admin.app.session_store import SessionData

    now = datetime.now(timezone.utc)
    fields = {
        "id": SESSION_ID,
        "user_id": USER_ID,
        "refresh_token_hash": "hash",
        "family_id": uuid.uuid4(),
        "created_at": now - timedelta(hours=1),
        "last_used_at": now - timedelta(minutes=5),
        "expires_at": now + timedelta(hours=1),
    }
    fields.update(overrides)
    return SessionData(**fields)


class _FakeSessionStore:
    def __init__(self, session=None, error: Exception | None = None):
        self._session = session
        self._error = error

    async def get_session(self, _session_id):
        if self._error is not None:
            raise self._error
        return self._session


def _check_session_bound_token(**kwargs):
    import asyncio

    from services.admin.app import dependencies as deps

    return asyncio.run(deps._enforce_session_bound_token(**kwargs))


class TestEnforceSessionBoundToken:
    def test_missing_session_row_is_rejected(self):
        from services.admin.app import dependencies as deps  # noqa: F401

        with pytest.raises(HTTPException) as exc:
            _check_session_bound_token(
                local_session_id=SESSION_ID,
                token_user_id=str(USER_ID),
                user=SimpleNamespace(id=USER_ID),
                session_store=_FakeSessionStore(session=None),
            )
        assert exc.value.status_code == 401

    def test_revoked_session_is_rejected(self):
        with pytest.raises(HTTPException) as exc:
            _check_session_bound_token(
                local_session_id=SESSION_ID,
                token_user_id=str(USER_ID),
                user=SimpleNamespace(id=USER_ID),
                session_store=_FakeSessionStore(session=_make_session_data(is_revoked=True)),
            )
        assert exc.value.status_code == 401

    def test_expired_session_is_rejected(self):
        past = datetime.now(timezone.utc) - timedelta(seconds=1)
        with pytest.raises(HTTPException) as exc:
            _check_session_bound_token(
                local_session_id=SESSION_ID,
                token_user_id=str(USER_ID),
                user=SimpleNamespace(id=USER_ID),
                session_store=_FakeSessionStore(session=_make_session_data(expires_at=past)),
            )
        assert exc.value.status_code == 401

    def test_session_owned_by_another_user_is_rejected(self):
        other = _make_session_data(user_id=uuid.uuid4())
        with pytest.raises(HTTPException) as exc:
            _check_session_bound_token(
                local_session_id=SESSION_ID,
                token_user_id=str(USER_ID),
                user=SimpleNamespace(id=USER_ID),
                session_store=_FakeSessionStore(session=other),
            )
        assert exc.value.status_code == 401

    def test_store_error_maps_to_503_not_401(self):
        with pytest.raises(HTTPException) as exc:
            _check_session_bound_token(
                local_session_id=SESSION_ID,
                token_user_id=str(USER_ID),
                user=SimpleNamespace(id=USER_ID),
                session_store=_FakeSessionStore(error=RuntimeError("redis down")),
            )
        assert exc.value.status_code == 503

    def test_valid_session_passes(self):
        assert (
            _check_session_bound_token(
                local_session_id=SESSION_ID,
                token_user_id=str(USER_ID),
                user=SimpleNamespace(id=USER_ID),
                session_store=_FakeSessionStore(session=_make_session_data()),
            )
            is None
        )


# ---------------------------------------------------------------------------
# PermissionChecker verdicts (real has_permission matcher)
# ---------------------------------------------------------------------------


def _checker_db_with_role(role_or_none):
    result = MagicMock()
    result.scalar_one_or_none.return_value = role_or_none
    db = MagicMock()
    db.execute.return_value = result
    return db


class TestPermissionCheckerVerdicts:
    def test_missing_role_is_403_role_not_found(self, monkeypatch):
        from services.admin.app import dependencies as deps

        monkeypatch.setattr(deps.TenantContext, "get_tenant_context", staticmethod(lambda _db: TENANT_ID))
        with pytest.raises(HTTPException) as exc:
            deps.PermissionChecker("users.read")(
                user=SimpleNamespace(id=USER_ID),
                db=_checker_db_with_role(None),
            )
        assert exc.value.status_code == 403
        assert exc.value.detail == "Role not found"

    def test_role_without_permission_is_403_insufficient(self, monkeypatch):
        from services.admin.app import dependencies as deps

        monkeypatch.setattr(deps.TenantContext, "get_tenant_context", staticmethod(lambda _db: TENANT_ID))
        role = SimpleNamespace(permissions=["users.read"])
        with pytest.raises(HTTPException) as exc:
            deps.PermissionChecker("users.manage_roles")(
                user=SimpleNamespace(id=USER_ID),
                db=_checker_db_with_role(role),
            )
        assert exc.value.status_code == 403
        assert exc.value.detail == "Insufficient permissions"

    def test_exact_permission_grant_passes(self, monkeypatch):
        from services.admin.app import dependencies as deps

        monkeypatch.setattr(deps.TenantContext, "get_tenant_context", staticmethod(lambda _db: TENANT_ID))
        role = SimpleNamespace(permissions=["users.read"])
        assert (
            deps.PermissionChecker("users.read")(
                user=SimpleNamespace(id=USER_ID),
                db=_checker_db_with_role(role),
            )
            is True
        )

    def test_wildcard_grant_passes(self, monkeypatch):
        from services.admin.app import dependencies as deps

        monkeypatch.setattr(deps.TenantContext, "get_tenant_context", staticmethod(lambda _db: TENANT_ID))
        role = SimpleNamespace(permissions=["users.*"])
        assert (
            deps.PermissionChecker("users.manage_roles")(
                user=SimpleNamespace(id=USER_ID),
                db=_checker_db_with_role(role),
            )
            is True
        )


# ---------------------------------------------------------------------------
# auth_routes session helpers
# ---------------------------------------------------------------------------


def _db_with_scalars_all(rows):
    scal = MagicMock()
    scal.all.return_value = rows
    result = MagicMock()
    result.scalars.return_value = scal
    db = MagicMock()
    db.execute.return_value = result
    return db


class TestResolveSessionTenantId:
    def test_sole_membership_resolves_tenant(self):
        from services.admin.app import auth_routes as routes

        db = _db_with_scalars_all([TENANT_ID])
        assert routes._resolve_session_tenant_id(user_id=USER_ID, db=db) == TENANT_ID

    def test_multiple_memberships_are_ambiguous(self):
        from services.admin.app import auth_routes as routes

        db = _db_with_scalars_all([TENANT_ID, uuid.uuid4()])
        assert routes._resolve_session_tenant_id(user_id=USER_ID, db=db) is None

    def test_no_membership_resolves_nothing(self):
        from services.admin.app import auth_routes as routes

        db = _db_with_scalars_all([])
        assert routes._resolve_session_tenant_id(user_id=USER_ID, db=db) is None


class TestResolveSessionPermissions:
    def test_none_tenant_returns_empty(self):
        from services.admin.app import auth_routes as routes

        assert routes._resolve_session_permissions(user_id=USER_ID, tenant_id=None, db=MagicMock()) == []

    def test_missing_role_returns_empty(self):
        from services.admin.app import auth_routes as routes

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db = MagicMock()
        db.execute.return_value = result
        assert routes._resolve_session_permissions(user_id=USER_ID, tenant_id=TENANT_ID, db=db) == []

    def test_non_list_permissions_return_empty(self):
        from services.admin.app import auth_routes as routes

        result = MagicMock()
        result.scalar_one_or_none.return_value = SimpleNamespace(permissions="users.read")
        db = MagicMock()
        db.execute.return_value = result
        assert routes._resolve_session_permissions(user_id=USER_ID, tenant_id=TENANT_ID, db=db) == []

    def test_non_string_entries_are_filtered(self):
        from services.admin.app import auth_routes as routes

        result = MagicMock()
        result.scalar_one_or_none.return_value = SimpleNamespace(
            permissions=["users.read", 42, None, "audit.read"]
        )
        db = MagicMock()
        db.execute.return_value = result
        assert routes._resolve_session_permissions(user_id=USER_ID, tenant_id=TENANT_ID, db=db) == [
            "users.read",
            "audit.read",
        ]


class TestLoadActiveOrganizationMembership:
    def _context(self, active_membership_id):
        return SimpleNamespace(
            user=SimpleNamespace(id=USER_ID),
            session=SimpleNamespace(active_membership_id=active_membership_id),
        )

    def test_no_active_membership_returns_none(self):
        from services.admin.app import auth_routes as routes

        assert routes._load_active_organization_membership(context=self._context(None), db=MagicMock()) is None

    def test_missing_row_is_401(self):
        from services.admin.app import auth_routes as routes

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db = MagicMock()
        db.execute.return_value = result
        with pytest.raises(HTTPException) as exc:
            routes._load_active_organization_membership(context=self._context(uuid.uuid4()), db=db)
        assert exc.value.status_code == 401

    def test_present_row_is_returned(self):
        from services.admin.app import auth_routes as routes

        membership = SimpleNamespace(id=uuid.uuid4())
        result = MagicMock()
        result.scalar_one_or_none.return_value = membership
        db = MagicMock()
        db.execute.return_value = result
        assert routes._load_active_organization_membership(context=self._context(membership.id), db=db) is membership


# ---------------------------------------------------------------------------
# data_export helpers
# ---------------------------------------------------------------------------


class TestExportSerialize:
    def test_none_stays_none(self):
        from services.admin.app.data_export_routes import _serialize

        assert _serialize(None) is None

    def test_datetime_becomes_iso_string(self):
        from services.admin.app.data_export_routes import _serialize

        moment = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        assert _serialize(moment) == moment.isoformat()

    def test_uuid_and_numbers_become_strings(self):
        from services.admin.app.data_export_routes import _serialize

        assert _serialize(USER_ID) == str(USER_ID)
        assert _serialize(5) == "5"

    def test_build_export_rejects_invalid_user_id_without_touching_db(self):
        from services.admin.app.data_export_routes import _build_user_export

        db = MagicMock()
        with pytest.raises(HTTPException) as exc:
            _build_user_export(db, "not-a-uuid")
        assert exc.value.status_code == 400
        db.get.assert_not_called()


# ---------------------------------------------------------------------------
# invite_routes helpers
# ---------------------------------------------------------------------------


class TestInviteCreateValidation:
    def test_invalid_email_is_rejected(self):
        from pydantic import ValidationError

        from services.admin.app.invite_routes import InviteCreate

        with pytest.raises(ValidationError):
            InviteCreate(email="not-an-email", role_id=uuid.uuid4())

    def test_valid_email_is_accepted(self):
        from services.admin.app.invite_routes import InviteCreate

        role_id = uuid.uuid4()
        invite = InviteCreate(email="buyer@example.com", role_id=role_id)
        assert invite.email == "buyer@example.com"
        assert invite.role_id == role_id


class TestInviteBaseUrl:
    def test_default_base_url(self, monkeypatch):
        from services.admin.app import invite_routes

        monkeypatch.delenv("INVITE_BASE_URL", raising=False)
        assert invite_routes._get_invite_base_url() == "https://regengine.co"

    def test_trailing_slash_is_stripped(self, monkeypatch):
        from services.admin.app import invite_routes

        monkeypatch.setenv("INVITE_BASE_URL", "https://app.example.com///")
        assert invite_routes._get_invite_base_url() == "https://app.example.com"

    def test_invite_link_keeps_token_in_fragment(self, monkeypatch):
        from services.admin.app import invite_routes

        monkeypatch.setenv("INVITE_BASE_URL", "https://app.example.com")
        relative, absolute = invite_routes._build_invite_link("tok123")
        assert relative == "/accept-invite#token=tok123"
        assert absolute == "https://app.example.com/accept-invite#token=tok123"
        assert "?" not in relative


class TestRecordE2EInviteEmail:
    def test_disabled_without_outbox_returns_false(self, monkeypatch):
        from services.admin.app import invite_routes

        monkeypatch.delenv("REGENGINE_E2E_EMAIL_OUTBOX", raising=False)
        monkeypatch.delenv("REGENGINE_E2E_MODE", raising=False)
        assert invite_routes._record_e2e_invite_email("buyer@example.com", "https://x/accept#token=t") is False
