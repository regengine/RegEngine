"""Supplier-facing token-scoped endpoints (no account, no principal).

Tenant binding: the token row IS the authenticated context — tenant_id is
read only from that server-side row (SECURITY DEFINER lookup), the RLS GUC
is set from it, and every query still carries explicit tenant/case
predicates. Request bodies define no tenant field at all.

Anti-enumeration: every token failure returns the same 400 body and every
session failure the same 401 body; the real deny reason goes to the audit
log only. Raw tokens appear once in the emailed link; only hashes are
stored. GET never consumes the token (acceptance #7) — only the explicit
exchange rotates a session.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from shared.database import get_db_session

from . import corrections, outbox, service, tokens
from .audit_utils import audit_event
from .schemas import MAX_FIELD_VALUE_CHARS, CorrectionRequest, ExchangeRequest
from .state import transition

logger = logging.getLogger("remediation.supplier")

router = APIRouter(prefix="/api/v1/remediation/supplier", tags=["Supplier Remediation (token)"])

_get_db_session = get_db_session  # test-override alias

# In-memory sliding-window rate limiter (per-process; multi-worker deploys
# should front this with the shared Redis limiter — documented limitation).
_WINDOW_SECONDS = 60
_BUCKETS: Dict[str, List[float]] = defaultdict(list)


def _rate_limit(request: Request, bucket: str, limit: int) -> None:
    now = time.monotonic()
    client_ip = request.client.host if request.client else "unknown"
    key = f"{bucket}:{client_ip}"
    hits = _BUCKETS[key]
    hits[:] = [t for t in hits if now - t < _WINDOW_SECONDS]
    if len(hits) >= limit:
        raise HTTPException(status_code=429, detail="Too many requests")
    hits.append(now)


def _db(db_session):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return db_session


def _case_context(db, token_row: Dict[str, Any]) -> Dict[str, Any]:
    from .router import _load_case  # same package; avoids duplicating the loader

    case = _load_case(db, token_row["tenant_id"], token_row["case_id"])
    record = service.load_record(db, tenant_id=token_row["tenant_id"], record_id=case["manifest_record_id"])
    current_values = {
        f["field_path"]: corrections.get_value(record["normalized_payload"] or {}, f["field_path"])
        for f in case["allowed_fields"]
    }
    return {
        "case_id": case["id"],
        "status": case["status"],
        "supplier": case["supplier_org"],
        "manifest": case["manifest_ref"],
        "line": case["line_ref"],
        "due_at": case["due_at"],
        "authorized_fields": case["allowed_fields"],
        "current_values": current_values,
        "failures": record["rule_failures"],
        "_case": case,
        "_record": record,
    }


@router.get("/{token}", summary="View the correction request (does not consume the link)")
async def get_token_context(token: str, request: Request, db_session=Depends(get_db_session)):
    _rate_limit(request, "preview", 10)
    db = _db(db_session)
    token_row = tokens.resolve_active_token(db, token)
    ctx = _case_context(db, token_row)
    return {k: v for k, v in ctx.items() if not k.startswith("_")}


@router.post("/exchange", summary="Exchange the link token for a 30-minute correction session")
async def exchange(body: ExchangeRequest, request: Request, db_session=Depends(get_db_session)):
    _rate_limit(request, "exchange", 5)
    db = _db(db_session)
    token_row = tokens.resolve_active_token(db, body.token)
    session = tokens.exchange_for_session(db, token_row)
    ctx = _case_context(db, token_row)
    return {
        "session_token": session["session_token"],
        "session_expires_at": session["expires_at"].isoformat(),
        "case": {k: v for k, v in ctx.items() if not k.startswith("_")},
    }


def _session_row(db, authorization: str) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise tokens.SESSION_NOT_VALID
    return tokens.resolve_active_session(db, authorization[7:].strip())


@router.get("/session/current", summary="Current record state for an active session")
async def get_session_state(
    request: Request,
    authorization: str = Header(default=""),
    db_session=Depends(get_db_session),
):
    _rate_limit(request, "session", 30)
    db = _db(db_session)
    token_row = _session_row(db, authorization)
    ctx = _case_context(db, token_row)
    return {k: v for k, v in ctx.items() if not k.startswith("_")}


@router.post("/session/corrections", summary="Submit a correction (attested, append-only)")
async def submit_correction(
    body: CorrectionRequest,
    request: Request,
    authorization: str = Header(default=""),
    db_session=Depends(get_db_session),
):
    _rate_limit(request, "correction", 10)
    db = _db(db_session)
    token_row = _session_row(db, authorization)
    ctx = _case_context(db, token_row)
    case, record = ctx["_case"], ctx["_record"]
    tenant_id = token_row["tenant_id"]

    if case["status"] != "awaiting_supplier":
        raise HTTPException(status_code=409, detail=f"Case is not awaiting a correction (status: {case['status']})")
    if not body.attestation.accepted:
        raise HTTPException(status_code=422, detail="The accuracy attestation must be accepted")

    allowed_paths = [f["field_path"] for f in case["allowed_fields"]]
    issue_by_field = {f["field_path"]: f.get("issue_id") for f in case["allowed_fields"]}
    for field_path, value in body.changes.items():
        corrections.validate_field_path(field_path, allowed_paths)
        if len(str(value)) > MAX_FIELD_VALUE_CHARS:
            raise HTTPException(
                status_code=422, detail=f"Value for '{field_path}' exceeds {MAX_FIELD_VALUE_CHARS} characters"
            )

    original_event = record["normalized_payload"] or {}
    previous_values = {p: corrections.get_value(original_event, p) for p in body.changes}

    patch_ids = corrections.insert_patches(
        db,
        tenant_id=tenant_id,
        case_id=case["id"],
        manifest_record_id=record["id"],
        changes=dict(body.changes),
        previous_values=previous_values,
        issue_by_field=issue_by_field,
        correcting_org=body.correcting_org or case["supplier_org"],
        actor_name=body.actor_name,
        actor_role=body.actor_role,
        correction_reason=body.reason,
        attestation_text=body.attestation.text,
        evidence_ref=body.evidence_ref,
    )

    # Apply patches to the staged record (original raw_row is never touched).
    updated = original_event
    for field_path, value in body.changes.items():
        updated = corrections.set_value(updated, field_path, value)
    record["normalized_payload"] = updated

    provenance = record["field_provenance"] or {}
    for i, field_path in enumerate(sorted(body.changes.keys())):
        provenance[field_path] = {
            "source": "supplier_correction",
            "patch_id": patch_ids[i] if i < len(patch_ids) else None,
            "value": body.changes[field_path],
        }
    _store_provenance(db, tenant_id, record["id"], provenance)

    audit_event(
        db,
        tenant_id=tenant_id,
        event_type="remediation.correction.submit",
        action="remediation.correction.submit",
        resource_type="remediation_case",
        resource_id=case["id"],
        metadata={
            "patch_ids": patch_ids,
            "field_paths": sorted(body.changes.keys()),
            "actor_name": body.actor_name,
            "actor_role": body.actor_role,
            "auth_method": "remediation_token",
        },
    )

    transition(
        db,
        tenant_id=tenant_id,
        case_id=case["id"],
        to_status="correction_submitted",
        expected_from="awaiting_supplier",
        actor=body.actor_name,
    )
    transition(
        db,
        tenant_id=tenant_id,
        case_id=case["id"],
        to_status="revalidating",
        expected_from="correction_submitted",
        actor="system",
    )

    result = service.revalidate_record(db, tenant_id=tenant_id, record=record)

    if not result["blocking"]:
        meta = service.get_run_meta(db, tenant_id=tenant_id, run_id=record["ingestion_run_id"])
        event_id = service.release_record(db, tenant_id=tenant_id, record=record, source_meta=meta)
        transition(
            db,
            tenant_id=tenant_id,
            case_id=case["id"],
            to_status="released",
            expected_from="revalidating",
            actor="system",
        )
        _resolve_exception(db, tenant_id, case, event_id)
        _notify_buyer(db, tenant_id, case, released_event_id=event_id, still_blocked=False)
        return {
            "status": "released",
            "released_event_id": event_id,
            "patch_ids": patch_ids,
            "message": "Correction accepted. The record passed revalidation and has been released.",
        }

    transition(
        db,
        tenant_id=tenant_id,
        case_id=case["id"],
        to_status="buyer_review",
        expected_from="revalidating",
        actor="system",
    )
    _notify_buyer(db, tenant_id, case, released_event_id=None, still_blocked=True)
    return {
        "status": "still_blocked",
        "patch_ids": patch_ids,
        "failures": result["failures"],
        "message": "Correction recorded, but the record still fails validation. The buyer has been notified for review.",
    }


def _store_provenance(db, tenant_id: str, record_id: str, provenance: Dict[str, Any]) -> None:
    import json

    from sqlalchemy import text

    db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            UPDATE fsma.manifest_records
            SET field_provenance = CAST(:provenance AS jsonb), updated_at = now()
            WHERE id = CAST(:record_id AS uuid)
              AND tenant_id = CAST(:tenant_id AS uuid)
            """
        ),
        {"provenance": json.dumps(provenance), "record_id": record_id, "tenant_id": tenant_id},
    )


def _resolve_exception(db, tenant_id: str, case: Dict[str, Any], event_id: str) -> None:
    if not case.get("exception_case_id"):
        return
    try:
        from shared.exception_queue import ExceptionQueueService

        ExceptionQueueService(db).resolve_exception(
            tenant_id=tenant_id,
            case_id=case["exception_case_id"],
            resolution_summary=f"Supplier correction accepted; record released as event {event_id}.",
            resolved_by=f"supplier-remediation:{case['id']}",
        )
    except Exception as exc:  # pragma: no cover — mirror is best-effort
        logger.warning("exception_resolve_failed case=%s error=%s", case["id"], exc)


def _notify_buyer(db, tenant_id: str, case: Dict[str, Any], *, released_event_id, still_blocked: bool) -> None:
    subject = (
        f"Supplier correction released: {case['manifest_ref']} ({case['line_ref']})"
        if not still_blocked
        else f"Supplier correction needs review: {case['manifest_ref']} ({case['line_ref']})"
    )
    body_text = (
        f"The supplier corrected {case['line_ref']} and the record passed revalidation (event {released_event_id})."
        if not still_blocked
        else f"The supplier submitted a correction for {case['line_ref']} but the record still fails validation."
    )
    outbox.enqueue_preview(
        db,
        tenant_id=tenant_id,
        case_id=case["id"],
        recipient=None,
        subject=subject,
        body=body_text,
        payload={"case_id": case["id"], "released_event_id": released_event_id},
    )
