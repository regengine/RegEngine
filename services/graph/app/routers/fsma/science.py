from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from shared.auth import require_api_key
from shared.middleware import get_current_tenant_id

router = APIRouter(tags=["Science"])
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
