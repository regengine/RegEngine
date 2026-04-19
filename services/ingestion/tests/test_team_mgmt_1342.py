"""Coverage for app/team_mgmt.py — team members, roles, invitations router.

Targets Pydantic models, DB helpers (happy path + exception path + None),
ROLE_PERMISSIONS catalog, and all four endpoints via FastAPI TestClient
with auth dependency override.

Issue: #1342
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import team_mgmt as tm
from app.team_mgmt import (
    InviteRequest,
    ROLE_PERMISSIONS,
    TeamMember,
    TeamResponse,
    _db_add_team_member,
    _db_get_team,
    _team_store,
    router,
)
from app.webhook_compat import _verify_api_key


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_store():
    _team_store.clear()
    yield
    _team_store.clear()


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def _mock_db_session(rows=None, raise_on_execute=False):
    """Return a MagicMock session that behaves like a SQLAlchemy Session."""
    session = MagicMock()
    if raise_on_execute:
        session.execute.side_effect = RuntimeError("boom")
    else:
        result = MagicMock()
        result.fetchall.return_value = rows or []
        session.execute.return_value = result
    return session


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TestPydanticModels:
    def test_team_member_defaults(self):
        m = TeamMember(id="m1", name="Alice Smith", email="a@x.com", role="admin", status="active")
        assert m.last_active is None
        assert m.invited_at is None
        assert m.avatar_initials == ""
        assert m.is_sample is False

    def test_team_member_with_all_fields(self):
        m = TeamMember(
            id="m1", name="Alice Smith", email="a@x.com", role="admin",
            status="active", last_active="2026-04-18T00:00:00Z",
            invited_at="2026-04-18T00:00:00Z", avatar_initials="AS",
            is_sample=True,
        )
        assert m.avatar_initials == "AS"
        assert m.is_sample is True

    def test_invite_request_defaults(self):
        req = InviteRequest(email="a@x.com", name="Alice")
        assert req.role == "viewer"

    def test_invite_request_explicit_role(self):
        req = InviteRequest(email="a@x.com", name="Alice", role="admin")
        assert req.role == "admin"

    def test_team_response_schema(self):
        resp = TeamResponse(
            tenant_id="t1", total_members=2, active_members=1,
            pending_invites=1, roles_breakdown={"admin": 1, "viewer": 1},
            members=[],
        )
        assert resp.total_members == 2


# ---------------------------------------------------------------------------
# ROLE_PERMISSIONS catalog
# ---------------------------------------------------------------------------


class TestRolePermissions:
    def test_four_roles_defined(self):
        assert set(ROLE_PERMISSIONS.keys()) == {"owner", "admin", "compliance_manager", "viewer"}

    def test_owner_has_all_permission(self):
        assert ROLE_PERMISSIONS["owner"]["permissions"] == ["all"]

    def test_viewer_is_read_only(self):
        assert ROLE_PERMISSIONS["viewer"]["permissions"] == ["read"]

    def test_admin_excludes_billing(self):
        perms = ROLE_PERMISSIONS["admin"]["permissions"]
        assert "billing" not in perms
        assert "team" in perms

    def test_compliance_manager_cannot_access_team_or_settings(self):
        perms = ROLE_PERMISSIONS["compliance_manager"]["permissions"]
        assert "team" not in perms
        assert "settings" not in perms
        assert "compliance" in perms

    def test_each_role_has_label_and_description(self):
        for role, defn in ROLE_PERMISSIONS.items():
            assert "label" in defn
            assert "description" in defn
            assert "permissions" in defn


# ---------------------------------------------------------------------------
# _db_get_team
# ---------------------------------------------------------------------------


class TestDbGetTeam:
    def test_returns_none_when_no_db(self, monkeypatch):
        monkeypatch.setattr(tm, "get_db_safe", lambda: None)
        assert _db_get_team("t1") is None

    def test_returns_empty_list_when_no_rows(self, monkeypatch):
        session = _mock_db_session(rows=[])
        monkeypatch.setattr(tm, "get_db_safe", lambda: session)
        result = _db_get_team("t1")
        assert result == []
        session.close.assert_called_once()

    def test_maps_rows_to_team_members(self, monkeypatch):
        session = _mock_db_session(rows=[
            ("m1", "Alice Smith", "a@x.com", "admin", "active", "2026-04-18T00:00:00Z", None),
            ("m2", "Bob Jones", "b@x.com", "viewer", "invited", None, "2026-04-18T00:00:00Z"),
        ])
        monkeypatch.setattr(tm, "get_db_safe", lambda: session)
        result = _db_get_team("t1")
        assert len(result) == 2
        assert result[0].id == "m1"
        assert result[0].name == "Alice Smith"
        assert result[0].avatar_initials == "AS"
        assert result[0].is_sample is False
        assert result[1].avatar_initials == "BJ"

    def test_avatar_initials_single_word_name(self, monkeypatch):
        session = _mock_db_session(rows=[
            ("m1", "Alice", "a@x.com", "admin", "active", None, None),
        ])
        monkeypatch.setattr(tm, "get_db_safe", lambda: session)
        result = _db_get_team("t1")
        assert result[0].avatar_initials == "A"

    def test_avatar_initials_multi_word_takes_first_two(self, monkeypatch):
        session = _mock_db_session(rows=[
            ("m1", "Alice Beatrice Carol Smith", "a@x.com", "admin", "active", None, None),
        ])
        monkeypatch.setattr(tm, "get_db_safe", lambda: session)
        result = _db_get_team("t1")
        assert result[0].avatar_initials == "AB"

    def test_avatar_initials_empty_name_is_empty(self, monkeypatch):
        session = _mock_db_session(rows=[
            ("m1", "", "a@x.com", "admin", "active", None, None),
        ])
        monkeypatch.setattr(tm, "get_db_safe", lambda: session)
        result = _db_get_team("t1")
        assert result[0].avatar_initials == ""

    def test_exception_returns_none_and_closes(self, monkeypatch):
        session = _mock_db_session(raise_on_execute=True)
        monkeypatch.setattr(tm, "get_db_safe", lambda: session)
        result = _db_get_team("t1")
        assert result is None
        session.close.assert_called_once()

    def test_execute_receives_tenant_id_parameter(self, monkeypatch):
        session = _mock_db_session(rows=[])
        monkeypatch.setattr(tm, "get_db_safe", lambda: session)
        _db_get_team("tenant-xyz")
        _sql, params = session.execute.call_args[0]
        assert params == {"tid": "tenant-xyz"}


# ---------------------------------------------------------------------------
# _db_add_team_member
# ---------------------------------------------------------------------------


class TestDbAddTeamMember:
    def _member(self):
        return TeamMember(
            id="m1", name="Alice", email="a@x.com", role="admin", status="active",
            last_active="2026-04-18T00:00:00Z", invited_at=None,
        )

    def test_returns_false_when_no_db(self, monkeypatch):
        monkeypatch.setattr(tm, "get_db_safe", lambda: None)
        assert _db_add_team_member("t1", self._member()) is False

    def test_happy_path_execute_and_commit(self, monkeypatch):
        session = _mock_db_session()
        monkeypatch.setattr(tm, "get_db_safe", lambda: session)
        result = _db_add_team_member("t1", self._member())
        assert result is True
        session.execute.assert_called_once()
        session.commit.assert_called_once()
        session.close.assert_called_once()

    def test_params_passed_to_execute(self, monkeypatch):
        session = _mock_db_session()
        monkeypatch.setattr(tm, "get_db_safe", lambda: session)
        _db_add_team_member("tenant-x", self._member())
        _sql, params = session.execute.call_args[0]
        assert params["id"] == "m1"
        assert params["tid"] == "tenant-x"
        assert params["name"] == "Alice"
        assert params["email"] == "a@x.com"
        assert params["role"] == "admin"
        assert params["status"] == "active"
        assert params["active"] == "2026-04-18T00:00:00Z"
        assert params["invited"] is None

    def test_exception_rolls_back_and_returns_false(self, monkeypatch):
        session = _mock_db_session(raise_on_execute=True)
        monkeypatch.setattr(tm, "get_db_safe", lambda: session)
        result = _db_add_team_member("t1", self._member())
        assert result is False
        session.rollback.assert_called_once()
        session.close.assert_called_once()

    def test_close_always_called(self, monkeypatch):
        session = _mock_db_session()
        monkeypatch.setattr(tm, "get_db_safe", lambda: session)
        _db_add_team_member("t1", self._member())
        session.close.assert_called_once()


# ---------------------------------------------------------------------------
# GET /{tenant_id}
# ---------------------------------------------------------------------------


class TestGetTeamEndpoint:
    def test_db_hit_populates_response(self, client, monkeypatch):
        members = [
            TeamMember(id="m1", name="Alice", email="a@x.com", role="admin", status="active"),
            TeamMember(id="m2", name="Bob", email="b@x.com", role="viewer", status="active"),
            TeamMember(id="m3", name="Carol", email="c@x.com", role="viewer", status="invited"),
        ]
        monkeypatch.setattr(tm, "_db_get_team", lambda tid: members)
        resp = client.get("/api/v1/team/t1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "t1"
        assert body["total_members"] == 3
        assert body["active_members"] == 2
        assert body["pending_invites"] == 1
        assert body["roles_breakdown"] == {"admin": 1, "viewer": 2}

    def test_db_none_falls_back_to_memory(self, client, monkeypatch):
        monkeypatch.setattr(tm, "_db_get_team", lambda tid: None)
        _team_store["t1"] = [
            TeamMember(id="m1", name="Alice", email="a@x.com", role="admin", status="active"),
        ]
        resp = client.get("/api/v1/team/t1")
        assert resp.status_code == 200
        assert resp.json()["total_members"] == 1

    def test_db_none_empty_memory_initializes_and_returns_empty(self, client, monkeypatch):
        monkeypatch.setattr(tm, "_db_get_team", lambda tid: None)
        resp = client.get("/api/v1/team/brand-new")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_members"] == 0
        assert body["active_members"] == 0
        assert body["pending_invites"] == 0
        assert body["roles_breakdown"] == {}
        assert "brand-new" in _team_store

    def test_empty_team_from_db_is_not_none(self, client, monkeypatch):
        # _db_get_team returns [] (not None) — should NOT fall through to memory
        monkeypatch.setattr(tm, "_db_get_team", lambda tid: [])
        _team_store["t1"] = [
            TeamMember(id="shadow", name="Shadow", email="s@x.com", role="viewer", status="active"),
        ]
        resp = client.get("/api/v1/team/t1")
        assert resp.status_code == 200
        # Empty list from DB wins, not memory cache
        assert resp.json()["total_members"] == 0


# ---------------------------------------------------------------------------
# POST /{tenant_id}/invite
# ---------------------------------------------------------------------------


class TestInviteMemberEndpoint:
    def test_invite_when_db_writable(self, client, monkeypatch):
        monkeypatch.setattr(tm, "_db_get_team", lambda tid: [])
        monkeypatch.setattr(tm, "_db_add_team_member", lambda tid, m: True)
        resp = client.post(
            "/api/v1/team/t1/invite",
            json={"email": "new@x.com", "name": "New Person", "role": "admin"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["invited"] is True
        assert body["member"]["email"] == "new@x.com"
        assert body["member"]["status"] == "invited"
        assert body["member"]["role"] == "admin"
        assert body["member"]["id"] == "t1-user-001"
        assert body["member"]["avatar_initials"] == "NP"
        assert body["member"]["invited_at"]

    def test_invite_falls_back_to_memory_when_db_fails(self, client, monkeypatch):
        monkeypatch.setattr(tm, "_db_get_team", lambda tid: None)
        monkeypatch.setattr(tm, "_db_add_team_member", lambda tid, m: False)
        resp = client.post(
            "/api/v1/team/t1/invite",
            json={"email": "new@x.com", "name": "New Person"},
        )
        assert resp.status_code == 200
        assert len(_team_store["t1"]) == 1
        assert _team_store["t1"][0].email == "new@x.com"

    def test_invite_id_increments_with_existing_members(self, client, monkeypatch):
        existing = [
            TeamMember(id="t1-user-001", name="A", email="a@x.com", role="admin", status="active"),
            TeamMember(id="t1-user-002", name="B", email="b@x.com", role="admin", status="active"),
        ]
        monkeypatch.setattr(tm, "_db_get_team", lambda tid: existing)
        monkeypatch.setattr(tm, "_db_add_team_member", lambda tid, m: True)
        resp = client.post(
            "/api/v1/team/t1/invite",
            json={"email": "c@x.com", "name": "Carol"},
        )
        assert resp.json()["member"]["id"] == "t1-user-003"

    def test_invite_seeds_empty_memory_when_db_unavailable(self, client, monkeypatch):
        monkeypatch.setattr(tm, "_db_get_team", lambda tid: None)
        monkeypatch.setattr(tm, "_db_add_team_member", lambda tid, m: False)
        resp = client.post(
            "/api/v1/team/brand-new/invite",
            json={"email": "new@x.com", "name": "New"},
        )
        assert resp.status_code == 200
        assert "brand-new" in _team_store
        assert len(_team_store["brand-new"]) == 1

    def test_invite_db_read_ok_write_fail_with_no_memory_initializes_memory(self, client, monkeypatch):
        # DB read returns a list (not None) so line 206 doesn't init memory.
        # DB write fails. Memory didn't have tenant_id yet -> line 223-224 runs.
        monkeypatch.setattr(
            tm, "_db_get_team",
            lambda tid: [TeamMember(id="existing", name="E", email="e@x.com", role="admin", status="active")]
        )
        monkeypatch.setattr(tm, "_db_add_team_member", lambda tid, m: False)
        assert "fresh-tenant" not in _team_store
        resp = client.post(
            "/api/v1/team/fresh-tenant/invite",
            json={"email": "new@x.com", "name": "New Person"},
        )
        assert resp.status_code == 200
        # Line 223-224 initialized an empty list and appended the new member
        assert "fresh-tenant" in _team_store
        assert len(_team_store["fresh-tenant"]) == 1
        assert _team_store["fresh-tenant"][0].email == "new@x.com"

    def test_invite_default_role_viewer(self, client, monkeypatch):
        monkeypatch.setattr(tm, "_db_get_team", lambda tid: [])
        monkeypatch.setattr(tm, "_db_add_team_member", lambda tid, m: True)
        resp = client.post(
            "/api/v1/team/t1/invite",
            json={"email": "new@x.com", "name": "New Person"},
        )
        assert resp.json()["member"]["role"] == "viewer"

    def test_invite_avatar_single_name(self, client, monkeypatch):
        monkeypatch.setattr(tm, "_db_get_team", lambda tid: [])
        monkeypatch.setattr(tm, "_db_add_team_member", lambda tid, m: True)
        resp = client.post(
            "/api/v1/team/t1/invite",
            json={"email": "m@x.com", "name": "Madonna"},
        )
        assert resp.json()["member"]["avatar_initials"] == "M"


# ---------------------------------------------------------------------------
# PUT /{tenant_id}/{member_id}/role
# ---------------------------------------------------------------------------


class TestUpdateRoleEndpoint:
    def test_update_role_db_path(self, client, monkeypatch):
        member = TeamMember(id="m1", name="Alice", email="a@x.com", role="viewer", status="active")
        monkeypatch.setattr(tm, "_db_get_team", lambda tid: [member])
        monkeypatch.setattr(tm, "_db_add_team_member", lambda tid, m: True)
        resp = client.put("/api/v1/team/t1/m1/role", params={"role": "admin"})
        assert resp.status_code == 200
        assert resp.json() == {"updated": True, "member_id": "m1", "new_role": "admin"}

    def test_update_role_memory_fallback(self, client, monkeypatch):
        member = TeamMember(id="m1", name="Alice", email="a@x.com", role="viewer", status="active")
        _team_store["t1"] = [member]
        # DB read returns None -> memory path
        monkeypatch.setattr(tm, "_db_get_team", lambda tid: None)
        monkeypatch.setattr(tm, "_db_add_team_member", lambda tid, m: False)
        resp = client.put("/api/v1/team/t1/m1/role", params={"role": "admin"})
        assert resp.status_code == 200
        assert resp.json()["new_role"] == "admin"
        assert _team_store["t1"][0].role == "admin"

    def test_update_role_db_write_failure_mutates_memory(self, client, monkeypatch):
        member_in_memory = TeamMember(id="m1", name="Alice", email="a@x.com", role="viewer", status="active")
        _team_store["t1"] = [member_in_memory]
        # DB read returns a distinct list (simulating DB-as-source-of-truth),
        # DB write fails, so memory copy is also updated
        monkeypatch.setattr(
            tm, "_db_get_team",
            lambda tid: [TeamMember(id="m1", name="Alice", email="a@x.com", role="viewer", status="active")]
        )
        monkeypatch.setattr(tm, "_db_add_team_member", lambda tid, m: False)
        resp = client.put("/api/v1/team/t1/m1/role", params={"role": "admin"})
        assert resp.status_code == 200
        assert _team_store["t1"][0].role == "admin"

    def test_update_role_unknown_member_returns_error(self, client, monkeypatch):
        monkeypatch.setattr(tm, "_db_get_team", lambda tid: [])
        resp = client.put("/api/v1/team/t1/nonexistent/role", params={"role": "admin"})
        assert resp.status_code == 200
        assert resp.json() == {"error": "Member not found"}

    def test_update_role_db_none_no_memory_returns_error(self, client, monkeypatch):
        monkeypatch.setattr(tm, "_db_get_team", lambda tid: None)
        resp = client.put("/api/v1/team/t1/m1/role", params={"role": "admin"})
        assert resp.status_code == 200
        assert resp.json() == {"error": "Member not found"}

    def test_update_role_db_write_failure_no_memory_still_returns_updated(self, client, monkeypatch):
        # DB read succeeds, DB write fails, memory not initialized — still returns updated=True
        monkeypatch.setattr(
            tm, "_db_get_team",
            lambda tid: [TeamMember(id="m1", name="Alice", email="a@x.com", role="viewer", status="active")]
        )
        monkeypatch.setattr(tm, "_db_add_team_member", lambda tid, m: False)
        resp = client.put("/api/v1/team/t1/m1/role", params={"role": "admin"})
        assert resp.status_code == 200
        assert resp.json()["updated"] is True


# ---------------------------------------------------------------------------
# GET /roles/definitions
# ---------------------------------------------------------------------------


class TestGetRolesEndpoint:
    def test_returns_all_four_roles(self, app):
        # This endpoint has no auth dependency, but use client for consistency
        client = TestClient(app)
        resp = client.get("/api/v1/team/roles/definitions")
        assert resp.status_code == 200
        body = resp.json()
        assert "roles" in body
        assert set(body["roles"].keys()) == {"owner", "admin", "compliance_manager", "viewer"}

    def test_owner_all_permission_present(self, client):
        resp = client.get("/api/v1/team/roles/definitions")
        assert resp.json()["roles"]["owner"]["permissions"] == ["all"]


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_prefix_and_tags(self):
        assert router.prefix == "/api/v1/team"
        assert "Team Management" in router.tags

    def test_registered_paths(self):
        paths = {r.path for r in router.routes}
        assert "/api/v1/team/{tenant_id}" in paths
        assert "/api/v1/team/{tenant_id}/invite" in paths
        assert "/api/v1/team/{tenant_id}/{member_id}/role" in paths
        assert "/api/v1/team/roles/definitions" in paths
