"""Cross-agent / cross-tenant isolation for agent-scoped API keys.

Mirrors ``services/ingestion/app/authz.py``'s ``require_permission()``
shape: a FastAPI dependency *factory* that reuses ``shared.auth.
require_api_key`` for the actual credential validation (hash check,
enabled/expiry/revocation, rate limiting) and only adds the agent-scope
layer on top.

Cross-tenant isolation falls out of ``require_api_key`` itself: it
already rejects any key whose ``tenant_id`` doesn't match the resolved
tenant context. ``require_agent_key`` adds the *additional* agent-level
narrowing that doesn't exist on tenant-scoped keys today: a valid
tenant-scoped key for tenant A, agent 1 must not be usable against
agent 2's resources even within the same tenant. That is the isolation
property this whole scoped-key feature exists to prove, and it's a pure
Python equality check plus the capability allowlist — no new DB round
trip.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field
from shared.api_key_store import APIKeyResponse
from shared.auth import require_api_key
from shared.permissions import has_permission


class AgentPrincipal(BaseModel):
    """Authenticated caller context for an agent-scoped route."""

    key_id: str
    tenant_id: str
    agent_id: str
    scopes: list[str] = Field(default_factory=list)


def require_agent_key(required_capability: str):
    """FastAPI dependency factory: require an agent-scoped key.

    The returned dependency authenticates the request (via
    ``shared.auth.require_api_key``), then requires that the presented
    key:

    1. is agent-scoped at all (``api_key.agent_id`` is set) — an
       ordinary tenant-wide key is rejected even if it would otherwise
       carry ``required_capability``;
    2. is scoped to *this* agent — bound from the route's ``{agent_id}``
       path parameter of the same name, so a key valid for one agent
       cannot be used against a different agent's resources, even
       within the same tenant;
    3. carries a scope that grants ``required_capability``.

    Raises ``HTTPException(403)`` on any of the three failures. Returns
    an :class:`AgentPrincipal` on success.
    """

    async def _dependency(
        request: Request,
        agent_id: str,
        api_key: APIKeyResponse = Depends(require_api_key),
    ) -> AgentPrincipal:
        key_agent_id: Optional[str] = getattr(api_key, "agent_id", None)
        if not key_agent_id:
            raise HTTPException(status_code=403, detail="Key is not agent-scoped")
        if str(key_agent_id) != str(agent_id):
            # Cross-agent: the key is valid but for a *different* agent.
            raise HTTPException(status_code=403, detail="Key is not scoped to this agent")
        if not has_permission(api_key.scopes or [], required_capability):
            raise HTTPException(status_code=403, detail="Missing capability")

        return AgentPrincipal(
            key_id=api_key.key_id,
            tenant_id=str(api_key.tenant_id),
            agent_id=str(key_agent_id),
            scopes=list(api_key.scopes or []),
        )

    return _dependency
