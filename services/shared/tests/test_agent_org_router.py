"""Unit tests for the agent-org onboarding router (``POST /agent-org/onboard``).

No live DB: the request-scoped ``db_session`` dependency is overridden with a
sentinel object (never touched, since ``onboard_tenant_agent_org`` itself is
monkeypatched), matching ``services/ingestion/tests/test_rules_router.py``'s
dependency-override style. The ``get_ingestion_principal`` override below is
the same technique as ``services/ingestion/tests/authz_overrides.py``'s
``install_ingestion_principal_override`` — reimplemented locally (via fully
qualified ``services.ingestion.app.authz`` imports) instead of reusing that
helper, since it assumes the ``app.authz`` short-import alias that only
``services/ingestion``-rooted test modules get from the root conftest's
per-service ``sys.path`` shim.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.ingestion.app.authz import IngestionPrincipal, get_ingestion_principal
from shared.agent_org import router as agent_org_router_mod
from shared.agent_org.onboarding import OnboardingResult

router = agent_org_router_mod.router
_get_db_session = agent_org_router_mod._get_db_session

VALID_BODY = {
    "pods": [
        {"name": "outreach-pod-1", "department": "outreach", "agent_count": 3},
    ]
}


def _principal(**overrides: Any) -> IngestionPrincipal:
    defaults = dict(key_id="test-key", scopes=["agent_org.admin"], tenant_id="tenant-1", auth_mode="scoped_key")
    defaults.update(overrides)
    return IngestionPrincipal(**defaults)


def _build_client(principal: IngestionPrincipal, *, db_session: Any = "not-none-sentinel") -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_ingestion_principal] = lambda: principal
    app.dependency_overrides[_get_db_session] = lambda: db_session
    return TestClient(app)


def test_onboard_requires_agent_org_admin_permission(monkeypatch):
    mock_onboard = AsyncMock()
    monkeypatch.setattr(agent_org_router_mod, "onboard_tenant_agent_org", mock_onboard)

    client = _build_client(_principal(scopes=["remediation.read"]))
    response = client.post("/agent-org/onboard", json=VALID_BODY)

    assert response.status_code == 403
    mock_onboard.assert_not_called()


def test_onboard_rejects_missing_db_session(monkeypatch):
    mock_onboard = AsyncMock()
    monkeypatch.setattr(agent_org_router_mod, "onboard_tenant_agent_org", mock_onboard)

    client = _build_client(_principal(), db_session=None)
    response = client.post("/agent-org/onboard", json=VALID_BODY)

    assert response.status_code == 503
    mock_onboard.assert_not_called()


def test_onboard_calls_onboarding_with_resolved_tenant_and_returns_result(monkeypatch):
    result = OnboardingResult(
        tenant_id="tenant-1",
        pods_created=1,
        agents_created=3,
        inboxes_created=3,
        keys_created=3,
        inbox_addresses=[
            "outreach-pod-1-agent-1@agents.acme.regengine.dev",
            "outreach-pod-1-agent-2@agents.acme.regengine.dev",
            "outreach-pod-1-agent-3@agents.acme.regengine.dev",
        ],
        key_ids=["key-1", "key-2", "key-3"],
    )
    mock_onboard = AsyncMock(return_value=result)
    monkeypatch.setattr(agent_org_router_mod, "onboard_tenant_agent_org", mock_onboard)

    client = _build_client(_principal())
    response = client.post("/agent-org/onboard", json=VALID_BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == "tenant-1"
    assert body["pods_created"] == 1
    assert body["agents_created"] == 3
    assert body["inboxes_created"] == 3
    assert body["keys_created"] == 3
    assert body["inbox_addresses"] == result.inbox_addresses
    assert body["key_ids"] == ["key-1", "key-2", "key-3"]
    # Never a raw key field of any kind in the response.
    assert "raw_key" not in body

    mock_onboard.assert_awaited_once()
    _, kwargs = mock_onboard.call_args
    call_args = mock_onboard.call_args.args
    assert call_args[1] == "tenant-1"  # resolved from the authenticated principal, never client input
    pod_specs = call_args[2]
    assert len(pod_specs) == 1
    assert pod_specs[0].name == "outreach-pod-1"
    assert pod_specs[0].department == "outreach"
    assert pod_specs[0].agent_count == 3


def test_onboard_rejects_invalid_department(monkeypatch):
    mock_onboard = AsyncMock()
    monkeypatch.setattr(agent_org_router_mod, "onboard_tenant_agent_org", mock_onboard)

    client = _build_client(_principal())
    bad_body = {"pods": [{"name": "x", "department": "not_a_real_department", "agent_count": 1}]}
    response = client.post("/agent-org/onboard", json=bad_body)

    assert response.status_code == 422
    mock_onboard.assert_not_called()


@pytest.mark.parametrize("agent_count", [0, -1, 51])
def test_onboard_rejects_agent_count_outside_bounds(monkeypatch, agent_count):
    mock_onboard = AsyncMock()
    monkeypatch.setattr(agent_org_router_mod, "onboard_tenant_agent_org", mock_onboard)

    client = _build_client(_principal())
    bad_body = {"pods": [{"name": "x", "department": "ops", "agent_count": agent_count}]}
    response = client.post("/agent-org/onboard", json=bad_body)

    assert response.status_code == 422
    mock_onboard.assert_not_called()


class TestOnboardRequestSizeCaps:
    """Regression coverage for the security-review finding: each pod's
    ``agent_count`` was capped (<=50) but nothing capped the *number of
    pods* in one request, so a single call could still request an
    effectively unbounded number of agents (e.g. 2,000 pods x 50 agents),
    each costing ``onboard_tenant_agent_org`` a synchronous DB round trip,
    a commit, and an awaited key-mint call. Both the pod-count and the
    total-agent-count-across-all-pods ceilings must reject oversized
    requests before ``onboard_tenant_agent_org`` is ever called.
    """

    def test_rejects_empty_pods_list(self, monkeypatch):
        mock_onboard = AsyncMock()
        monkeypatch.setattr(agent_org_router_mod, "onboard_tenant_agent_org", mock_onboard)

        client = _build_client(_principal())
        response = client.post("/agent-org/onboard", json={"pods": []})

        assert response.status_code == 422
        mock_onboard.assert_not_called()

    def test_rejects_too_many_pods(self, monkeypatch):
        mock_onboard = AsyncMock()
        monkeypatch.setattr(agent_org_router_mod, "onboard_tenant_agent_org", mock_onboard)

        too_many_pods = [
            {"name": f"pod-{i}", "department": "ops", "agent_count": 1}
            for i in range(agent_org_router_mod.MAX_PODS_PER_REQUEST + 1)
        ]
        client = _build_client(_principal())
        response = client.post("/agent-org/onboard", json={"pods": too_many_pods})

        assert response.status_code == 422
        mock_onboard.assert_not_called()

    def test_accepts_pod_count_at_the_limit(self, monkeypatch):
        mock_onboard = AsyncMock(
            return_value=OnboardingResult(
                tenant_id="tenant-1",
                pods_created=0,
                agents_created=0,
                inboxes_created=0,
                keys_created=0,
            )
        )
        monkeypatch.setattr(agent_org_router_mod, "onboard_tenant_agent_org", mock_onboard)

        pods_at_limit = [
            {"name": f"pod-{i}", "department": "ops", "agent_count": 1}
            for i in range(agent_org_router_mod.MAX_PODS_PER_REQUEST)
        ]
        client = _build_client(_principal())
        response = client.post("/agent-org/onboard", json={"pods": pods_at_limit})

        assert response.status_code == 200
        mock_onboard.assert_awaited_once()

    def test_rejects_total_agent_count_over_the_cap_even_within_pod_limits(self, monkeypatch):
        # Individually-legal pods (agent_count <= 50, pod count <=
        # MAX_PODS_PER_REQUEST) whose *sum* still exceeds the total-agent
        # ceiling — this is exactly the shape of the reported exploit,
        # just scaled down to this test's limits.
        mock_onboard = AsyncMock()
        monkeypatch.setattr(agent_org_router_mod, "onboard_tenant_agent_org", mock_onboard)

        per_pod = 50
        num_pods = agent_org_router_mod.MAX_TOTAL_AGENTS_PER_REQUEST // per_pod + 1
        assert num_pods <= agent_org_router_mod.MAX_PODS_PER_REQUEST
        pods = [{"name": f"pod-{i}", "department": "ops", "agent_count": per_pod} for i in range(num_pods)]

        client = _build_client(_principal())
        response = client.post("/agent-org/onboard", json={"pods": pods})

        assert response.status_code == 422
        mock_onboard.assert_not_called()
