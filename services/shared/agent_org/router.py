"""API route for one-call agent-org onboarding.

See ``DESIGN_agent-org.md`` section 6. Mounted in ``server/main.py``
following the exact ``_router_enabled(...)`` / ``include_owned_router(...)``
pattern used for every other domain router (the ``remediation`` block is
the direct template).

Authentication/authorization reuse ``services.ingestion.app.authz``'s
``IngestionPrincipal`` / ``require_permission`` and
``services.ingestion.app.tenant_validation.resolve_tenant`` — the same
tenant-key auth stack every other tenant-scoped router in this monolith
uses (see ``services/ingestion/app/remediation/router.py``). Onboarding is
performed with a full tenant key carrying the ``agent_org.admin``
permission scope, never an agent-scoped key (those are minted *by* this
call and carry only the narrow ``agent.*`` capabilities from
``shared.agent_org.keys.AGENT_KEY_CAPABILITIES`` — a distinct namespace,
never checked here).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from shared.database import get_db_session

from services.ingestion.app.authz import IngestionPrincipal, require_permission
from services.ingestion.app.tenant_validation import resolve_tenant

from .onboarding import PodSpec, onboard_tenant_agent_org

router = APIRouter(prefix="/agent-org", tags=["Agent Organization"])

_get_db_session = get_db_session  # test-override alias, mirrors remediation/router.py

#: Per-request ceilings. Each individual pod's ``agent_count`` was already
#: bounded (<=50), but nothing capped how many *pods* one request could
#: list, so a single call could still request an effectively unbounded
#: number of agents (e.g. 2,000 pods x 50 agents each). Every agent
#: onboarded costs `onboard_tenant_agent_org` a synchronous DB round trip,
#: a `db.commit()`, and an awaited key-mint call against a separate async
#: engine, so both the pod count and the total agent count summed across
#: all pods must be capped up front — this is a one-call *onboarding*
#: endpoint for a real org's headcount, not a bulk-provisioning API.
MAX_PODS_PER_REQUEST = 20
MAX_TOTAL_AGENTS_PER_REQUEST = 200


class PodSpecRequest(BaseModel):
    """One pod to create/find during onboarding."""

    name: str
    department: Literal["research", "outreach", "ops", "legal_review"]
    agent_count: int = Field(gt=0, le=50)


class OnboardRequest(BaseModel):
    pods: list[PodSpecRequest] = Field(min_length=1, max_length=MAX_PODS_PER_REQUEST)

    @model_validator(mode="after")
    def _check_total_agent_count(self) -> "OnboardRequest":
        total = sum(p.agent_count for p in self.pods)
        if total > MAX_TOTAL_AGENTS_PER_REQUEST:
            raise ValueError(
                f"Total agent_count across all pods ({total}) exceeds the "
                f"per-request limit of {MAX_TOTAL_AGENTS_PER_REQUEST}. Split "
                "large onboarding requests into multiple calls."
            )
        return self


class OnboardingResultResponse(BaseModel):
    """Summary of one onboarding call — never carries raw key material."""

    tenant_id: str
    pods_created: int
    agents_created: int
    inboxes_created: int
    keys_created: int
    inbox_addresses: list[str] = Field(default_factory=list)
    key_ids: list[str] = Field(default_factory=list)  # key_id only — never raw_key


@router.post(
    "/onboard",
    response_model=OnboardingResultResponse,
    summary="Onboard a tenant's agent organization (pods, agents, inboxes, scoped keys) in one call",
)
async def onboard(
    body: OnboardRequest,
    principal: IngestionPrincipal = Depends(require_permission("agent_org.admin")),
    db_session=Depends(_get_db_session),
) -> OnboardingResultResponse:
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    tid = resolve_tenant(None, principal)
    result = await onboard_tenant_agent_org(
        db_session,
        tid,
        [PodSpec(name=p.name, department=p.department, agent_count=p.agent_count) for p in body.pods],
    )
    return OnboardingResultResponse(**asdict(result))
