"""Task-queue handler for discovery scrape jobs (ADR-002 PR-D).

Registers one task type:
  - ``discovery_scrape`` — calls services.ingestion.app.discovery.scrape(body, url)

Used by /v1/ingest/discovery/approve and /v1/ingest/discovery/bulk-approve
to replace BackgroundTasks.add_task(discovery.scrape, body, url).
"""

from __future__ import annotations

import asyncio
from typing import Any

from shared.task_queue import register_task_handler

from .discovery import discovery


def _handle_discovery_scrape(
    *,
    body: str,
    url: str,
    tenant_id: str = "system",
    **_: Any,
) -> None:
    # Forward the owning tenant so a robots-denied re-scrape re-queues to
    # that tenant's manual_upload_queue instead of the system queue.
    # The "system" default keeps payloads enqueued before this field
    # existed working unchanged.
    asyncio.run(discovery.scrape(body, url, tenant_id=tenant_id))


def register_discovery_handlers() -> None:
    """Call once at startup to wire handlers into TASK_HANDLERS."""
    register_task_handler("discovery_scrape", _handle_discovery_scrape)
