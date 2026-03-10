"""Compatibility helpers for webhook auth and ingestion.

This module is the stable import surface for non-router ingestion modules.
Legacy `webhook_router.py` has been retired; `webhook_router_v2.py` remains
the mounted HTTP router.
"""

from __future__ import annotations

from typing import Optional

from app.webhook_models import IngestResponse, WebhookPayload
from app.webhook_router_v2 import _verify_api_key, ingest_events as ingest_events_v2


async def ingest_events(
    payload: WebhookPayload,
    x_regengine_api_key: Optional[str] = None,
) -> IngestResponse:
    """Delegate ingestion to webhook router v2 using explicit key passthrough."""
    return await ingest_events_v2(
        payload=payload,
        x_regengine_api_key=x_regengine_api_key,
    )
