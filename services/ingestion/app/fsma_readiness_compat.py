"""Compatibility endpoints for customer-readiness frontend probes.

The dashboard already degrades gracefully when export jobs and field mapping
review are not configured. These backend endpoints mirror that response so
production probes do not produce noisy 404 warnings while those workflows are
still account-gated.

#2893 — they answer 501 Not Implemented, not 200. An empty 200 is an
affirmative claim that the tenant has no FSMA export jobs, and a client
that checks ``response.ok`` (most generated clients do) cannot tell that
apart from "this capability does not exist"; the distinguishing signal was
buried in ``meta.status``. Never assert an empty evidence set that was
never queried. The body keeps the ``meta.status: not_connected`` marker for
callers that do read it, and the Next.js BFF in
``frontend/src/app/api/fsma/customer-readiness/*`` already falls through to
its own not_connected payload on any non-ok backend response — the same
path it takes when the backend is unreachable — so the dashboard renders
identically. Its sibling POST handler already answers 501 for this very
capability.
"""

from __future__ import annotations

from fastapi import APIRouter, status

router = APIRouter(
    prefix="/api/v1/fsma",
    tags=["FSMA Customer Readiness"],
    include_in_schema=False,
)


@router.get("/export-jobs", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_export_jobs() -> dict[str, object]:
    return {
        "jobs": [],
        "meta": {
            "status": "not_connected",
            "message": "Export job scheduling is not yet available — this capability is still in development.",
        },
    }


@router.get("/mappings", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_field_mappings() -> dict[str, object]:
    return {
        "items": [],
        "meta": {
            "status": "not_connected",
            "message": "Field mapping review is not yet available — this capability is still in development.",
        },
    }
