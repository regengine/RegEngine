"""Compatibility endpoints for customer-readiness frontend probes.

The dashboard already degrades gracefully when export jobs and field mapping
review are not configured. These backend endpoints mirror that response so
production probes do not produce noisy 404 warnings while those workflows are
still account-gated.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(
    prefix="/api/v1/fsma",
    tags=["FSMA Customer Readiness"],
    include_in_schema=False,
)


@router.get("/export-jobs")
async def list_export_jobs() -> dict[str, object]:
    return {
        "jobs": [],
        "meta": {
            "status": "not_connected",
            "message": "Export job scheduling is not yet configured for this account.",
        },
    }


@router.get("/mappings")
async def list_field_mappings() -> dict[str, object]:
    return {
        "items": [],
        "meta": {
            "status": "not_connected",
            "message": "Field mapping review is not yet configured for this account.",
        },
    }
