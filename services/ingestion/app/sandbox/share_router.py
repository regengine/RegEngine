"""
Sandbox Share Router — persisted share links for sandbox evaluations.

Split out of ``sandbox/router.py`` by #3825 so the stateless evaluation
surface (``/evaluate``, ``/trace``) could be promoted into the production
router allowlist without carrying these two endpoints with it.

They are mounted under their own router owner, ``sandbox_share``, which stays
in ``EXPERIMENTAL_ROUTERS`` and out of ``PRODUCTION_ENABLED_ROUTERS``. Three
reasons they are not production-eligible as written:

1. ``POST /share`` is an UNAUTHENTICATED write: it inserts caller-supplied CSV
   (up to 2MB, possibly real supplier data) into ``sandbox_shares`` with no
   auth principal and no tenant, retained 30 days.
2. Its output is already dead. ``share_url`` points at ``/sandbox/results/{id}``,
   a frontend route that was deleted when the public sandbox page was retired,
   so a successful share returns a link to a 404.
3. The rate limit does not hold at scale. ``_share_buckets`` is a per-process
   dict, so the 10/hour/IP cap is per-replica rather than per-deployment.

Retiring or repointing these endpoints is tracked as a follow-up to #3825.
Do not add ``sandbox_share`` to the production allowlist without resolving
all three.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import text

from .client_ip import resolve_client_ip
from .models import (
    SandboxResponse,
    SandboxShareRequest,
    SandboxShareResponse,
)

logger = structlog.get_logger("sandbox.share")

router = APIRouter(prefix="/api/v1/sandbox", tags=["Sandbox"])


# In-memory share rate limiter (10/hour per IP)
_share_buckets: Dict[str, list] = {}
_SHARE_RATE_LIMIT = 10
_SHARE_WINDOW = 3600
# #2711: cap unbounded key growth — when exceeded, evict buckets whose
# newest entry has aged out of the window (an IP that never returns
# otherwise keeps its bucket forever).
_SHARE_BUCKET_CAP = 10000


def _evict_stale_share_buckets(now: float) -> None:
    """Drop empty/aged-out share buckets once the dict exceeds the cap (#2711)."""
    if len(_share_buckets) <= _SHARE_BUCKET_CAP:
        return
    cutoff = now - _SHARE_WINDOW
    for stale_key in [k for k, v in _share_buckets.items() if not v or v[-1] < cutoff]:
        _share_buckets.pop(stale_key, None)


@router.post(
    "/share",
    response_model=SandboxShareResponse,
    summary="Create a shareable link for sandbox results",
)
async def sandbox_share(payload: SandboxShareRequest, request: Request) -> SandboxShareResponse:
    """Store evaluation results and return a shareable URL."""
    # Trusted-proxy-aware client IP (see resolve_client_ip); falls back to the
    # socket peer when no trusted proxy is configured.
    client_ip = resolve_client_ip(request)

    # Rate limit shares (10/hour per IP)
    now = datetime.now(timezone.utc).timestamp()
    bucket = _share_buckets.setdefault(client_ip, [])
    bucket[:] = [t for t in bucket if now - t < _SHARE_WINDOW]
    if len(bucket) >= _SHARE_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Share rate limit exceeded. Try again later.")
    bucket.append(now)
    _evict_stale_share_buckets(now)

    # Same payload guard as /evaluate: shares store the CSV the user
    # evaluated, which was already capped at 2MB there.
    if len(payload.csv) > 2_000_000:
        raise HTTPException(
            status_code=413,
            detail="CSV text too large for sandbox (max 2MB). Contact us for unlimited evaluation.",
        )

    share_id = secrets.token_urlsafe(12)
    ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:16]
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    try:
        from shared.database import get_db

        with get_db() as db:
            db.execute(
                text(
                    "INSERT INTO sandbox_shares (id, csv_text, result_json, ip_hash, expires_at) "
                    "VALUES (:id, :csv, :result, :ip_hash, :expires_at)"
                ),
                {
                    "id": share_id,
                    "csv": payload.csv,
                    "result": payload.result.model_dump_json(),
                    "ip_hash": ip_hash,
                    "expires_at": expires_at,
                },
            )
            db.commit()
    except Exception as e:
        logger.error("sandbox_share_error", error=str(e))
        raise HTTPException(status_code=503, detail="Sharing is temporarily unavailable.")

    return SandboxShareResponse(
        share_id=share_id,
        share_url=f"/sandbox/results/{share_id}?utm_source=sandbox_share&utm_medium=link",
        expires_at=expires_at.isoformat(),
    )


@router.get(
    "/share/{share_id}",
    response_model=SandboxResponse,
    summary="Retrieve shared sandbox results",
)
async def sandbox_share_get(share_id: str) -> SandboxResponse:
    """Retrieve shared evaluation results by ID."""
    if len(share_id) > 20:
        raise HTTPException(status_code=400, detail="Invalid share ID")

    try:
        from shared.database import get_db

        with get_db() as db:
            row = db.execute(
                text(
                    "UPDATE sandbox_shares SET view_count = view_count + 1 "
                    "WHERE id = :id AND expires_at > now() "
                    "RETURNING result_json"
                ),
                {"id": share_id},
            ).fetchone()
            db.commit()
    except Exception as e:
        logger.error("sandbox_share_get_error", error=str(e))
        raise HTTPException(status_code=503, detail="Share retrieval temporarily unavailable.")

    if not row:
        raise HTTPException(status_code=404, detail="Shared result not found or expired.")

    import json

    result_data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    try:
        return SandboxResponse(**result_data)
    except ValidationError:
        # Stored result predates the current response shape. Report it as
        # gone rather than turning a schema drift into a 500.
        raise HTTPException(status_code=404, detail="Shared result not found or expired.")
