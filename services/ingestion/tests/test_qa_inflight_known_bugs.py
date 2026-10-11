"""Known bugs in in-flight modules (product edits owned by other draft PRs).

``services/ingestion/app/team_mgmt.py`` and
``services/ingestion/app/recall_simulations.py`` are changed by other open
draft PRs, so this file adds tests only and changes no product code. Each
test below documents a real bug found during the QA pass and is marked
``xfail(strict=True)``: it fails on current code and must be converted to a
passing test when the owning work fixes the behavior.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app import team_mgmt as tm  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.recall_simulations import (  # noqa: E402
    _simulation_store as _recall_store,
    router as recall_router,  # noqa: E402
)
from app.team_mgmt import _team_store, router as team_router  # noqa: E402
from app.webhook_compat import _verify_api_key  # noqa: E402

from services.ingestion.tests.tenant_context_overrides import (  # noqa: E402
    install_tenant_context_override,
)


@pytest.fixture()
def team_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app = FastAPI()
    app.include_router(team_router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    install_tenant_context_override(app)
    _team_store.clear()
    monkeypatch.setattr(tm, "_db_get_team", lambda tid: None)
    monkeypatch.setattr(tm, "_db_add_team_member", lambda tid, m: False)
    with TestClient(app) as test_client:
        yield test_client
    _team_store.clear()


@pytest.fixture()
def recall_client() -> TestClient:
    app = FastAPI()
    app.include_router(recall_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key",
        scopes=["*"],
        tenant_id="tenant-test",
        auth_mode="test",
    )
    _recall_store.clear()
    with TestClient(app) as test_client:
        yield test_client
    _recall_store.clear()


@pytest.mark.xfail(
    strict=True,
    reason="team_mgmt invite_member stores any role string without checking ROLE_PERMISSIONS (in-flight file, not fixed here)",
)
def test_team_invite_rejects_unknown_role(team_client: TestClient) -> None:
    response = team_client.post(
        "/api/v1/team/t1/invite",
        json={"email": "mallory@example.com", "name": "Mallory", "role": "superuser"},
    )
    assert response.status_code in (400, 422)


@pytest.mark.xfail(
    strict=True,
    reason="team_mgmt InviteRequest.email is a plain str, so malformed emails are invited (in-flight file, not fixed here)",
)
def test_team_invite_rejects_malformed_email(team_client: TestClient) -> None:
    response = team_client.post(
        "/api/v1/team/t1/invite",
        json={"email": "not-an-email", "name": "Nobody", "role": "viewer"},
    )
    assert response.status_code in (400, 422)


@pytest.mark.xfail(
    strict=True,
    reason="team_mgmt update_role writes any role string without checking ROLE_PERMISSIONS (in-flight file, not fixed here)",
)
def test_team_update_role_rejects_unknown_role(
    team_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    invite = team_client.post(
        "/api/v1/team/t1/invite",
        json={"email": "member@example.com", "name": "Member", "role": "viewer"},
    )
    assert invite.status_code == 200
    member_id = invite.json()["member"]["id"]
    response = team_client.put(f"/api/v1/team/t1/{member_id}/role", params={"role": "superuser"})
    assert response.status_code in (400, 422)


@pytest.mark.xfail(
    strict=True,
    reason="recall_simulations timeline/impact-graph reads drop the illustrative-data disclaimer the main read attaches (in-flight file, not fixed here)",
)
def test_recall_timeline_carries_illustrative_disclaimer(recall_client: TestClient) -> None:
    run_response = recall_client.post("/api/v1/simulations/run", json={"scenario_id": "romaine-ecoli"})
    assert run_response.status_code == 201
    simulation_id = run_response.json()["id"]

    timeline = recall_client.get(f"/api/v1/simulations/{simulation_id}/timeline")
    assert timeline.status_code == 200
    payload = timeline.json()
    assert payload.get("is_illustrative") is True
    assert payload.get("demo_disclaimer")
