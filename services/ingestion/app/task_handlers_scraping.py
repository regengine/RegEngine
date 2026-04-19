"""Task-queue handlers for scraper routes (ADR-002 PR-C).

Registers two task types:
  - ``state_scrape``   — runs a named adaptor from ADAPTORS + run_state_scrape_job
  - ``generic_scrape`` — runs the fallback GenericStateScraper + run_generic_scrape_job

Adaptors cannot be JSON-serialized, so payloads carry the adaptor name;
the handler reconstructs the instance from the module-level ADAPTORS dict.
"""

from __future__ import annotations

import asyncio
from typing import Any

from shared.task_queue import register_task_handler

from .scraper_job import run_state_scrape_job, run_generic_scrape_job


def _handle_state_scrape(
    *,
    adaptor_name: str,
    url: str,
    jurisdiction_code: str,
    tenant_id: str | None = None,
    **_: Any,
) -> None:
    from .routes_scraping import ADAPTORS
    adaptor_instance = ADAPTORS.get(adaptor_name)
    if adaptor_instance is None:
        raise ValueError(f"Unknown adaptor: {adaptor_name!r}")
    asyncio.run(
        run_state_scrape_job(
            adaptor_name=adaptor_name,
            adaptor_instance=adaptor_instance,
            url=url,
            jurisdiction_code=jurisdiction_code,
            tenant_id=tenant_id,
        )
    )


def _handle_generic_scrape(
    *,
    url: str,
    jurisdiction_code: str,
    tenant_id: str | None = None,
    **_: Any,
) -> None:
    asyncio.run(
        run_generic_scrape_job(
            url=url,
            jurisdiction_code=jurisdiction_code,
            tenant_id=tenant_id,
        )
    )


def register_scraping_handlers() -> None:
    """Call once at startup to wire handlers into TASK_HANDLERS."""
    register_task_handler("state_scrape", _handle_state_scrape)
    register_task_handler("generic_scrape", _handle_generic_scrape)
