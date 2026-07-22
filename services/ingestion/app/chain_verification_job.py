"""
Background Chain Verification Job.

Provides endpoints to trigger and poll hash chain verification for tenants.
Verifies the integrity of the FSMA 204 CTE hash chain using
CTEPersistence.verify_chain() and logs results to the audit system.

Endpoints:
    POST /api/v1/chain/verify-all       — Kick off chain verification for a tenant
    GET  /api/v1/chain/verify-all/{job_id} — Poll for verification results
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from shared.tenant_context import TenantContext

from .webhook_compat import require_tenant_context

logger = logging.getLogger("chain-verification")

router = APIRouter(prefix="/api/v1/chain", tags=["Chain Verification"])


# ---------------------------------------------------------------------------
# In-memory job store (fallback when DB table doesn't exist)
# ---------------------------------------------------------------------------

_verification_jobs: dict[str, dict] = {}
_verification_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class VerifyAllRequest(BaseModel):
    """Request to start a chain verification job."""

    tenant_id: str = Field(..., description="Tenant whose chain to verify")


class VerificationJobResponse(BaseModel):
    """Response after kicking off a verification job."""

    job_id: str
    tenant_id: str
    status: str
    started_at: str


class VerificationResultResponse(BaseModel):
    """Full result of a completed verification job."""

    job_id: str
    tenant_id: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    chain_valid: Optional[bool] = None
    chain_length: Optional[int] = None
    errors: list[str] = Field(default_factory=list)
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _combine_verifications(canonical_result, legacy_result):
    """Combine the canonical and legacy chain verifications (#2506).

    Both verifiers walk the SAME ``fsma.hash_chain`` rows (sequence,
    linkage, and ``chain_hash`` recompute are store-independent and
    identical). They diverge only on:
      * the orphan check — store-specific: the canonical verifier flags a
        row whose ``event_id`` is absent from ``traceability_events``, the
        legacy one whose id is absent from ``cte_events``;
      * event-content tamper — a canonical-only capability (re-derives
        ``sha256_hash`` from the canonical row).

    During the dual-write migration a chain row legitimately lives in only
    one store. So a row is a TRUE orphan only when BOTH stores miss it. A
    canonical event-content tamper, or a sequence/linkage/chain_hash break,
    is real regardless of store. Returns ``(valid, chain_length, errors)``.
    """
    canonical_orphans = set(canonical_result.orphan_chain_rows or [])
    legacy_orphans = set(legacy_result.orphan_chain_rows or [])
    true_orphans = sorted(canonical_orphans & legacy_orphans)

    # Non-orphan failures from the canonical verifier: tamper (event +
    # chain_hash), sequence gaps, linkage breaks. The canonical verifier
    # skips event-hash recompute for rows it considers orphaned, so its
    # ``tamper_rows`` never contains a legacy-only (canonical-orphan) row.
    canonical_non_orphan_break = bool(canonical_result.tamper_rows) or any(
        "Sequence gap" in e or "Chain break" in e or "Genesis entry" in e for e in (canonical_result.errors or [])
    )

    valid = not true_orphans and not canonical_non_orphan_break
    chain_length = max(canonical_result.chain_length, legacy_result.chain_length)

    errors: list[str] = []
    if canonical_non_orphan_break:
        errors.extend(e for e in (canonical_result.errors or []) if "Orphan chain row" not in e)
    if true_orphans:
        errors.append(f"Orphan chain rows missing from BOTH stores: {true_orphans}")
    return valid, chain_length, errors


def _run_verification(job_id: str, tenant_id: str) -> None:
    """Execute chain verification in a background thread."""
    try:
        from shared.canonical_persistence import CanonicalEventStore
        from shared.cte_persistence import CTEPersistence
        from shared.database import SessionLocal
        from shared.tenant_context import tenant_scope

        # #2461: contextvars do NOT inherit into threading.Thread bodies —
        # seed the tenant here, inside the thread, so the Engine begin-hook
        # applies app.tenant_id to every transaction below (including the
        # re-begin after _persist_verification_result's commit/rollback).
        # This is what makes verify_chain_canonical / verify_chain (both
        # read RLS-forced fsma.hash_chain) survive the #2461 cutover.
        with tenant_scope(tenant_id):
            _run_verification_inner(job_id, tenant_id, CanonicalEventStore, CTEPersistence, SessionLocal)
    except Exception as exc:
        logger.error(
            "chain_verification_failed job_id=%s tenant_id=%s error=%s",
            job_id,
            tenant_id,
            str(exc),
        )
        with _verification_lock:
            _verification_jobs[job_id].update(
                {
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "chain_valid": None,
                    "chain_length": 0,
                    "errors": [str(exc)],
                    "message": f"Verification failed: {exc}",
                }
            )


def _run_verification_inner(job_id: str, tenant_id: str, CanonicalEventStore, CTEPersistence, SessionLocal) -> None:
    """Body of the verification job — runs inside tenant_scope."""
    db = SessionLocal()
    try:
        # #2506: walk BOTH stores and combine (see _combine_verifications).
        canonical_result = CanonicalEventStore(db, dual_write=False).verify_chain_canonical(tenant_id)
        legacy_result = CTEPersistence(db).verify_chain(tenant_id)

        chain_valid, chain_length, errors = _combine_verifications(canonical_result, legacy_result)
        completed_at = datetime.now(timezone.utc).isoformat()

        # Try to persist to fsma.chain_verification_log
        _persist_verification_result(
            db,
            job_id,
            tenant_id,
            chain_valid,
            chain_length,
            errors,
            completed_at,
        )

        with _verification_lock:
            _verification_jobs[job_id].update(
                {
                    "status": "completed",
                    "completed_at": completed_at,
                    "chain_valid": chain_valid,
                    "chain_length": chain_length,
                    "errors": errors,
                    "message": (
                        "Chain integrity verified — no tampering detected"
                        if chain_valid
                        else f"Chain integrity FAILED — {len(errors)} error(s) detected"
                    ),
                }
            )

        logger.info(
            "chain_verification_complete job_id=%s tenant_id=%s valid=%s length=%d errors=%d",
            job_id,
            tenant_id,
            chain_valid,
            chain_length,
            len(errors),
        )

        # Log to audit system (best-effort, async)
        _log_verification_audit(tenant_id, job_id, chain_valid, chain_length, errors)

    finally:
        db.close()


def _persist_verification_result(
    db,
    job_id: str,
    tenant_id: str,
    chain_valid: bool,
    chain_length: int,
    errors: list[str],
    completed_at: str,
) -> None:
    """Try to write result to fsma.chain_verification_log; fall back silently."""
    try:
        import json

        from sqlalchemy import text

        db.execute(
            text("""
                INSERT INTO fsma.chain_verification_log
                    (job_id, tenant_id, chain_valid, chain_length, errors, completed_at)
                VALUES
                    (:job_id, :tid, :valid, :length, :errors, :completed)
            """),
            {
                "job_id": job_id,
                "tid": tenant_id,
                "valid": chain_valid,
                "length": chain_length,
                "errors": json.dumps(errors),
                "completed": completed_at,
            },
        )
        db.commit()
    except Exception as exc:
        logger.debug(
            "chain_verification_log_persist_skipped reason=%s (using in-memory fallback)",
            str(exc),
        )
        try:
            db.rollback()
        except Exception:
            logger.debug("chain_verification_rollback_failed", exc_info=True)


def _log_verification_audit(
    tenant_id: str,
    job_id: str,
    chain_valid: bool,
    chain_length: int,
    errors: list[str],
) -> None:
    """Best-effort audit log entry for the verification run."""
    try:
        import asyncio

        from shared.audit_logging import AuditActor, AuditEventCategory, AuditEventType, AuditLogger, AuditSeverity

        audit = AuditLogger.get_instance()
        actor = AuditActor(
            actor_id="system",
            actor_type="service",
            username="chain-verification-job",
            ip_address="127.0.0.1",
            tenant_id=tenant_id,
        )
        severity = AuditSeverity.INFO if chain_valid else AuditSeverity.WARNING

        # Run async log in a new event loop if needed
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        coro = audit.log(
            event_type=AuditEventType.DATA_READ,
            category=AuditEventCategory.DATA_ACCESS,
            severity=severity,
            actor=actor,
            action="chain_verification",
            outcome="success" if chain_valid else "failure",
            message=f"Chain verification for tenant {tenant_id}: valid={chain_valid}, length={chain_length}",
            details={
                "job_id": job_id,
                "chain_valid": chain_valid,
                "chain_length": chain_length,
                "error_count": len(errors),
            },
            tags=["chain_verification", "integrity"],
        )

        if loop and loop.is_running():
            asyncio.ensure_future(coro)
        else:
            asyncio.run(coro)

    except Exception as exc:
        logger.debug("audit_log_skipped reason=%s", str(exc))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/verify-all",
    response_model=VerificationJobResponse,
    status_code=202,
    summary="Start chain verification for a tenant",
)
async def start_chain_verification(
    request: VerifyAllRequest,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Kick off a background chain verification job for the given tenant.

    Returns a job_id that can be polled via GET /verify-all/{job_id}.
    """
    job_id = str(uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    tenant_id = ctx.tenant_id

    job_record = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "status": "running",
        "started_at": started_at,
        "completed_at": None,
        "chain_valid": None,
        "chain_length": None,
        "errors": [],
        "message": None,
    }

    with _verification_lock:
        _verification_jobs[job_id] = job_record

    # Run verification in background thread
    thread = threading.Thread(
        target=_run_verification,
        args=(job_id, tenant_id),
        daemon=True,
    )
    thread.start()

    logger.info(
        "chain_verification_started job_id=%s tenant_id=%s",
        job_id,
        tenant_id,
    )

    return VerificationJobResponse(
        job_id=job_id,
        tenant_id=tenant_id,
        status="running",
        started_at=started_at,
    )


@router.get(
    "/verify-all/{job_id}",
    response_model=VerificationResultResponse,
    summary="Poll chain verification job status",
)
async def get_verification_result(
    job_id: str,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Get the current status/result of a chain verification job."""
    with _verification_lock:
        job = _verification_jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Verification job '{job_id}' not found")
    if job.get("tenant_id") != ctx.tenant_id:
        raise HTTPException(status_code=404, detail=f"Verification job '{job_id}' not found")

    return VerificationResultResponse(**job)
