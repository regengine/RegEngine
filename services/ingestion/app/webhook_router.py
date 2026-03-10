"""Deprecated webhook router v1 compatibility shim.

This module is retained for backward compatibility with legacy imports.
It delegates all ingest/auth behavior to the v2-backed compatibility surface.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header

from app.webhook_compat import _verify_api_key
from app.webhook_compat import ingest_events as ingest_events_v2
from app.webhook_models import IngestResponse, WebhookPayload

logger = logging.getLogger("webhook-ingestion")

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhook Ingestion"])

_deprecation_logged = False


def _log_deprecation_once() -> None:
    global _deprecation_logged
    if _deprecation_logged:
        return
    logger.warning(
        "webhook_router_v1_deprecated",
        extra={
            "replacement_router": "app.webhook_router_v2",
            "replacement_helpers": "app.webhook_compat",
        },
    )
    _deprecation_logged = True


async def ingest_events(
    payload: WebhookPayload,
    x_regengine_api_key: Optional[str] = None,
) -> IngestResponse:
    """Backward-compatible helper that delegates to v2 ingestion."""
    _log_deprecation_once()
    return await ingest_events_v2(
        payload=payload,
        x_regengine_api_key=x_regengine_api_key,
    )


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Ingest traceability events (deprecated shim)",
)
async def ingest_events_endpoint(
    payload: WebhookPayload,
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
) -> IngestResponse:
    """Deprecated endpoint shim for legacy callers."""
    return await ingest_events(
        payload=payload,
        x_regengine_api_key=x_regengine_api_key,
    )
