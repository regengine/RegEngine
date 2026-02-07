from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from ...fsma_utils import check_mass_balance, check_mass_balance_for_lot
from ...neo4j_utils import Neo4jClient
from ...neo4j_utils import Neo4jClient
from shared.auth import require_api_key

import uuid
import sys
# Add shared utilities
sys.path.insert(0, '/Users/christophersellers/Desktop/RegEngine/services')
from shared.middleware import get_current_tenant_id

router = APIRouter(tags=["Science"])
logger = structlog.get_logger("fsma-science")


@router.get("/mass-balance/{tlc}")
async def mass_balance_endpoint(
    tlc: str,
    tolerance: float = Query(
        0.10, ge=0.0, le=1.0, description="Allowed variance (0.10 = 10%)"
    ),
    tag_imbalance: bool = Query(
        True, description="Tag events with MASS_IMBALANCE risk flag"
    ),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Check mass balance for all transformation events involving a lot.

    Physics Engine Feature: Validates mass conservation across supply chain.

    Rule: sum(inputs.quantity) * (1 + tolerance) >= sum(outputs.quantity)

    - Allows for yield loss (less output than input)
    - Flags if output exceeds input by more than tolerance (default 10%)
    - Optionally tags TraceEvent nodes with risk_flag: "MASS_IMBALANCE"

    Use case: Detect fraudulent quantity inflation or data entry errors.
    """
    db_name = Neo4jClient.get_tenant_database_name(tenant_id)
    client = Neo4jClient(database=db_name)

    try:
        report = await check_mass_balance_for_lot(
            client,
            tlc,
            tolerance=tolerance,
            tenant_id=str(tenant_id),
            tag_imbalance=tag_imbalance,
        )
        await client.close()

        return {
            "lot_id": report.lot_id,
            "transformation_count": report.transformation_count,
            "balanced_count": report.balanced_count,
            "imbalanced_count": report.imbalanced_count,
            "flagged_events": report.flagged_events,
            "events": [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type,
                    "event_date": e.event_date,
                    "input_quantity": e.input_quantity,
                    "output_quantity": e.output_quantity,
                    "imbalance_ratio": e.imbalance_ratio,
                    "is_balanced": e.is_balanced,
                    "risk_flag": e.risk_flag,
                    "input_lots": e.input_lots,
                    "output_lots": e.output_lots,
                }
                for e in report.events
            ],
            "query_time_ms": report.query_time_ms,
        }
    except Exception as e:
        logger.exception("mass_balance_error", tlc=tlc, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mass-balance/event/{event_id}")
async def mass_balance_event_endpoint(
    event_id: str,
    tolerance: float = Query(
        0.10, ge=0.0, le=1.0, description="Allowed variance (0.10 = 10%)"
    ),
    tag_imbalance: bool = Query(
        True, description="Tag event with MASS_IMBALANCE risk flag"
    ),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Check mass balance for a single transformation event.

    Physics Engine Feature: Validates mass conservation for one event.

    Returns detailed breakdown of:
    - Input lots and quantities consumed
    - Output lots and quantities produced
    - Imbalance ratio and balance status
    """
    db_name = Neo4jClient.get_tenant_database_name(tenant_id)
    client = Neo4jClient(database=db_name)

    try:
        result = await check_mass_balance(
            client,
            event_id,
            tolerance=tolerance,
            tenant_id=str(tenant_id),
            tag_imbalance=tag_imbalance,
        )
        await client.close()

        return {
            "event_id": result.event_id,
            "event_type": result.event_type,
            "event_date": result.event_date,
            "input_quantity": result.input_quantity,
            "output_quantity": result.output_quantity,
            "imbalance_ratio": result.imbalance_ratio,
            "is_balanced": result.is_balanced,
            "tolerance": result.tolerance,
            "risk_flag": result.risk_flag,
            "input_lots": result.input_lots,
            "output_lots": result.output_lots,
        }
    except Exception as e:
        logger.exception("mass_balance_event_error", event_id=event_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
