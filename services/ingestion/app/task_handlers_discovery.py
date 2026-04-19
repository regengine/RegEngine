"""Task-queue handler for discovery scrape jobs (ADR-002 PR-D).

Registers one task type:
  - ``discovery_scrape`` — calls kernel.discovery.scrape(body, url)

Used by /v1/ingest/discovery/approve and /v1/ingest/discovery/bulk-approve
to replace BackgroundTasks.add_task(discovery.scrape, body, url).
"""

from __future__ import annotations

import asyncio
from typing import Any

from shared.task_queue import register_task_handler

from kernel.discovery import discovery


def _handle_discovery_scrape(
    *,
    body: str,
    url: str,
    **_: Any,
) -> None:
    asyncio.run(discovery.scrape(body, url))


def register_discovery_handlers() -> None:
    """Call once at startup to wire handlers into TASK_HANDLERS."""
    register_task_handler("discovery_scrape", _handle_discovery_scrape)
