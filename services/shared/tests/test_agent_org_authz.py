"""Unit tests for ``shared.agent_org.authz.require_agent_key``.

No live DB: ``shared.auth.require_api_key`` (the only collaborator that
would otherwise need a database) is swapped out via FastAPI's own
``app.dependency_overrides``, the exact technique
``test_agent_org_router.py`` uses for the same purpose. This isolates the
three checks ``require_agent_key`` itself adds on top of authentication:
agent-scoping, cross-agent rejection, and the capability check.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from shared.agent_org.authz import AgentPrincipal, require_agent_key
from shared.api_key_store import APIKeyResponse
from shared.auth import require_api_key


def _api_key(**overrides) -> APIKeyResponse:
    defaults = dict(
        key_id="key-1",
        key_prefix="rk_test_abc",
        name="test key",
        tenant_id="tenant-1",
        agent_id="agent-1",
        scopes=["agent.inbox.read"],
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return APIKeyResponse(**defaults)


def _build_app(api_key: APIKeyResponse, *, required_capability: str = "agent.inbox.read") -> FastAPI:
    app = FastAPI()

    @app.get("/agents/{agent_id}/widgets")
    async def widgets(agent_id: str, principal: AgentPrincipal = Depends(require_agent_key(required_capability))):
        return {"principal": principal.model_dump()}

    app.dependency_overrides[require_api_key] = lambda: api_key
    return app


class TestRequireAgentKey:
    def test_agent_scoped_key_with_matching_agent_and_capability_succeeds(self):
        app = _build_app(_api_key(agent_id="agent-1", scopes=["agent.inbox.read"]))
        client = TestClient(app)

        response = client.get("/agents/agent-1/widgets")

        assert response.status_code == 200
        body = response.json()["principal"]
        assert body["key_id"] == "key-1"
        assert body["tenant_id"] == "tenant-1"
        assert body["agent_id"] == "agent-1"
        assert body["scopes"] == ["agent.inbox.read"]

    def test_key_with_no_agent_id_is_rejected_even_with_the_capability(self):
        # An ordinary tenant-wide key must never satisfy an agent-scoped
        # route just because it happens to carry a matching scope string.
        app = _build_app(_api_key(agent_id=None, scopes=["agent.inbox.read"]))
        client = TestClient(app)

        response = client.get("/agents/agent-1/widgets")

        assert response.status_code == 403
        assert "not agent-scoped" in response.json()["detail"]

    def test_key_scoped_to_a_different_agent_is_rejected(self):
        # The core isolation property: a valid key for agent-1 must not
        # work against agent-2's resources, even within the same tenant.
        app = _build_app(_api_key(agent_id="agent-2", scopes=["agent.inbox.read"]))
        client = TestClient(app)

        response = client.get("/agents/agent-1/widgets")

        assert response.status_code == 403
        assert "not scoped to this agent" in response.json()["detail"]

    def test_key_missing_the_required_capability_is_rejected(self):
        app = _build_app(_api_key(agent_id="agent-1", scopes=["agent.suppression.read"]))
        client = TestClient(app)

        response = client.get("/agents/agent-1/widgets")

        assert response.status_code == 403
        assert "Missing capability" in response.json()["detail"]

    def test_namespace_wildcard_scope_grants_the_capability(self):
        # has_permission() supports "agent.*" namespace wildcards; this
        # dependency must honor that, not just exact string matches.
        app = _build_app(_api_key(agent_id="agent-1", scopes=["agent.*"]))
        client = TestClient(app)

        response = client.get("/agents/agent-1/widgets")

        assert response.status_code == 200

    def test_empty_scopes_are_rejected(self):
        app = _build_app(_api_key(agent_id="agent-1", scopes=[]))
        client = TestClient(app)

        response = client.get("/agents/agent-1/widgets")

        assert response.status_code == 403

    @pytest.mark.parametrize("agent_id_type_mismatch", ["agent-1", " agent-1", "AGENT-1"])
    def test_agent_id_comparison_is_exact_string_match(self, agent_id_type_mismatch):
        # str(key_agent_id) != str(agent_id) is a plain equality check —
        # no normalization. Anything other than the exact path value must
        # fail except the true exact match.
        app = _build_app(_api_key(agent_id=agent_id_type_mismatch, scopes=["agent.inbox.read"]))
        client = TestClient(app)

        response = client.get("/agents/agent-1/widgets")

        if agent_id_type_mismatch == "agent-1":
            assert response.status_code == 200
        else:
            assert response.status_code == 403
