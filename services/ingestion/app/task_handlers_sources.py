"""Task-queue handlers for federal source adapters (ADR-002 PR-B).

Registers three task types consumed by the shared TaskWorker:
  - ``federal_register_ingest``
  - ``ecfr_ingest``
  - ``fda_ingest``

Each handler reconstructs the adapter from the payload and delegates to
``_run_adapter_ingest``, which is the same coroutine the old
``BackgroundTasks`` path used.  Moving to the task queue gives us
durability across SIGTERM and automatic retry with exponential backoff.
"""

from __future__ import annotations

import asyncio
from typing import Any

from shared.task_queue import register_task_handler

from regengine_ingestion.sources import FederalRegisterAdapter, ECFRAdapter, FDAAdapter
from .routes import _run_adapter_ingest


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _handle_federal_register(
    *,
    vertical: str,
    tenant_id: str,
    job_id: str,
    max_documents: int | None = None,
    date_from: str | None = None,
    agencies: list[str] | None = None,
    **_: Any,
) -> None:
    adapter = FederalRegisterAdapter(user_agent="RegEngine/1.0")
    asyncio.run(
        _run_adapter_ingest(
            adapter=adapter,
            vertical=vertical,
            tenant_id=tenant_id,
            source_system="federal_register_api",
            job_id=job_id,
            max_documents=max_documents,
            date_from=date_from,
            agencies=agencies,
        )
    )


def _handle_ecfr(
    *,
    vertical: str,
    tenant_id: str,
    job_id: str,
    cfr_title: int | None = None,
    cfr_part: str | None = None,
    **_: Any,
) -> None:
    adapter = ECFRAdapter(user_agent="RegEngine/1.0")
    asyncio.run(
        _run_adapter_ingest(
            adapter=adapter,
            vertical=vertical,
            tenant_id=tenant_id,
            source_system="ecfr_api",
            job_id=job_id,
            cfr_title=cfr_title,
            cfr_part=cfr_part,
        )
    )


def _handle_fda(
    *,
    vertical: str,
    tenant_id: str,
    job_id: str,
    max_documents: int | None = None,
    **_: Any,
) -> None:
    adapter = FDAAdapter(api_key=None, user_agent="RegEngine/1.0")
    asyncio.run(
        _run_adapter_ingest(
            adapter=adapter,
            vertical=vertical,
            tenant_id=tenant_id,
            source_system="openfda_api",
            job_id=job_id,
            max_documents=max_documents,
        )
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_source_handlers() -> None:
    """Call once at startup to wire handlers into TASK_HANDLERS."""
    register_task_handler("federal_register_ingest", _handle_federal_register)
    register_task_handler("ecfr_ingest", _handle_ecfr)
    register_task_handler("fda_ingest", _handle_fda)
