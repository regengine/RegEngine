"""Compatibility helpers for webhook auth and ingestion.

This module is the stable import surface for non-router ingestion modules.
All auth logic delegates to ``shared.auth.require_api_key`` — the single
canonical auth path for every RegEngine service.

Legacy ``webhook_router.py`` has been retired; ``webhook_router_v2.py``
remains the mounted HTTP router.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Header, Request

from app.webhook_models import IngestResponse, WebhookPayload
from app.webhook_router_v2 import ingest_events as ingest_events_v2
from shared.auth import require_api_key


async def _verify_api_key(
    request: Request,
    x_regengine_api_key: Optional[str] = Header(
        default=None, alias="X-RegEngine-API-Key"
    ),
) -> None:
    """Auth gate — delegates to shared.auth.require_api_key.

    This is the stable import surface for ingestion sub-routers.
    All auth logic (preshared key, scoped keys, test bypass) lives
    in ``shared/auth.py``.  Callers use ``Depends(_verify_api_key)``
    exactly as before; the return value is discarded.
    """
    await require_api_key(request=request, x_regengine_api_key=x_regengine_api_key)


async def ingest_events(
    payload: WebhookPayload,
    x_regengine_api_key: Optional[str] = None,
) -> IngestResponse:
    """Delegate ingestion to webhook router v2 using explicit key passthrough."""
    return await ingest_events_v2(
        payload=payload,
        x_regengine_api_key=x_regengine_api_key,
    )
