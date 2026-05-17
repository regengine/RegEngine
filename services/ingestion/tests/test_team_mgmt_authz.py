from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import team_mgmt


TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"


def _api_key(tenant_id: str | None = TENANT_A, scopes: list[str] | None = None):
    return SimpleNamespace(
        tenant_id=tenant_id,
        scopes=scopes if scopes is not None else ["read", "admin"],
    )


@pytest.fixture(autouse=True)
def _reset_team_store(monkeypatch):
    monkeypatch.setattr(team_mgmt, "_team_store", {})
    monkeypatch.setattr(team_mgmt, "_db_get_team", lambda _tenant_id: None)
    monkeypatch.setattr(team_mgmt, "_db_add_team_member", lambda _tenant_id, _member: False)


@pytest.mark.asyncio
async def test_get_team_rejects_cross_tenant_api_key():
    with pytest.raises(HTTPException) as exc:
        await team_mgmt.get_team(TENANT_B, api_key=_api_key(TENANT_A))

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_team_rejects_unscoped_api_key():
    with pytest.raises(HTTPException) as exc:
        await team_mgmt.get_team(TENANT_A, api_key=_api_key(None))

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_invite_requires_admin_api_key_scope():
    request = team_mgmt.InviteRequest(
        email="new-user@example.test",
        name="New User",
        role="viewer",
    )

    with pytest.raises(HTTPException) as exc:
        await team_mgmt.invite_member(
            TENANT_A,
            request,
            api_key=_api_key(TENANT_A, scopes=["read", "ingest"]),
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_invite_rejects_unknown_role():
    request = team_mgmt.InviteRequest(
        email="new-user@example.test",
        name="New User",
        role="superuser",
    )

    with pytest.raises(HTTPException) as exc:
        await team_mgmt.invite_member(TENANT_A, request, api_key=_api_key(TENANT_A))

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_role_requires_admin_scope_and_known_role():
    with pytest.raises(HTTPException) as exc:
        await team_mgmt.update_role(
            TENANT_A,
            "member-1",
            "owner",
            api_key=_api_key(TENANT_A, scopes=["read"]),
        )

    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as invalid_role:
        await team_mgmt.update_role(
            TENANT_A,
            "member-1",
            "superuser",
            api_key=_api_key(TENANT_A),
        )

    assert invalid_role.value.status_code == 400
