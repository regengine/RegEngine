from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from shared.auth import require_api_key
from shared.middleware import get_current_tenant_id

# Validate the API key before any endpoint parameter. The handlers below declare
# ``Depends(get_current_tenant_id)`` ahead of ``Depends(require_api_key)``, so a key-only
# caller got 401 on tenant resolution before the key was checked. Router-level
# dependencies resolve first; the per-request cache still validates the key exactly once.
router = APIRouter(tags=["Science"], dependencies=[Depends(require_api_key)])
logger = structlog.get_logger("fsma-science")


@router.get("/mass-balance/{tlc}")
async def mass_balance_endpoint(
    tlc: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Mass-balance validation has been removed from the MVP scope.

    Only deterministic cryptographic chain validation (hash-chain integrity,
    broken-chain detection) is in scope for FSMA 204 compliance.
    """
    raise HTTPException(
        status_code=501,
        detail="Mass-balance validation is not implemented. "
        "Use /chain-integrity or /broken-chains for cryptographic validation.",
    )


@router.get("/mass-balance/event/{event_id}")
async def mass_balance_event_endpoint(
    event_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Mass-balance validation has been removed from the MVP scope.

    Only deterministic cryptographic chain validation (hash-chain integrity,
    broken-chain detection) is in scope for FSMA 204 compliance.
    """
    raise HTTPException(
        status_code=501,
        detail="Mass-balance validation is not implemented. "
        "Use /chain-integrity or /broken-chains for cryptographic validation.",
    )
